"""Task 3: detect duplicate emails, flag them in the database and write duplicates_report.csv.

Duplicate rule (from the brief): same from_address, same subject after stripping
Re:/Fw:/Fwd: prefixes, and body text that fuzzy-matches at >= 90%.

How groups are built:
1. Block: bucket emails by (from_address, normalized subject). Only emails in the same
   bucket can be duplicates, so fuzzy matching runs inside small buckets.
2. Order each bucket original-first by ``sort_key``: (date, folder rank, source_file).
3. Anchor clustering: walk the bucket in that order. Each email is compared with the
   original (first email) of every group already formed in the bucket and joins the group
   whose original it matches best at >= 90%. If none matches, it starts a new group.
   Comparing against the original rather than any member keeps every flagged email within
   90% of the record it is reported against (similarity is not transitive).
4. Flag every member except the original: is_duplicate = 1, duplicate_of = the original's
   message_id, similarity_score = score against the original. The last member in sort
   order is the latest email, the primary target for notification.

Text compared: the sender's own body, whitespace-normalized. When it is empty (a pure
forward or reply) the full text (body + forwarded + quoted) is used instead, so two
different forwards do not match just because neither has text of its own.

Similarity: ``rapidfuzz.fuzz.ratio`` (normalized Indel similarity, 0-100, word-order aware).

Tie-break for identical timestamps (96% of groups are the same email stored in several
folders): copies in real folders beat Lotus Notes auto-generated views and deleted items
(see ``folder_rank``), then source_file. Deterministic and independent of load order.

Re-running is idempotent: all duplicate flags are cleared, then recomputed.
"""
from __future__ import annotations

import csv
import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

from . import config
from .database import DB_PATH, connect, to_iso_utc

log = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 90.0
REPORT_PATH = config.PROJECT_ROOT / "duplicates_report.csv"
STATS_PATH = config.OUTPUT_DIR / "dedup_stats.json"
REPORT_COLUMNS = (
    "duplicate_message_id", "original_message_id", "subject", "from_address",
    "duplicate_date", "original_date", "similarity_score",
)

# Stacked, mixed-case reply/forward prefixes: "Re: FW: re[2]: Fwd :" ...
_SUBJECT_PREFIX = re.compile(r"^\s*(?:(?:re|fw|fwd)\s*(?:\[\d+\])?\s*:\s*)+", re.IGNORECASE)

# Folder priority when timestamps tie (lower wins = original). Top-level folder names.
_SENT_FOLDERS = {"sent", "_sent", "_sent_mail", "sent_items"}
_INBOX_FOLDERS = {"inbox", "notes_inbox"}
_VIEW_FOLDERS = {"all_documents", "discussion_threads"}  # Lotus Notes views that copy other folders
_TRASH_FOLDERS = {"deleted_items"}


def normalize_subject(subject: str) -> str:
    """Strip Re:/Fw:/Fwd: prefixes (stacked, any case), collapse whitespace, casefold."""
    return " ".join(_SUBJECT_PREFIX.sub("", subject or "").split()).casefold()


def normalize_text(text: str | None) -> str:
    return " ".join((text or "").split())


def comparison_text(body: str | None, forwarded: str | None, quoted: str | None) -> str:
    """Own body; the full text when the own body is empty."""
    own = normalize_text(body)
    if own:
        return own
    return normalize_text(" ".join(part for part in (body, forwarded, quoted) if part))


def folder_rank(source_file: str) -> int:
    """0 sent folders, 1 inbox folders, 2 user folders, 3 Lotus views, 4 deleted items."""
    parts = source_file.split("/")  # maildir/<mailbox>/<folder>/.../<file>
    folder = parts[2].lower() if len(parts) > 3 else ""
    if folder in _SENT_FOLDERS:
        return 0
    if folder in _INBOX_FOLDERS:
        return 1
    if folder in _VIEW_FOLDERS:
        return 3
    if folder in _TRASH_FOLDERS:
        return 4
    return 2


@dataclass
class Candidate:
    id: int
    message_id: str
    date: str  # ISO 8601 UTC text, sorts chronologically
    from_address: str
    subject: str
    source_file: str
    text: str

    @property
    def sort_key(self) -> tuple:
        return (self.date, folder_rank(self.source_file), self.source_file)


@dataclass
class DuplicateGroup:
    original: Candidate
    members: list[tuple[Candidate, float]] = field(default_factory=list)  # flagged, original-first order

    @property
    def latest(self) -> Candidate:
        return self.members[-1][0]


def load_candidates(conn: sqlite3.Connection) -> list[Candidate]:
    rows = conn.execute(
        "SELECT id, message_id, date, from_address, subject, source_file, body, forwarded_content, quoted_content "
        "FROM emails"
    )
    return [Candidate(*row[:6], text=comparison_text(*row[6:])) for row in rows]


