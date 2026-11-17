"""Single entry point for the Enron email pipeline.

    python main.py                       # full run, dry run for notifications (writes .eml drafts)
    python main.py --send-live           # also send up to 5 group notifications via the Gmail MCP server
    python main.py --send-live --limit 2 # cap live sends for this run
    python main.py --reset-db            # rebuild the database from scratch

Stages: dataset (download + extract chosen mailboxes) -> Task 1 extraction -> Task 2 database load
-> Task 3 duplicate detection -> Task 4 notifications.
"""
from __future__ import annotations

import argparse
import logging
import sys

from enron_pipeline.database import run_database
from enron_pipeline.dataset import ensure_dataset
from enron_pipeline.dedup import run_dedup
from enron_pipeline.extract import run_extraction
from enron_pipeline.notify import DEFAULT_LIVE_LIMIT, MAX_LIVE_LIMIT, run_notifications


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enron email extraction, deduplication and notification pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument(
        "--reset-db", action="store_true",
        help="delete output/enron.db before loading (clears duplicate flags and notification history)",
    )
    parser.add_argument(
        "--send-live", action="store_true",
        help="send notifications through the Gmail MCP server (to NOTIFY_LIVE_TO only; default is dry run)",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIVE_LIMIT,
        help=f"max duplicate groups to notify in one live run (default {DEFAULT_LIVE_LIMIT}, max {MAX_LIVE_LIMIT})",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_LIVE_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_LIVE_LIMIT}")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_dataset()
    extraction = run_extraction()
    run_database(extraction.records, reset=args.reset_db)
    run_dedup()
    summary = run_notifications(send_live=args.send_live, limit=args.limit)
    live = summary["live"]
    return 1 if live and (live["refused"] or live["failed"]) else 0


if __name__ == "__main__":
    sys.exit(main())
