"""Split a plain-text email body into the sender's own text, forwarded content and quoted reply content.

Rules (derived from profiling the Enron subset):

1. Find the earliest "message boundary" marker in the body.
   - Forward markers: ``---- Forwarded by X on DATE ----`` (Lotus Notes, can wrap onto
     two lines), ``---- Forwarded message ----``, ``Begin forwarded message:``.
   - Reply markers: Lotus Notes reply headers (``Name`` / ``MM/DD/YYYY HH:MM AM`` / ... /
     ``To:``, or ``Name on MM/DD/YYYY HH:MM AM`` / ... / ``To:``).
   - Ambiguous markers, classified by the subject (``FW:``/``Fwd:`` -> forward, else reply):
     ``-----Original Message-----`` (Outlook uses it for both), a ``From:`` line directly
     followed by ``Sent:``, and an embedded raw header block (AOL-style forwards).
2. Everything after that marker goes, in one piece, to ``forwarded_content`` or
   ``quoted_content`` depending on the marker type. Nested forwards/replies stay inside
   that piece, so nothing is lost or reordered.
3. Before the marker, lines starting with ``>`` are inline quoted text: they move to
   ``quoted_content`` and the remaining lines are the sender's own ``body``.
"""
from __future__ import annotations

import re

_FLAGS = re.IGNORECASE | re.MULTILINE
_DATE_TIME = r"\d{1,2}/\d{1,2}/\d{2,4}[ \t]+\d{1,2}:\d{2}(?::\d{2})?[ \t]*[AP]M"

_FORWARD_MARKERS = (
    re.compile(r"^[ \t]*-{3,}[ \t]*Forwarded by\b", _FLAGS),
    re.compile(r"^[ \t]*-{3,}[ \t]*Forwarded message[ \t]*-{3,}", _FLAGS),
    re.compile(r"^[ \t]*Begin forwarded message:", _FLAGS),
)

_REPLY_MARKERS = (
    # Lotus Notes reply headers: always a reply.
    re.compile(rf"^[ \t]*\S[^\n]{{0,100}}\n[ \t]*{_DATE_TIME}[^\n]*\n(?:[^\n]*\n){{0,3}}?[ \t]*To:", _FLAGS),
    re.compile(rf"^[^\n]*\bon {_DATE_TIME}[^\n]*\n(?:[^\n]*\n){{0,3}}?[ \t]*To:", _FLAGS),
)

# Used by both replies and forwards (Outlook writes "Original Message" for both, AOL embeds raw
# headers). The subject decides: "FW:" / "Fwd:" first means forward, anything else means reply.
_AMBIGUOUS_MARKERS = (
    re.compile(r"^[ \t]*-{2,}[ \t]*Original Message[ \t]*-{2,}", _FLAGS),
    re.compile(r"^[ \t]*From:[^\n]*\n[ \t]*Sent:", _FLAGS),
    re.compile(
        r"^[ \t]*(?:Return-path|From):[^\n]*\n"
        r"(?:[ \t]*(?:From|Full-name|Message-ID|Received|Date|To|Subject|Reply-To|Return-path|cc):[^\n]*\n){2,}",
        _FLAGS,
    ),
)

_FORWARD_SUBJECT = re.compile(r"^\s*(?:fw|fwd)\s*:", re.IGNORECASE)
_QUOTED_LINE = re.compile(r"^[ \t]*>")


def _first_marker(text: str, subject: str) -> tuple[int, str] | None:
    """Return (position, kind) of the earliest boundary marker, kind is 'forward' or 'reply'."""
    ambiguous_kind = "forward" if _FORWARD_SUBJECT.match(subject or "") else "reply"
    first: tuple[int, str] | None = None
    groups = (("forward", _FORWARD_MARKERS), ("reply", _REPLY_MARKERS), (ambiguous_kind, _AMBIGUOUS_MARKERS))
    for kind, patterns in groups:
        for rx in patterns:
            m = rx.search(text)
            if m and (first is None or m.start() < first[0]):
                first = (m.start(), kind)
    return first


def split_body(text: str, subject: str = "") -> tuple[str, str | None, str | None]:
    """Return (own_body, forwarded_content, quoted_content). Empty parts come back as None,
    except own_body which is always a string (possibly empty for pure forwards).
    ``subject`` decides whether an ambiguous marker (Outlook "Original Message", embedded
    header block) starts forwarded or quoted content."""
    marker = _first_marker(text, subject)
    if marker is None:
        head, tail, kind = text, "", None
    else:
        pos, kind = marker
        head, tail = text[:pos], text[pos:]

    own_lines: list[str] = []
    quoted_lines: list[str] = []
    for line in head.split("\n"):
        (quoted_lines if _QUOTED_LINE.match(line) else own_lines).append(line)

    own = "\n".join(own_lines).strip()
    forwarded = tail.strip() if kind == "forward" else ""
    quoted_parts = ["\n".join(quoted_lines).strip()]
    if kind == "reply":
        quoted_parts.append(tail.strip())
    quoted = "\n\n".join(part for part in quoted_parts if part)
    return own, forwarded or None, quoted or None
