"""Parse one raw Enron email file into a structured record (spec Section 3).

Headers and body are split at the byte level first, so each part can be decoded on
its own terms: headers with a UTF-8 -> cp1252 -> latin-1 fallback, the body with its
Content-Transfer-Encoding (quoted-printable / base64) and declared charset first.
Parsing a decoded string with ``email.message_from_string`` guarantees every header
value is a ``str`` (bytes input can yield ``email.header.Header`` objects instead).

A missing mandatory field raises ``ParseError``; its message is the reason written
to the error log. All reasons for one file are reported together.
"""
from __future__ import annotations

import base64
import binascii
import quopri
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import message_from_bytes, message_from_string, policy
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from dateutil import parser as dateutil_parser

from .body_split import split_body
from .headings import extract_headings

FALLBACK_ENCODINGS = ("utf-8", "cp1252", "latin-1")

# Offsets (seconds east of UTC) for abbreviations that email.utils does not know.
TZINFOS = {
    "UT": 0, "UTC": 0, "GMT": 0, "Z": 0, "WET": 0, "BST": 3600, "CET": 3600, "CEST": 7200,
    "EET": 7200, "EEST": 10800, "AST": -14400, "ADT": -10800, "EST": -18000, "EDT": -14400,
    "CST": -21600, "CDT": -18000, "MST": -25200, "MDT": -21600, "PST": -28800, "PDT": -25200,
    "AKST": -32400, "AKDT": -28800, "HST": -36000, "JST": 32400, "IST": 19800, "SGT": 28800,
}

# 1980-01-01 00:00 UTC (DOS epoch) and 1970-01-01 (Unix epoch) are "no date" placeholders.
PLACEHOLDER_DATES = {
    datetime(1980, 1, 1, tzinfo=timezone.utc),
    datetime(1970, 1, 1, tzinfo=timezone.utc),
}
MIN_PLAUSIBLE_DATE = datetime(1990, 1, 1, tzinfo=timezone.utc)
MAX_PLAUSIBLE_DATE = datetime(2010, 1, 1, tzinfo=timezone.utc)

_HEADER_END = re.compile(rb"\r?\n\r?\n")
_TRAILING_ZONE = re.compile(r"\b([A-Za-z]{1,5})$")
_FALLBACK_ADDRESS = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")

_ATTACHMENT_HINTS = re.compile(
    r"<<\s*File:[^>]*>>"
    r"|<<[^<>\n]*\.(?:doc|xls|ppt|pdf|zip|txt|rtf|csv|jpg|gif|tif|bmp|msg|wpd|htm|html)x?\s*>>"
    r"|^[ \t]*-[ \t]+[^\n]{1,80}\.(?:doc|xls|ppt|pdf|zip|txt|rtf|csv|jpg|gif|tif|bmp|msg|wpd)x?[ \t]*$"
    r"|\battach(?:ed|ment|ments)\b",
    re.IGNORECASE | re.MULTILINE,
)


class ParseError(Exception):
    """A mandatory field could not be extracted. ``str(exc)`` is the logged reason."""


@dataclass
class EmailRecord:
    # Mandatory (spec 3.1)
    message_id: str
    date: datetime  # timezone-aware, UTC
    from_address: str
    to_addresses: list[str]
    subject: str
    body: str
    source_file: str
    # Optional (spec 3.2)
    cc_addresses: list[str] = field(default_factory=list)
    bcc_addresses: list[str] = field(default_factory=list)
    x_from: str | None = None
    x_to: str | None = None
    x_cc: str | None = None
    x_bcc: str | None = None
    x_folder: str | None = None
    x_origin: str | None = None
    content_type: str | None = None
    has_attachment: bool = False
    forwarded_content: str | None = None
    quoted_content: str | None = None
    headings: str | None = None
    # Parse diagnostics (not stored as spec fields)
    dropped_addresses: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- decoding helpers

