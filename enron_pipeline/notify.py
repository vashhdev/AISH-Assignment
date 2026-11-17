"""Task 4: duplicate notification emails, as .eml drafts and as live sends through a Gmail MCP server.

Dry run (default): one draft ``.eml`` per flagged duplicate in ``output/replies/``, built from
the notification template.

Live (``--send-live``): one notification per duplicate group, about the group's latest duplicate,
sent with the Gmail MCP server's ``send_email`` tool. Python is the MCP client: it spawns the
server over stdio (command from ``mcp_config.json``, else the pinned default below), checks that
``send_email`` is offered, and calls it once per notification.

Safety rails for live mode:
- Mail never goes to the dataset's addresses. Every live send goes to ``NOTIFY_LIVE_TO`` (from the
  environment or ``.env``). The intended recipient is kept in ``output/send_log.csv``. The body is
  exactly the template.
- The recipient is refused if it is an @enron.com address or appears anywhere in the database.
- At most ``--limit`` groups per run (default 5, hard ceiling 50). Groups go in report order and
  groups already notified are skipped, so each run continues where the last one stopped.
- ``notification_sent`` / ``notification_date`` are set right after each confirmed send, so a crash
  mid-run cannot cause a re-send.
- Failures (server not starting, auth errors, timeouts) are logged as failed rows, never raised.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import format_datetime
from pathlib import Path

import anyio

from . import config
from .database import DB_PATH, connect, to_iso_utc
from .dedup import folder_rank

log = logging.getLogger(__name__)

REPLIES_DIR = config.OUTPUT_DIR / "replies"
SEND_LOG_PATH = config.OUTPUT_DIR / "send_log.csv"
MCP_CONFIG_PATH = config.PROJECT_ROOT / "mcp_config.json"
ENV_PATH = config.PROJECT_ROOT / ".env"
LIVE_RECIPIENT_VAR = "NOTIFY_LIVE_TO"
DEFAULT_LIVE_LIMIT = 5
MAX_LIVE_LIMIT = 50
SEND_TIMEOUT_SECONDS = 60
STARTUP_TIMEOUT_SECONDS = 120  # first npx run downloads the server package

# Pinned server (TASK_4 D3): GongRzhe Gmail MCP 1.1.11, keys/token in ~/.gmail-mcp/
DEFAULT_SERVER = {"command": "npx", "args": ["-y", "@gongrzhe/server-gmail-autoauth-mcp@1.1.11"]}
SERVER_NAME = "gmail"
SEND_TOOL = "send_email"
SUCCESS_PREFIX = "Email sent successfully"  # the server reports errors as plain text, without isError

SEND_LOG_COLUMNS = ("timestamp", "recipient", "subject", "status", "error", "intended_recipient", "flagged_message_id")

SUBJECT_TEMPLATE = "[Duplicate Notice] Re: {original_subject}"
BODY_TEMPLATE = (
    "This is an automated notification from the Email Deduplication System.\n"
    "\n"
    "Your email has been identified as a potential duplicate:\n"
    "\n"
    "Your Email (Flagged):\n"
    "Message-ID: {flagged_message_id}\n"
    "Date Sent: {flagged_date}\n"
    "Subject: {flagged_subject}\n"
    "\n"
    "Original Email on Record:\n"
    "Message-ID: {original_message_id}\n"
    "Date Sent: {original_date}\n"
    "\n"
    "Similarity Score: {similarity}%\n"
    "\n"
    "If this was NOT a duplicate and you intended to send this email,\n"
    "please reply with CONFIRM to restore it to active status.\n"
    "\n"
    "No action is required if this is indeed a duplicate.\n"
)

_EML_POLICY = default_policy.clone(max_line_length=None, linesep="\n")  # no header folding
_ADDRESS = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


@dataclass
class FlaggedEmail:
    id: int
    message_id: str
    date: str
    from_address: str
    subject: str
    source_file: str
    similarity: float
    notification_sent: int
    original_message_id: str
    original_date: str
    original_subject: str
    original_source_file: str

    @property
    def sort_key(self) -> tuple:
        return (self.date, folder_rank(self.source_file), self.source_file)

    @property
    def original_sort_key(self) -> tuple:
        return (self.original_date, folder_rank(self.original_source_file), self.original_source_file)


@dataclass
class Notification:
    flagged: FlaggedEmail
    to: str           # intended recipient: the sender of the flagged email
    subject: str
    date: str         # RFC 2822, generation time
    references: str   # message_id of the flagged email
    body: str


# ------------------------------------------------------------------ building notifications

def rfc2822(iso_utc: str | datetime) -> str:
    """'2000-07-26T10:46:00Z' or an aware datetime -> 'Wed, 26 Jul 2000 10:46:00 +0000'."""
    dt = iso_utc if isinstance(iso_utc, datetime) else datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return format_datetime(dt.astimezone(timezone.utc))


def _one_line(value: str) -> str:
    """Header safety: a stored subject never contains line breaks, but never trust it."""
    return re.sub(r"[\r\n]+", " ", value)


def build_notification(flagged: FlaggedEmail, now: datetime) -> Notification:
    body = BODY_TEMPLATE.format(
        flagged_message_id=flagged.message_id,
        flagged_date=rfc2822(flagged.date),
        flagged_subject=_one_line(flagged.subject),
        original_message_id=flagged.original_message_id,
        original_date=rfc2822(flagged.original_date),
        similarity=f"{flagged.similarity:.2f}",
    )
    return Notification(
        flagged=flagged,
        to=flagged.from_address,
        subject=SUBJECT_TEMPLATE.format(original_subject=_one_line(flagged.original_subject)),
        date=rfc2822(now),
        references=flagged.message_id,
        body=body,
    )


def to_eml(note: Notification) -> bytes:
    msg = EmailMessage(policy=_EML_POLICY)
    msg["To"] = note.to
    msg["Subject"] = note.subject
    msg["Date"] = note.date
    msg["References"] = note.references
    msg.set_content(note.body, charset="utf-8", cte="7bit" if note.body.isascii() else "8bit")
    return msg.as_bytes()


def eml_filename(message_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@-]", "_", message_id.strip("<>")) + ".eml"


# ------------------------------------------------------------------ database access

def load_flagged(conn: sqlite3.Connection) -> list[FlaggedEmail]:
    rows = conn.execute(
        "SELECT d.id, d.message_id, d.date, d.from_address, d.subject, d.source_file, d.similarity_score, "
        "       d.notification_sent, o.message_id, o.date, o.subject, o.source_file "
        "FROM emails AS d JOIN emails AS o ON o.message_id = d.duplicate_of "
        "WHERE d.is_duplicate = 1"
    )
    return [FlaggedEmail(*row) for row in rows]


def latest_per_group(flagged: list[FlaggedEmail]) -> list[FlaggedEmail]:
    """The latest duplicate of every group, groups in report order (earliest original first)."""
    groups: dict[str, list[FlaggedEmail]] = defaultdict(list)
    for item in flagged:
        groups[item.original_message_id].append(item)
    latest = [max(members, key=lambda f: f.sort_key) for members in groups.values()]
    latest.sort(key=lambda f: f.original_sort_key)
    return latest


def mark_notified(conn: sqlite3.Connection, email_id: int, when: datetime) -> None:
    with conn:
        conn.execute(
            "UPDATE emails SET notification_sent = 1, notification_date = ? WHERE id = ?",
            (to_iso_utc(when), email_id),
        )


# ------------------------------------------------------------------ dry run

def write_drafts(flagged: list[FlaggedEmail], out_dir: Path = REPLIES_DIR, now: datetime | None = None) -> int:
    """One .eml per flagged duplicate. Stale drafts from earlier runs are removed first."""
    now = now or datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.eml"):
        old.unlink()
    for item in flagged:
        (out_dir / eml_filename(item.message_id)).write_bytes(to_eml(build_notification(item, now)))
    return len(flagged)


# ------------------------------------------------------------------ live mode config

def read_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    return values


def live_recipient(env_path: Path = ENV_PATH) -> str | None:
    return os.environ.get(LIVE_RECIPIENT_VAR) or read_env_file(env_path).get(LIVE_RECIPIENT_VAR)


def check_live_recipient(conn: sqlite3.Connection, recipient: str | None) -> str | None:
    """Return an error message if the live recipient is missing or unsafe, else None."""
    if not recipient:
        return f"{LIVE_RECIPIENT_VAR} is not set (environment or .env). Live mail only goes to your own inbox."
    address = recipient.strip().lower()
    if not _ADDRESS.match(address):
        return f"{LIVE_RECIPIENT_VAR}={recipient!r} is not an email address."
    if address.endswith("@enron.com"):
        return f"{LIVE_RECIPIENT_VAR} must not be an @enron.com address."
    in_data = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM addresses WHERE address = ?) "
        "    OR EXISTS (SELECT 1 FROM emails WHERE from_address = ?)",
        (address, address),
    ).fetchone()[0]
    if in_data:
        return f"{LIVE_RECIPIENT_VAR} is an address from the Enron dataset; refusing to send there."
    return None


def server_params(config_path: Path = MCP_CONFIG_PATH):
    """MCP server launch settings from mcp_config.json (mcpServers.gmail), else the pinned default."""
    from mcp import StdioServerParameters

    entry = DEFAULT_SERVER
    if config_path.exists():
        entry = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"][SERVER_NAME]
    return StdioServerParameters(command=entry["command"], args=entry.get("args", []), env=entry.get("env") or None)


# ------------------------------------------------------------------ live sending over MCP

@dataclass
class SendResult:
    note: Notification
    recipient: str
    ok: bool
    detail: str  # server reply on success, error text on failure
    timestamp: datetime


def _result_text(result) -> str:
    parts = [getattr(item, "text", "") for item in (getattr(result, "content", None) or [])]
    return " ".join(p for p in parts if p).strip()


async def send_via_mcp(notes: list[Notification], recipient: str, params, on_result, errlog_path: Path) -> None:
    """Send each note with the MCP send_email tool; call ``on_result(SendResult)`` after each one."""
    from mcp import ClientSession, stdio_client

    def fail_all(remaining: list[Notification], error: str) -> None:
        for note in remaining:
            on_result(SendResult(note, recipient, False, error, datetime.now(timezone.utc)))

    pending = list(notes)
    errlog_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with errlog_path.open("a", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    with anyio.fail_after(STARTUP_TIMEOUT_SECONDS):
                        await session.initialize()
                        tools = await session.list_tools()
                    if SEND_TOOL not in {tool.name for tool in tools.tools}:
                        fail_all(pending, f"MCP server does not offer a {SEND_TOOL} tool")
                        return
                    while pending:
                        note = pending.pop(0)
                        try:
                            with anyio.fail_after(SEND_TIMEOUT_SECONDS):
                                result = await session.call_tool(SEND_TOOL, {
                                    "to": [recipient],
                                    "subject": note.subject,
                                    "body": note.body,
                                    "inReplyTo": note.references,  # server sets In-Reply-To and References
                                })
                            text = _result_text(result)
                            ok = not getattr(result, "is_error", False) and text.startswith(SUCCESS_PREFIX)
                            on_result(SendResult(note, recipient, ok, text or "empty response", datetime.now(timezone.utc)))
                        except Exception as exc:  # timeout, server crash: log and keep going
                            on_result(SendResult(note, recipient, False, f"{type(exc).__name__}: {exc}",
                                                 datetime.now(timezone.utc)))
    except Exception as exc:  # server failed to start or the handshake failed
        fail_all(pending, f"MCP server unavailable: {type(exc).__name__}: {exc}")


def append_send_log(path: Path, result: SendResult) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        if new:
            writer.writerow(SEND_LOG_COLUMNS)
        writer.writerow((
            to_iso_utc(result.timestamp), result.recipient, result.note.subject,
            "sent" if result.ok else "failed", "" if result.ok else result.detail,
            result.note.to, result.note.flagged.message_id,
        ))


def run_live(
    conn: sqlite3.Connection,
    flagged: list[FlaggedEmail],
    limit: int,
    recipient: str | None,
    log_path: Path = SEND_LOG_PATH,
    params=None,
    sender=send_via_mcp,
) -> dict:
    """Send up to ``limit`` group notifications. Returns a summary; never raises on send errors."""
    problem = check_live_recipient(conn, recipient)
    if problem:
        log.error("Live send refused: %s", problem)
        return {"refused": problem, "attempted": 0, "sent": 0, "failed": 0}
    limit = max(1, min(limit, MAX_LIVE_LIMIT))
    pending = [f for f in latest_per_group(flagged) if not f.notification_sent][:limit]
    if not pending:
        log.info("Live send: every duplicate group has already been notified")
        return {"refused": None, "attempted": 0, "sent": 0, "failed": 0}

    now = datetime.now(timezone.utc)
    notes = [build_notification(f, now) for f in pending]
    counts = {"sent": 0, "failed": 0}

    def on_result(result: SendResult) -> None:
        if result.ok:
            mark_notified(conn, result.note.flagged.id, result.timestamp)
            counts["sent"] += 1
            log.info("Sent notice for %s to %s (intended %s): %s", result.note.flagged.message_id,
                     result.recipient, result.note.to, result.detail)
        else:
            counts["failed"] += 1
            log.error("Send failed for %s: %s", result.note.flagged.message_id, result.detail)
        append_send_log(log_path, result)

    log.info("Live send: %d notification(s) to %s via MCP %s", len(notes), recipient, SEND_TOOL)
    anyio.run(sender, notes, recipient.strip(), params or server_params(), on_result,
              config.OUTPUT_DIR / "mcp_server.log")
    return {"refused": None, "attempted": len(notes), **counts}


# ------------------------------------------------------------------ entry point

def run_notifications(
    send_live: bool = False,
    limit: int = DEFAULT_LIVE_LIMIT,
    db_path: Path = DB_PATH,
    replies_dir: Path = REPLIES_DIR,
    log_path: Path = SEND_LOG_PATH,
) -> dict:
    conn = connect(db_path)
    try:
        flagged = load_flagged(conn)
        drafts = write_drafts(flagged, replies_dir)
        groups = len({f.original_message_id for f in flagged})
        summary = {"drafts": drafts, "groups": groups, "live": None}
        if send_live:
            summary["live"] = run_live(conn, flagged, limit, live_recipient(), log_path)
    finally:
        conn.close()
    print("\n=== Notifications ===")
    print(f"Draft .eml files      : {drafts} in {replies_dir}")
    print(f"Duplicate groups      : {groups} (live mode sends one notice per group, about its latest duplicate)")
    live = summary["live"]
    if live is None:
        print("Live sending          : off (dry run). Use --send-live to send through the Gmail MCP server.")
    elif live["refused"]:
        print(f"Live sending          : refused. {live['refused']}")
    else:
        print(f"Live sending          : attempted {live['attempted']}, sent {live['sent']}, failed {live['failed']}"
              f" (log: {log_path})")
    return summary