def find_groups(candidates: list[Candidate], threshold: float = SIMILARITY_THRESHOLD) -> tuple[list[DuplicateGroup], dict]:
    """Return duplicate groups (each with >= 1 flagged member) and blocking stats."""
    blocks: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for cand in candidates:
        blocks[(cand.from_address, normalize_subject(cand.subject))].append(cand)

    groups: list[DuplicateGroup] = []
    multi = 0
    in_multi = 0
    for key in sorted(blocks):
        block = blocks[key]
        if len(block) < 2:
            continue
        multi += 1
        in_multi += len(block)
        block.sort(key=lambda c: c.sort_key)
        open_groups: list[DuplicateGroup] = []
        for cand in block:
            best, best_score = None, 0.0
            if cand.text:  # an email with no text at all can never match
                for group in open_groups:
                    # score_cutoff: returns 0 below the threshold and lets rapidfuzz exit early
                    score = fuzz.ratio(cand.text, group.original.text, score_cutoff=threshold)
                    if score > best_score:
                        best, best_score = group, score
            if best is None:
                open_groups.append(DuplicateGroup(cand))
            else:
                best.members.append((cand, best_score))
        groups.extend(g for g in open_groups if g.members)
    groups.sort(key=lambda g: g.original.sort_key)
    return groups, {"candidate_blocks": multi, "emails_in_candidate_blocks": in_multi}


def apply_flags(conn: sqlite3.Connection, groups: list[DuplicateGroup]) -> None:
    """Clear every duplicate flag, then set the new ones, in one transaction."""
    rows = [
        (group.original.message_id, round(score, 2), member.id)
        for group in groups
        for member, score in group.members
    ]
    with conn:
        conn.execute(
            "UPDATE emails SET is_duplicate = 0, duplicate_of = NULL, similarity_score = NULL "
            "WHERE is_duplicate = 1 OR duplicate_of IS NOT NULL OR similarity_score IS NOT NULL"
        )
        conn.executemany(
            "UPDATE emails SET is_duplicate = 1, duplicate_of = ?, similarity_score = ? WHERE id = ?", rows
        )


def write_report(groups: list[DuplicateGroup], path: Path = REPORT_PATH) -> int:
    """One row per flagged email, grouped by original, in the brief's column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(REPORT_COLUMNS)
        for group in groups:
            orig = group.original
            for member, score in group.members:
                writer.writerow((
                    member.message_id, orig.message_id, member.subject, member.from_address,
                    member.date, orig.date, f"{score:.2f}",
                ))
                count += 1
    return count


def compute_stats(candidates: list[Candidate], groups: list[DuplicateGroup], block_stats: dict) -> dict:
    flagged = sum(len(g.members) for g in groups)
    scores = [score for g in groups for _, score in g.members]
    sizes = Counter(len(g.members) + 1 for g in groups)
    return {
        "generated_at": to_iso_utc(datetime.now(timezone.utc)),
        "rule": "same from_address + same normalized subject + rapidfuzz.fuzz.ratio >= 90 on body text",
        "threshold": SIMILARITY_THRESHOLD,
        "emails_scanned": len(candidates),
        **block_stats,
        "groups": len(groups),
        "flagged": flagged,
        "average_group_size": round((flagged + len(groups)) / len(groups), 2) if groups else 0.0,
        "largest_group": max(sizes) if sizes else 0,
        "group_size_distribution": {str(k): sizes[k] for k in sorted(sizes)},
        "flagged_score_100": sum(1 for s in scores if s >= 100),
        "flagged_score_90_to_100": sum(1 for s in scores if s < 100),
        "groups_with_tied_timestamps": sum(
            1 for g in groups if any(m.date == g.original.date for m, _ in g.members)
        ),
        "groups_with_blank_normalized_subject": sum(1 for g in groups if not normalize_subject(g.original.subject)),
    }


def print_stats(stats: dict) -> None:
    print("\n=== Duplicate detection ===")
    print(f"Emails scanned        : {stats['emails_scanned']}")
    print(f"Candidate blocks      : {stats['candidate_blocks']} (same sender + normalized subject, >= 2 emails)")
    print(f"Duplicate groups      : {stats['groups']}")
    print(f"Emails flagged        : {stats['flagged']}  (score 100: {stats['flagged_score_100']}, "
          f"90-99.99: {stats['flagged_score_90_to_100']})")
    print(f"Average group size    : {stats['average_group_size']}  (original + duplicates; largest {stats['largest_group']})")
    print(f"Groups with tied dates: {stats['groups_with_tied_timestamps']}")


def run_dedup(
    db_path: Path = DB_PATH,
    report_path: Path = REPORT_PATH,
    stats_path: Path = STATS_PATH,
) -> tuple[list[DuplicateGroup], dict]:
    conn = connect(db_path)
    try:
        candidates = load_candidates(conn)
        groups, block_stats = find_groups(candidates)
        apply_flags(conn, groups)
    finally:
        conn.close()
    write_report(groups, report_path)
    stats = compute_stats(candidates, groups, block_stats)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8", newline="\n")
    log.info("Duplicate groups %d, flagged %d, average group size %s",
             stats["groups"], stats["flagged"], stats["average_group_size"])
    log.info("Wrote %s and %s", report_path, stats_path)
    print_stats(stats)
    return groups, stats
