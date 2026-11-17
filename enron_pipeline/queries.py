"""Run every query in sample_queries.sql against the database and print the results.

    python -m enron_pipeline.queries [--db output/enron.db] [--rows 15]

Each query's leading comment block (title + expected output) is printed above its result,
so the expected and actual output can be compared side by side.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from . import config
from .database import DB_PATH

QUERIES_PATH = config.PROJECT_ROOT / "sample_queries.sql"


def split_queries(sql_text: str) -> list[tuple[list[str], str]]:
    """Split a .sql file into (comment lines, statement) pairs.

    Comments directly above a statement belong to it; the file header (the comment
    block before the first blank line that precedes a query) is dropped.
    """
    queries: list[tuple[list[str], str]] = []
    comments: list[str] = []
    statement: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not statement:
            if not stripped:
                comments = []  # a blank line separates a comment block from the next query
                continue
            if stripped.startswith("--"):
                comments.append(stripped[2:].strip())
                continue
        statement.append(line)
        text = "\n".join(statement)
        if sqlite3.complete_statement(text):
            queries.append((comments, text.strip()))
            comments, statement = [], []
    return queries


def _format_table(columns: list[str], rows: list[tuple], width: int = 60) -> str:
    cells = [[("NULL" if v is None else str(v))[:width] for v in row] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(columns, widths))]
    lines.append("  ".join("-" * w for w in widths))
    lines += ["  ".join(v.ljust(w) for v, w in zip(row, widths)) for row in cells]
    return "\n".join(lines)


def run_queries(db_path: Path = DB_PATH, queries_path: Path = QUERIES_PATH, max_rows: int = 15) -> int:
    if not Path(db_path).exists():
        print(f"Database not found: {db_path}. Run `python main.py` first.", file=sys.stderr)
        return 1
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        for comments, sql in split_queries(queries_path.read_text(encoding="utf-8")):
            print("\n" + "=" * 100)
            print("\n".join(comments))
            print("-" * 100)
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            print(_format_table(columns, rows[:max_rows]))
            more = f", first {max_rows} shown" if len(rows) > max_rows else ""
            print(f"({len(rows)} rows{more})")
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--rows", type=int, default=15, help="max rows printed per query")
    args = parser.parse_args(argv)
    return run_queries(args.db, max_rows=args.rows)


if __name__ == "__main__":
    sys.exit(main())
