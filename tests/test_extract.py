"""End-to-end Task 1 run over a small temp maildir with broken files mixed in."""
import json

from enron_pipeline.extract import run_extraction
from tests.test_parser import HEADERS, make


def test_run_extraction_never_crashes_and_logs_failures(tmp_path):
    inbox = tmp_path / "maildir" / "test-a" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "1").write_bytes(make())
    (inbox / "2").write_bytes(b"")
    (inbox / "3").write_bytes(b"\x00\xff\xfe junk")
    (inbox / "4").write_bytes(make(HEADERS.replace("To: keith.holst@enron.com\n", "")))
    (tmp_path / "maildir" / ".extracted.json").write_text("{}")  # hidden marker is not an email

    error_log = tmp_path / "error_log.txt"
    stats_file = tmp_path / "out" / "stats.json"
    result = run_extraction(data_dir=tmp_path, error_log_path=error_log, stats_path=stats_file)

    assert len(result.records) == 1
    assert result.records[0].source_file == "maildir/test-a/inbox/1"
    assert {src for src, _ in result.failures} == {
        "maildir/test-a/inbox/2", "maildir/test-a/inbox/3", "maildir/test-a/inbox/4",
    }
    log_lines = [l for l in error_log.read_text().splitlines() if not l.startswith("#")]
    assert len(log_lines) == 3 and all("\t" in l for l in log_lines)
    stats = json.loads(stats_file.read_text())
    assert stats["total_files"] == 4 and stats["parsed"] == 1 and stats["failed"] == 3
    assert stats["field_completeness"]["message_id"]["rate"] == 1.0