def decode_bytes(data: bytes, preferred: str | None = None) -> str:
    """Decode bytes, trying the declared charset first, then UTF-8, cp1252, latin-1."""
    for encoding in ([preferred] if preferred else []) + list(FALLBACK_ENCODINGS):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")  # latin-1 cannot fail; kept for safety


def clean_header(value: object) -> str:
    """Unfold a header value (RFC 5322 continuation lines), decode RFC 2047 words, strip."""
    text = re.sub(r"\r?\n(?=[ \t])", "", str(value))
    if "=?" in text:
        try:
            text = str(make_header(decode_header(text)))
        except Exception:  # malformed encoded-word: keep the raw text
            pass
    return text.strip()


def _optional(msg: Message, name: str) -> str | None:
    value = msg.get(name)
    if value is None:
        return None
    return clean_header(value) or None


# ---------------------------------------------------------------- field parsers

def parse_date(value: str) -> datetime:
    """Parse an RFC 2822 date (offsets or tz abbreviations) and normalize to UTC."""
    cleaned = re.sub(r"\([^)]*\)", " ", value).strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None or dt.tzinfo is None:
        # email.utils silently returns a naive datetime for zone abbreviations it does not
        # know (e.g. CEST). Re-parse with dateutil and an explicit abbreviation table.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # dateutil's UnknownTimezoneWarning, handled below
                dt = dateutil_parser.parse(cleaned, tzinfos=TZINFOS)
        except (ValueError, OverflowError, TypeError) as exc:
            raise ParseError(f"unparseable Date {value!r}") from exc
        if dt.tzinfo is None:
            zone = _TRAILING_ZONE.search(cleaned)
            if zone and zone.group(1).upper() not in ("AM", "PM"):
                raise ParseError(f"unknown timezone {zone.group(1)!r} in Date {value!r}")
            dt = dt.replace(tzinfo=timezone.utc)  # no zone given at all: treat as UTC
    dt = dt.astimezone(timezone.utc)
    if dt in PLACEHOLDER_DATES:
        raise ParseError(f"placeholder Date {value!r} ({dt.isoformat()} is an epoch placeholder)")
    if not MIN_PLAUSIBLE_DATE <= dt < MAX_PLAUSIBLE_DATE:
        raise ParseError(f"implausible Date {value!r}")
    return dt


def parse_address_list(values: list[str]) -> tuple[list[str], list[str]]:
    """Return (addresses, dropped_tokens). Addresses are bare, lowercased, de-duplicated."""
    cleaned = [clean_header(v) for v in values if v is not None]
    addresses: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        address = candidate.strip().strip("<>").lower()
        if address and address not in seen:
            seen.add(address)
            addresses.append(address)

    for name, addr in getaddresses(cleaned):
        token = addr.strip()
        if not token:
            if name.strip():
                dropped.append(name.strip())
            continue
        if "@" in token and " " not in token and not token.startswith("@") and not token.endswith("@"):
            add(token)
        else:
            dropped.append(token)

    if not addresses:  # strict getaddresses can reject a whole odd header; fall back to a regex scan
        for value in cleaned:
            for match in _FALLBACK_ADDRESS.findall(value):
                add(match)
    return addresses, dropped


def infer_attachment(content_type: str | None, text: str) -> bool:
    """Attachment inferred from MIME type/boundary or from attachment references in the body."""
    ct = (content_type or "").lower()
    if ct.startswith("multipart/") or "boundary=" in ct:
        return True
    return bool(_ATTACHMENT_HINTS.search(text))


def _decode_transfer(body: bytes, cte: str) -> bytes:
    cte = cte.strip().lower()
    if cte == "quoted-printable":
        return quopri.decodestring(body)
    if cte == "base64":
        try:
            return base64.b64decode(body, validate=False)
        except (binascii.Error, ValueError):
            return body
    return body


