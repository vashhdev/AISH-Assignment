"""Task 2 tests: schema, normalized recipients, idempotent load, indexes, sample queries."""
import sqlite3

import pytest

from enron_pipeline.database import connect, init_schema, load_records
from enron_pipeline.parser import parse_bytes
from enron_pipeline.queries import QUERIES_PATH, split_queries
from tests.test_parser import HEADERS, make


def record(message_id: str, to: str, cc: str = "", source: str = "maildir/test/inbox/1"):
    headers = HEADERS.replace("<1.2.JavaMail.evans@thyme>", message_id)
    extra = f"Cc: {cc}\nBcc: {cc}\n" if cc else ""
    headers = headers.replace("To: keith.holst@enron.com\n", f"To: {to}\n{extra}")
    return parse_bytes(make(headers), source)


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def records():
    return [
        record("<a@x>", "keith.holst@enron.com, jane.doe@enron.com", cc="boss@enron.com", source="maildir/t/inbox/1"),
        record("<b@x>", "Keith.Holst@enron.com", source="maildir/t/inbox/2"),
        record("<a@x>", "someone@enron.com", source="maildir/t/inbox/3"),  # exact duplicate message_id
    ]


def test_schema_is_rerunnable(conn):
    init_schema(conn)  # second run must not fail
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    assert {"emails", "addresses", "email_recipients", "recipients"} <= tables


def test_recipients_are_normalized(conn, records):
    stats = load_records(conn, records)
    assert (stats.inserted, stats.exact_duplicates) == (2, 1)
    assert stats.exact_duplicate_examples == [("<a@x>", "maildir/t/inbox/3")]
    # no address-list columns on emails
    email_columns = {r[1] for r in conn.execute("PRAGMA table_info(emails)")}
    assert not email_columns & {"to_addresses", "cc_addresses", "bcc_addresses", "to", "cc", "bcc"}
    # keith.holst appears in both emails but is stored once (case-normalized by the parser)
    assert conn.execute("SELECT COUNT(*) FROM addresses WHERE address = 'keith.holst@enron.com'").fetchone()[0] == 1
    rows = conn.execute(
        "SELECT r.kind, r.position, r.address FROM recipients r JOIN emails e ON e.id = r.email_id "
        "WHERE e.message_id = '<a@x>' ORDER BY r.kind DESC, r.position"
    ).fetchall()
    assert rows == [
        ("to", 0, "keith.holst@enron.com"), ("to", 1, "jane.doe@enron.com"),
        ("cc", 0, "boss@enron.com"), ("bcc", 0, "boss@enron.com"),
    ]


def test_reload_adds_nothing_and_keeps_state(conn, records):
    load_records(conn, records)
    with conn:
        conn.execute(
            "UPDATE emails SET notification_sent = 1, notification_date = '2026-11-16T00:00:00Z' "
            "WHERE message_id = '<a@x>'"
        )
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("emails", "addresses", "email_recipients")}
    stats = load_records(conn, records)
    assert (stats.inserted, stats.already_in_db, stats.recipient_rows, stats.new_addresses) == (0, 2, 0, 0)
    assert stats.totals == before
    assert conn.execute("SELECT notification_sent FROM emails WHERE message_id = '<a@x>'").fetchone()[0] == 1


def test_message_id_unique_constraint(conn, records):
    load_records(conn, records[:1])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO emails (message_id, date, from_address, source_file) "
            "VALUES ('<a@x>', '2001-01-01T00:00:00Z', 'x@enron.com', 'other')"
        )


def test_required_indexes_exist(conn):
    indexed = set()
    for _, name, *_ in conn.execute("PRAGMA index_list(emails)"):
        indexed |= {r[2] for r in conn.execute(f"PRAGMA index_info({name})")}
    assert {"date", "from_address", "subject", "message_id"} <= indexed


def test_state_columns_and_defaults(conn, records):
    load_records(conn, records[:1])
    info = {r[1]: (r[2], r[4]) for r in conn.execute("PRAGMA table_info(emails)")}
    assert info["is_duplicate"] == ("INTEGER", "0")
    assert info["notification_sent"] == ("INTEGER", "0")
    assert info["duplicate_of"][1] is None and info["notification_date"][1] is None
    row = conn.execute(
        "SELECT date, is_duplicate, duplicate_of, notification_sent, notification_date FROM emails"
    ).fetchone()
    assert row == ("2000-10-09T14:16:00Z", 0, None, 0, None)
    with pytest.raises(sqlite3.IntegrityError):  # duplicate_of only allowed on a flagged duplicate
        conn.execute("UPDATE emails SET duplicate_of = '<a@x>'")


def test_sample_queries_all_run(conn, records):
    load_records(conn, records)
    queries = split_queries(QUERIES_PATH.read_text(encoding="utf-8"))
    assert len(queries) >= 3
    for comments, sql in queries:
        assert any(line.startswith("Expected output") for line in comments), sql[:60]
        conn.execute(sql).fetchall()
