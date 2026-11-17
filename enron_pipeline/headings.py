"""Heuristic heading extraction for plain-text email content.

Plain text has no markup, so a heading is recognised by layout. A line (max 80 chars)
counts as a heading when it is one of:

1. Banner: text framed by runs of ``= * - _ ~ # +``, e.g. ``===== Sponsored by =====``.
2. Underlined: followed by a line made only of ``- = ~ _ *`` of roughly the same length
   (0.5x to 1.5x), not ending in sentence punctuation. Longer rules are separators.
3. ALL CAPS: at least 3 letters, all letters uppercase, at most 10 words, no sentence
   punctuation at the end, and not a lone sign-off word (THANKS, FYI, ...).
4. Label: stands alone after a blank line, at most 6 words, starts uppercase, ends with ``:``,
   and does not open a message (first line, or right after a To:/Subject: block), because
   there a ``Name:`` line is a salutation ("Jeff:"), not a heading.
5. Numbered section title: ``1. Overview``, ``II) Background`` after a blank line,
   at most 6 words, starts uppercase, no sentence punctuation at the end.

Never headings: embedded mail headers (To:, cc:, Subject:, ...), lines with URLs or
email addresses, ``>`` quoted lines, ``- `` list lines, tab-separated table rows,
salutations (Dear/Hi/Hello/Gentlemen ...), forward/reply separator lines, and attachment
file references (``<<File.doc>>``). Placeholders like ``[IMAGE]`` are removed first.
"""
from __future__ import annotations

import re

MAX_LEN = 80
MAX_WORDS = 10

_HEADER_LINE = re.compile(
    r"^(?:to|cc|bcc|from|subject|sent|date|re|fw|fwd|importance|attachments?|please respond to)\s*:", re.I
)
_RULE_ONLY = re.compile(r"^[=*\-_~#+ \t]{3,}$")
_BANNER = re.compile(r"^[=*\-_~#+]{3,}\s*([^=*\-_~#+\s].*?)\s*[=*\-_~#+]{3,}$")
_NUMBERED = re.compile(r"^(?:\d{1,2}|[IVX]{1,4})[.)]\s+(\S.*)$")
_URL_OR_EMAIL = re.compile(r"https?://|www\.|\S@\S")
_SEPARATOR_WORDS = re.compile(r"forwarded by|original message|forwarded message", re.I)
_FILE_REF = re.compile(
    r"<<|>>|\.(?:doc|xls|ppt|pdf|zip|txt|rtf|csv|jpg|gif|tif|bmp|msg|wpd|htm|html)x?\b", re.I
)
_PLACEHOLDER = re.compile(r"\[[^\]]{0,20}\]")  # newsletter image placeholders like [IMAGE]
_SALUTATION = re.compile(
    r"^(?:dear|hi|hello|hey|greetings|gentlemen|ladies|attention|to the attention of|good (?:morning|afternoon|evening))\b",
    re.I,
)
_SENTENCE_END = (".", ",", ";", "?", "!")
_SIGN_OFF = {"THANKS", "THANK", "REGARDS", "FYI", "ASAP", "HELLO", "OK", "YES", "NO", "PS", "NOTE"}


def _letters(s: str) -> list[str]:
    return [c for c in s if c.isalpha()]


def _is_all_caps(line: str) -> bool:
    letters = _letters(line)
    if len(letters) < 3 or not all(c.isupper() for c in letters):
        return False
    words = line.split()
    if len(words) > MAX_WORDS or line.endswith(_SENTENCE_END):
        return False
    return not (len(words) == 1 and re.sub(r"[^A-Z]", "", line) in _SIGN_OFF)


def _classify(line: str, prev_blank: bool, next_line: str, opening: bool) -> str | None:
    banner = _BANNER.match(line)
    if banner:
        return banner.group(1)
    if _RULE_ONLY.match(line):
        return None
    if next_line and _RULE_ONLY.match(next_line):
        # A real underline is about as long as its text; a much longer rule is a separator.
        rule_len = len(next_line.replace(" ", ""))
        if (
            max(3, len(line) // 2) <= rule_len <= len(line) * 1.5 + 3
            and not line.endswith(_SENTENCE_END)
            and len(line.split()) <= MAX_WORDS
        ):
            return line
        return None
    if _is_all_caps(line):
        return line
    words = line.split()
    if prev_blank and not opening and line.endswith(":") and len(words) <= 6 and line[0].isupper():
        return line
    numbered = _NUMBERED.match(line)
    if (
        numbered
        and prev_blank
        and len(numbered.group(1).split()) <= 6
        and numbered.group(1)[0].isupper()
        and not line.endswith(_SENTENCE_END)
    ):
        return line
    return None


def extract_headings(text: str) -> str | None:
    """Return newline-joined headings found in ``text`` (in order, de-duplicated), or None."""
    lines = text.splitlines()
    found: list[str] = []
    seen: set[str] = set()
    last_nonblank: str | None = None  # previous non-blank line, to spot message openings
    for i, raw in enumerate(lines):
        line = _PLACEHOLDER.sub("", raw).strip()
        opening = (
            last_nonblank is None
            or bool(_HEADER_LINE.match(last_nonblank))
            or bool(_SEPARATOR_WORDS.search(last_nonblank))
        )
        if raw.strip():
            last_nonblank = raw.strip()
        if (
            not line
            or len(line) > MAX_LEN
            or "\t" in line
            or line.startswith((">", "- "))
            or _HEADER_LINE.match(line)
            or _URL_OR_EMAIL.search(line)
            or _SEPARATOR_WORDS.search(line)
            or _FILE_REF.search(line)
            or _SALUTATION.match(line)
        ):
            continue
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        heading = _classify(line, prev_blank, next_line, opening)
        if heading:
            heading = heading.strip(" :\t")
            if len(_letters(heading)) >= 2 and heading not in seen:
                seen.add(heading)
                found.append(heading)
    return "\n".join(found) or None
