"""Task 4 tests: template exactness, .eml drafts, group selection, live-send safety and the MCP client."""
import csv
import email
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from mcp import StdioServerParameters

from enron_pipeline.database import connect, init_schema, load_records
from enron_pipeline.dedup import run_dedup
from enron_pipeline.notify import (
    FlaggedEmail, build_notification, check_live_recipient, eml_filename, latest_per_group, load_flagged,
    run_live, to_eml, write_drafts,
)
from tests.test_dedup import SCENARIO

NOW = datetime(2026, 11, 17, 4, 30, tzinfo=timezone.utc)
LIVE_TO = "notify-test@example.org"
FAKE_SERVER = Path(__file__).with_name("fake_gmail_mcp.py")

FLAGGED = FlaggedEmail(
    id=7, message_id="<15240164.1075855689768.JavaMail.evans@thyme>", date="2000-07-26T10:46:00Z",
    from_address="phillip.allen@enron.com", subject="Re: New Notice from Transwestern Pipeline Co.",
    source_file="maildir/allen-p/all_documents/1", similarity=92.857, notification_sent=0,
    original_message_id="<10221129.1075855690113.JavaMail.evans@thyme>", original_date="2000-07-11T09:12:00Z",
    original_subject="Re: New Notice from Transwestern Pipeline Co.", original_source_file="maildir/allen-p/sent/1",
)

EXPECTED_BODY = """This is an automated notification from the Email Deduplication System.

Your email has been identified as a potential duplicate:

Your Email (Flagged):
Message-ID: <15240164.1075855689768.JavaMail.evans@thyme>
Date Sent: Wed, 26 Jul 2000 10:46:00 +0000
Subject: Re: New Notice from Transwestern Pipeline Co.

Original Email on Record:
Message-ID: <10221129.1075855690113.JavaMail.evans@thyme>
Date Sent: Tue, 11 Jul 2000 09:12:00 +0000

Similarity Score: 92.86%

If this was NOT a duplicate and you intended to send this email,
please reply with CONFIRM to restore it to active status.

No action is required if this is indeed a duplicate.
"""


def test_notification_follows_template_exactly():
    note = build_notification(FLAGGED, NOW)
    assert note.to == "phillip.allen@enron.com"
    assert note.subject == "[Duplicate Notice] Re: Re: New Notice from Transwestern Pipeline Co."  # literal template
    assert note.date == "Tue, 17 Nov 2026 04:30:00 +0000"
    assert note.references == "<15240164.1075855689768.JavaMail.evans@thyme>"  # not double-wrapped
    assert note.body == EXPECTED_BODY


def test_eml_has_template_headers_unfolded():
    raw = to_eml(build_notification(FLAGGED, NOW))
    text = raw.decode("utf-8")
    assert "Subject: [Duplicate Notice] Re: Re: New Notice from Transwestern Pipeline Co.\n" in text  # one line
    assert text.index("To:") < text.index("Subject:") < text.index("Date:") < text.index("References:")
    msg = email.message_from_bytes(raw)
    assert msg["To"] == "phillip.allen@enron.com"
    assert msg["References"] == "<15240164.1075855689768.JavaMail.evans@thyme>"
    assert msg.get_payload(decode=True).decode("utf-8") == EXPECTED_BODY
    assert eml_filename(FLAGGED.message_id) == "15240164.1075855689768.JavaMail.evans@thyme.eml"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    init_schema(conn)
    load_records(conn, SCENARIO)
    conn.close()
    run_dedup(db_path=path, report_path=tmp_path / "r.csv", stats_path=tmp_path / "s.json")
    return path


def _flagged(db):
    conn = connect(db)
    try:
        return load_flagged(conn)
    finally:
        conn.close()


def test_drafts_one_per_flagged_and_stale_removed(db, tmp_path):
    out = tmp_path / "replies"
    out.mkdir()
    (out / "stale.eml").write_text("old")
    assert write_drafts(_flagged(db), out, NOW) == 4
    assert sorted(p.name for p in out.iterdir()) == ["a@test.eml", "c@test.eml", "d@test.eml", "j@test.eml"]


