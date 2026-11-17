"""Single entry point for the Enron email pipeline.

    python main.py

Stages: dataset (download + extract chosen mailboxes) -> Task 1 extraction.
Later stages (database, duplicate detection, notifications) are added as they are built.
"""
from __future__ import annotations

import argparse
import logging
import sys

from enron_pipeline.dataset import ensure_dataset
from enron_pipeline.extract import run_extraction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enron email extraction and deduplication pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_dataset()
    run_extraction()
    return 0


if __name__ == "__main__":
    sys.exit(main())
