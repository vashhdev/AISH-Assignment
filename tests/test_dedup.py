"""Task 3 tests: subject normalization, text choice, tie-break, clustering, flags, report, reruns."""
import csv
from datetime import datetime, timedelta, timezone

import pytest
from rapidfuzz import fuzz

from enron_pipeline.database import connect, init_schema, load_records
from enron_pipeline.dedup import comparison_text, folder_rank, normalize_subject, run_dedup
from enron_pipeline.parser import EmailRecord

BASE = "Please review the attached gas trading report for the west desk before Friday."
CLOSE = "Please review the attached gas trading report for the west desk by Friday noon."
NEAR_MISS = "Please read the attached gas trading summary for the west desk before Friday."
T0 = datetime(2001, 5, 1, 9, 0, tzinfo=timezone.utc)
T1, T2 = T0 + timedelta(days=1), T0 + timedelta(days=2)


def rec(key, source, date, body=BASE, subject="Gas report", sender="phillip.allen@enron.com", forwarded=None):
    return EmailRecord(
        message_id=f"<{key}@test>", date=date, from_address=sender, to_addresses=["keith.holst@enron.com"],
        subject=subject, body=body, source_file=source, forwarded_content=forwarded,
    )


SCENARIO = [
    rec("a", "maildir/allen-p/all_documents/1", T0),                       # view copy, same time as b
    rec("b", "maildir/allen-p/sent/1", T0),                                # original: sent folder wins the tie
    rec("c", "maildir/allen-p/inbox/1", T1, body=CLOSE, subject="Re: Gas report"),
    rec("d", "maildir/allen-p/deleted_items/1", T2, subject="FW: RE: gas  REPORT"),  # latest duplicate
    rec("e", "maildir/allen-p/sent/2", T2 + timedelta(hours=1), body=NEAR_MISS),     # 89% -> not a duplicate
    rec("f", "maildir/arnold-j/sent/1", T1, sender="john.arnold@enron.com"),         # other sender
    rec("g", "maildir/allen-p/sent/3", T0, body="", subject="FW: Deal sheet", forwarded="Q3 volumes by region and desk"),
    rec("h", "maildir/allen-p/sent/4", T1, body="", subject="FW: Deal sheet", forwarded="Office party moved to Thursday"),
    rec("i", "maildir/allen-p/sent/5", T0, body="", subject="Fwd: Credit memo", forwarded="Counterparty limits attached"),
    rec("j", "maildir/allen-p/inbox/5", T1, body="", subject="Fwd: Credit memo", forwarded="Counterparty limits attached"),
]


def test_fixture_scores_are_where_we_think():
    assert 90 <= fuzz.ratio(BASE, CLOSE) < 100
    assert 85 <= fuzz.ratio(BASE, NEAR_MISS) < 90


@pytest.mark.parametrize("subject, expected", [
    ("Re: RE: Fwd: FW: Fw:  Gas   Report ", "gas report"),
    ("re[2]: Gas report", "gas report"),
    ("Fwd : Gas report", "gas report"),
    ("Re:", ""),
    ("", ""),
    ("Regarding: gas", "regarding: gas"),        # not a prefix
    ("Gas report re: prices", "gas report re: prices"),  # only leading prefixes are stripped
])
def test_normalize_subject(subject, expected):
    assert normalize_subject(subject) == expected


def test_comparison_text_falls_back_to_full_text():
    assert comparison_text("  own \n text ", "forwarded", "quoted") == "own text"
    assert comparison_text("", "forwarded  part", "quoted") == "forwarded part quoted"
    assert comparison_text(None, None, None) == ""


def test_folder_rank_order():
    ranks = [folder_rank(f"maildir/x/{folder}/1") for folder in
             ("sent", "_sent_mail", "inbox", "_americas", "all_documents", "deleted_items")]
    assert ranks == sorted(ranks) and ranks[0] < ranks[2] < ranks[3] < ranks[4] < ranks[5]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    init_schema(conn)
    load_records(conn, SCENARIO)
    conn.close()
    return path


def _run(db, tmp_path):
    return run_dedup(db_path=db, report_path=tmp_path / "report.csv", stats_path=tmp_path / "stats.json")


def _flags(db):
    conn = connect(db)
    try:
        return {
            mid: (dup, of, score) for mid, dup, of, score in conn.execute(
                "SELECT message_id, is_duplicate, duplicate_of, similarity_score FROM emails ORDER BY message_id")
        }
    finally:
        conn.close()


def test_groups_flags_and_scores(db, tmp_path):
    groups, stats = _run(db, tmp_path)
    flags = _flags(db)
    flagged = {mid for mid, (dup, _, _) in flags.items() if dup}
    assert flagged == {"<a@test>", "<c@test>", "<d@test>", "<j@test>"}
    assert {mid: flags[mid][1] for mid in flagged} == {
        "<a@test>": "<b@test>", "<c@test>": "<b@test>", "<d@test>": "<b@test>", "<j@test>": "<i@test>",
    }
    assert flags["<a@test>"][2] == 100 and 90 <= flags["<c@test>"][2] < 100
    # every group: exactly one unflagged original
    for group in groups:
        assert flags[group.original.message_id][0] == 0
    assert groups[0].latest.message_id == "<d@test>"
    assert (stats["groups"], stats["flagged"], stats["average_group_size"]) == (2, 4, 3.0)


def test_report_columns_and_rows(db, tmp_path):
    _run(db, tmp_path)
    with (tmp_path / "report.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == [
        "duplicate_message_id", "original_message_id", "subject", "from_address",
        "duplicate_date", "original_date", "similarity_score",
    ]
    assert len(rows) == 1 + 4
    assert rows[1][:2] == ["<a@test>", "<b@test>"] and rows[1][4] == rows[1][5] == "2001-05-01T09:00:00Z"


def test_rerun_is_idempotent_and_keeps_notification_state(db, tmp_path):
    _run(db, tmp_path)
    first_flags, first_report = _flags(db), (tmp_path / "report.csv").read_bytes()
    conn = connect(db)
    with conn:  # stale flag from an imagined earlier run + a sent notification
        conn.execute("UPDATE emails SET is_duplicate = 1, duplicate_of = '<b@test>' WHERE message_id = '<e@test>'")
        conn.execute("UPDATE emails SET notification_sent = 1, notification_date = '2026-11-16T00:00:00Z' "
                     "WHERE message_id = '<d@test>'")
    conn.close()
    _run(db, tmp_path)
    assert _flags(db) == first_flags
    assert (tmp_path / "report.csv").read_bytes() == first_report
    conn = connect(db)
    assert conn.execute("SELECT notification_sent FROM emails WHERE message_id = '<d@test>'").fetchone()[0] == 1
    conn.close()