def test_latest_per_group_in_report_order(db):
    latest = latest_per_group(_flagged(db))
    assert [f.message_id for f in latest] == ["<d@test>", "<j@test>"]


@pytest.mark.parametrize("recipient, ok", [
    (None, False), ("", False), ("not-an-address", False), ("someone@enron.com", False),
    ("keith.holst@enron.com", False), ("PHILLIP.ALLEN@ENRON.COM", False), (LIVE_TO, True),
])
def test_live_recipient_guard(db, recipient, ok):
    conn = connect(db)
    try:
        assert (check_live_recipient(conn, recipient) is None) == ok
    finally:
        conn.close()


def _fake_params(tmp_path, fail_on=""):
    return StdioServerParameters(
        command=sys.executable, args=[str(FAKE_SERVER)],
        env={"FAKE_GMAIL_CALLS": str(tmp_path / "calls.jsonl"), "FAKE_GMAIL_FAIL_ON": fail_on},
    )


def _log_rows(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _notified(db):
    conn = connect(db)
    try:
        return dict(conn.execute("SELECT message_id, notification_sent FROM emails WHERE notification_sent = 1"))
    finally:
        conn.close()


def test_live_send_over_mcp_marks_only_successes(db, tmp_path):
    log_path = tmp_path / "send_log.csv"
    conn = connect(db)
    try:
        summary = run_live(conn, load_flagged(conn), 5, LIVE_TO, log_path, _fake_params(tmp_path, "Credit memo"))
    finally:
        conn.close()
    assert (summary["attempted"], summary["sent"], summary["failed"]) == (2, 1, 1)
    assert _notified(db) == {"<d@test>": 1}
    rows = _log_rows(log_path)
    assert list(rows[0])[:5] == ["timestamp", "recipient", "subject", "status", "error"]
    assert [(r["status"], r["recipient"], r["intended_recipient"]) for r in rows] == [
        ("sent", LIVE_TO, "phillip.allen@enron.com"), ("failed", LIVE_TO, "phillip.allen@enron.com"),
    ]
    assert rows[0]["error"] == "" and "simulated Gmail failure" in rows[1]["error"]
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert calls[0]["to"] == [LIVE_TO] and calls[0]["inReplyTo"] == "<d@test>"
    assert calls[0]["subject"] == "[Duplicate Notice] Re: Gas report"

    # rerun: the notified group is skipped, only the failed one is retried
    conn = connect(db)
    try:
        again = run_live(conn, load_flagged(conn), 5, LIVE_TO, log_path, _fake_params(tmp_path))
    finally:
        conn.close()
    assert (again["attempted"], again["sent"]) == (1, 1)
    assert set(_notified(db)) == {"<d@test>", "<j@test>"}


def test_live_limit_is_respected(db, tmp_path):
    conn = connect(db)
    try:
        summary = run_live(conn, load_flagged(conn), 1, LIVE_TO, tmp_path / "log.csv", _fake_params(tmp_path))
    finally:
        conn.close()
    assert summary["attempted"] == 1 and _notified(db) == {"<d@test>": 1}


def test_server_unavailable_is_logged_not_raised(db, tmp_path):
    params = StdioServerParameters(command=str(tmp_path / "no-such-server.exe"))
    conn = connect(db)
    try:
        summary = run_live(conn, load_flagged(conn), 5, LIVE_TO, tmp_path / "log.csv", params)
    finally:
        conn.close()
    assert (summary["sent"], summary["failed"]) == (0, 2)
    assert all("MCP server unavailable" in r["error"] for r in _log_rows(tmp_path / "log.csv"))
    assert _notified(db) == {}


def test_enron_recipient_refused_before_any_send(db, tmp_path):
    conn = connect(db)
    try:
        summary = run_live(conn, load_flagged(conn), 5, "keith.holst@enron.com", tmp_path / "log.csv",
                           _fake_params(tmp_path))
    finally:
        conn.close()
    assert summary["refused"] and summary["attempted"] == 0
    assert not (tmp_path / "log.csv").exists() and not (tmp_path / "calls.jsonl").exists()
