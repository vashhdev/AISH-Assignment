"""Task 1: discover email files, parse them, log failures and report extraction statistics."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .parser import EmailRecord, ParseError, parse_file

log = logging.getLogger(__name__)

MANDATORY_FIELDS = ("message_id", "date", "from_address", "to_addresses", "subject", "body", "source_file")
OPTIONAL_FIELDS = (
    "cc_addresses", "bcc_addresses", "x_from", "x_to", "x_cc", "x_bcc", "x_folder", "x_origin",
    "content_type", "has_attachment", "forwarded_content", "quoted_content", "headings",
)


@dataclass
class ExtractionResult:
    records: list[EmailRecord]
    failures: list[tuple[str, str]]  # (source_file, reason)
    stats: dict


def discover(maildir: Path) -> list[Path]:
    """Recursively find every email file under ``maildir`` (hidden files skipped), in stable order."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(maildir):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.startswith("."):
                found.append(Path(dirpath) / name)
    return found


def _is_filled(value: object) -> bool:
    return value is not None and value != "" and value != []


def compute_stats(total: int, records: list[EmailRecord], failures: list[tuple[str, str]]) -> dict:
    parsed = len(records)
    completeness = {}
    for name in MANDATORY_FIELDS + OPTIONAL_FIELDS:
        if name == "has_attachment":
            filled = sum(1 for r in records if r.has_attachment)
        else:
            filled = sum(1 for r in records if _is_filled(getattr(r, name)))
        completeness[name] = {
            "filled": filled,
            "rate": round(filled / parsed, 4) if parsed else 0.0,
            "kind": "mandatory" if name in MANDATORY_FIELDS else "optional",
        }
    reasons: dict[str, int] = {}
    for _, reason in failures:
        for part in reason.split("; "):
            key = part.split(" (")[0].split(" '")[0]
            reasons[key] = reasons.get(key, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_files": total,
        "parsed": parsed,
        "failed": len(failures),
        "success_rate": round(parsed / total, 4) if total else 0.0,
        "failure_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "dropped_address_tokens": sum(len(r.dropped_addresses) for r in records),
        "field_completeness": completeness,
    }


def write_error_log(failures: list[tuple[str, str]], total: int, path: Path) -> None:
    lines = [
        f"# Parse failures: {len(failures)} of {total} files",
        f"# Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "# Format: source_file<TAB>reason",
    ]
    lines += [f"{source}\t{reason}" for source, reason in failures]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def print_stats(stats: dict) -> None:
    print("\n=== Extraction statistics ===")
    print(f"Total files found : {stats['total_files']}")
    print(f"Parsed OK         : {stats['parsed']} ({stats['success_rate']:.1%})")
    print(f"Failed            : {stats['failed']}")
    for reason, count in stats["failure_reasons"].items():
        print(f"    {count:>6}  {reason}")
    print(f"Dropped invalid address tokens: {stats['dropped_address_tokens']}")
    print("\nField completeness (share of parsed records with a non-empty value; has_attachment = share True):")
    for name, info in stats["field_completeness"].items():
        print(f"  {name:18} {info['kind']:9} {info['filled']:>6}  {info['rate']:7.1%}")


def run_extraction(
    data_dir: Path = config.DATA_DIR,
    error_log_path: Path = config.PROJECT_ROOT / "error_log.txt",
    stats_path: Path = config.OUTPUT_DIR / "extraction_stats.json",
) -> ExtractionResult:
    """Parse every email file under ``data_dir/maildir``. Never raises on bad input."""
    files = discover(data_dir / "maildir")
    log.info("Discovered %d email files", len(files))
    records: list[EmailRecord] = []
    failures: list[tuple[str, str]] = []
    for path in files:
        source = path.relative_to(data_dir).as_posix()
        try:
            records.append(parse_file(path, data_dir))
        except ParseError as exc:
            failures.append((source, str(exc)))
        except Exception as exc:  # never crash on malformed input (spec Section 5)
            failures.append((source, f"unexpected error {type(exc).__name__}: {exc}"))

    stats = compute_stats(len(files), records, failures)
    write_error_log(failures, len(files), error_log_path)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8", newline="\n")
    log.info("Wrote %s and %s", error_log_path, stats_path)
    print_stats(stats)
    return ExtractionResult(records, failures, stats)
