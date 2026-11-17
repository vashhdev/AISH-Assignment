"""Single entry point for the Enron email pipeline.

    python main.py              # dataset -> extraction -> database
    python main.py --reset-db   # rebuild the database from scratch

Stages: dataset (download + extract chosen mailboxes) -> Task 1 extraction -> Task 2 database load.
Later stages (duplicate detection, notifications) are added as they are built.
"""
from __future__ import annotations

import argparse
import logging
import sys

from enron_pipeline.database import run_database
from enron_pipeline.dataset import ensure_dataset
from enron_pipeline.extract import run_extraction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enron email extraction and deduplication pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument(
        "--reset-db", action="store_true",
        help="delete output/enron.db before loading (clears duplicate flags and notification history)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_dataset()
    extraction = run_extraction()
    run_database(extraction.records, reset=args.reset_db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
