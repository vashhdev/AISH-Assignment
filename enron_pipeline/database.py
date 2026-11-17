"""Task 2: create the SQLite database from schema.sql and load parsed email records.

Loading is idempotent: an email whose message_id is already stored is skipped
(``ON CONFLICT (message_id) DO NOTHING``), so re-running the pipeline adds no rows and
keeps the duplicate and notification state written by later stages. Only the
message_id conflict is swallowed; any other constraint failure is a real bug and raises.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import config
from .parser import EmailRecord

log = logging.getLogger(__name__)

SCHEMA_PATH = config.PROJECT_ROOT / "schema.sql"
DB_PATH = config.OUTPUT_DIR / "enron.db"
STATS_PATH = config.OUTPUT_DIR / "db_stats.json"

_EMAIL_COLUMNS = (
    "message_id", "date", "from_address", "subject", "body", "source_file",
    "x_from", "x_to", "x_cc", "x_bcc", "x_folder", "x_origin", "content_type",
    "has_attachment", "forwarded_content", "quoted_content", "headings",
)
_INSERT_EMAIL = (
    f"INSERT INTO emails ({', '.join(_EMAIL_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_EMAIL_COLUMNS))}) "
    "ON CONFLICT (message_id) DO NOTHING"
)
_INSERT_RECIPIENT = "INSERT INTO email_recipients (email_id, address_id, kind, position) VALUES (?, ?, ?, ?)"


@dataclass
class LoadStats:
    records_in: int = 0
    inserted: int = 0
    already_in_db: int = 0            # message_id stored by an earlier run
    exact_duplicates: int = 0         # same message_id seen twice in this batch
    recipient_rows: int = 0
    new_addresses: int = 0
    totals: dict = field(default_factory=dict)  # row counts per table after the load
    exact_duplicate_examples: list = field(default_factory=list)  # (message_id, source_file), capped


def to_iso_utc(dt: datetime) -> str:
    """Aware datetime -> '2001-05-14T23:39:00Z'."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def _email_row(rec: EmailRecord) -> tuple:
    values = {name: getattr(rec, name) for name in _EMAIL_COLUMNS}
    values["date"] = to_iso_utc(rec.date)
    values["has_attachment"] = int(rec.has_attachment)
    return tuple(values[name] for name in _EMAIL_COLUMNS)


def _address_id(conn: sqlite3.Connection, cache: dict[str, int], address: str) -> int:
    address_id = cache.get(address)
    if address_id is None:
        address_id = conn.execute("INSERT INTO addresses (address) VALUES (?)", (address,)).lastrowid
        cache[address] = address_id
    return address_id


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("emails", "addresses", "email_recipients")
    }


def load_records(conn: sqlite3.Connection, records: Iterable[EmailRecord]) -> LoadStats:
    """Insert records and their recipients in one transaction."""
    stats = LoadStats()
    address_ids: dict[str, int] = dict(conn.execute("SELECT address, id FROM addresses"))
    addresses_before = len(address_ids)
    seen: set[str] = set()
    with conn:
        for rec in records:
            stats.records_in += 1
            if rec.message_id in seen:
                stats.exact_duplicates += 1
                if len(stats.exact_duplicate_examples) < 50:
                    stats.exact_duplicate_examples.append((rec.message_id, rec.source_file))
                log.debug("Exact duplicate message_id %s in %s", rec.message_id, rec.source_file)
                continue
            seen.add(rec.message_id)
            cur = conn.execute(_INSERT_EMAIL, _email_row(rec))
            if cur.rowcount == 0:
                stats.already_in_db += 1
                continue
            stats.inserted += 1
            email_id = cur.lastrowid
            rows = [
                (email_id, _address_id(conn, address_ids, address), kind, position)
                for kind, addresses in (("to", rec.to_addresses), ("cc", rec.cc_addresses), ("bcc", rec.bcc_addresses))
                for position, address in enumerate(addresses)
            ]
            conn.executemany(_INSERT_RECIPIENT, rows)
            stats.recipient_rows += len(rows)
    stats.new_addresses = len(address_ids) - addresses_before
    stats.totals = table_counts(conn)
    return stats


def print_load_stats(stats: LoadStats, db_path: Path | str) -> None:
    print("\n=== Database load ===")
    print(f"Database           : {db_path}")
    print(f"Records offered    : {stats.records_in}")
    print(f"Inserted           : {stats.inserted}")
    print(f"Already in DB      : {stats.already_in_db}  (loaded by an earlier run, left untouched)")
    print(f"Exact duplicates   : {stats.exact_duplicates}  (same message_id twice in this batch, skipped)")
    print(f"Recipient rows     : {stats.recipient_rows}   New addresses: {stats.new_addresses}")
    print("Table totals       : " + ", ".join(f"{t} {n}" for t, n in stats.totals.items()))


def run_database(
    records: list[EmailRecord],
    db_path: Path = DB_PATH,
    schema_path: Path = SCHEMA_PATH,
    stats_path: Path = STATS_PATH,
    reset: bool = False,
) -> LoadStats:
    """Create the database if needed and load ``records``. ``reset`` deletes it first."""
    if reset and db_path.exists():
        log.warning("Deleting %s: duplicate flags and notification history are reset", db_path)
        db_path.unlink()
    conn = connect(db_path)
    try:
        init_schema(conn, schema_path)
        stats = load_records(conn, records)
    finally:
        conn.close()
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": to_iso_utc(datetime.now(timezone.utc)), **asdict(stats)}
    stats_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    print_load_stats(stats, db_path)
    return stats