def _multipart_text(raw: bytes) -> str:
    """Concatenate the text/plain parts of a MIME multipart message."""
    msg = message_from_bytes(raw, policy=policy.compat32)
    parts = []
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            payload = part.get_payload(decode=True) or b""
            parts.append(decode_bytes(payload, part.get_content_charset()))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- main entry points

def parse_bytes(raw: bytes, source_file: str) -> EmailRecord:
    """Parse raw email bytes. Raises ParseError with a reason if a mandatory field is missing."""
    if not raw.strip():
        raise ParseError("empty file")
    if b"\x00" in raw[:4096]:
        raise ParseError("binary content (NUL bytes), not an RFC 2822 text email")

    match = _HEADER_END.search(raw)
    header_bytes, body_bytes = (raw[: match.start()], raw[match.end():]) if match else (raw, b"")
    msg = message_from_string(decode_bytes(header_bytes) + "\n\n", policy=policy.compat32)
    if not msg.keys():
        raise ParseError("no headers found")

    errors: list[str] = []

    message_id = clean_header(msg.get("Message-ID", ""))
    if not message_id:
        errors.append("missing Message-ID")

    date: datetime | None = None
    date_value = clean_header(msg.get("Date", ""))
    if not date_value:
        errors.append("missing Date")
    else:
        try:
            date = parse_date(date_value)
        except ParseError as exc:
            errors.append(str(exc))

    from_list, _ = parse_address_list(msg.get_all("From", []))
    if not from_list:
        from_raw = msg.get("From")
        errors.append(f"invalid From {clean_header(from_raw)[:80]!r}" if from_raw is not None else "missing From")

    if msg.get("To") is None:
        errors.append(f"missing To (X-To: {_optional(msg, 'X-To')!r})")
        to_list, to_dropped = [], []
    else:
        to_list, to_dropped = parse_address_list(msg.get_all("To", []))
        if not to_list:
            errors.append(f"To has no valid address ({clean_header(msg.get('To'))[:80]!r})")

    subject_raw = msg.get("Subject")
    if subject_raw is None:
        errors.append("missing Subject")
    subject = clean_header(subject_raw) if subject_raw is not None else ""

    content_type = _optional(msg, "Content-Type")
    if content_type and content_type.lower().startswith("multipart/"):
        text = _multipart_text(raw)
    else:
        decoded = _decode_transfer(body_bytes, msg.get("Content-Transfer-Encoding", ""))
        text = decode_bytes(decoded, msg.get_content_charset())
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        errors.append("empty body")

    if errors:
        raise ParseError("; ".join(errors))

    cc_list, cc_dropped = parse_address_list(msg.get_all("Cc", []))
    bcc_list, bcc_dropped = parse_address_list(msg.get_all("Bcc", []))
    own_body, forwarded, quoted = split_body(text, subject)

    return EmailRecord(
        message_id=message_id,
        date=date,  # type: ignore[arg-type]  # not None once errors is empty
        from_address=from_list[0],
        to_addresses=to_list,
        subject=subject,
        body=own_body,
        source_file=source_file,
        cc_addresses=cc_list,
        bcc_addresses=bcc_list,
        x_from=_optional(msg, "X-From"),
        x_to=_optional(msg, "X-To"),
        x_cc=_optional(msg, "X-cc"),
        x_bcc=_optional(msg, "X-bcc"),
        x_folder=_optional(msg, "X-Folder"),
        x_origin=_optional(msg, "X-Origin"),
        content_type=content_type,
        has_attachment=infer_attachment(content_type, text),
        forwarded_content=forwarded,
        quoted_content=quoted,
        headings=extract_headings(text),
        dropped_addresses=to_dropped + cc_dropped + bcc_dropped,
    )


def parse_file(path: Path, base_dir: Path) -> EmailRecord:
    """Parse one file. ``source_file`` is the POSIX path relative to ``base_dir``."""
    return parse_bytes(path.read_bytes(), path.relative_to(base_dir).as_posix())
