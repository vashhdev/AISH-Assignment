# Task 1: Data Extraction Pipeline

Depends on: `02_FIELDS.md` (field definitions).
Status: Done (2026-11-16). All acceptance items pass. Code: `enron_pipeline/{dataset,parser,body_split,headings,extract}.py`, `main.py`, `tests/`.

## Requirements (spec)
Build a script or application that:

| ID | Requirement |
|---|---|
| T1.1 | Recursively traverses the Enron maildir folder structure and discovers all email files. |
| T1.2 | Parses each raw email file to extract the mandatory and optional fields defined in Section 3 (see `02_FIELDS.md`). |
| T1.3 | Handles parsing edge cases gracefully: malformed headers, missing fields, encoding issues, multi-line header values, and nested forwarded messages. |
| T1.4 | Logs all parse failures with the file path and reason to a separate error log. |
| T1.5 | Outputs extraction statistics: total files found, successfully parsed, failed, and field-level completeness rates. |

Also from Section 2: subset of at least 5 mailboxes and at least 10,000 emails. Document which and why.

## Outputs
- Parser module(s) producing one structured record per email (feeds Task 2).
- `error_log.txt`: one line per failure, file path + reason.
- Extraction stats: printed to console and saved to a file (e.g. `output/extraction_stats.json`).

## Steps (proposed)
0. Download tarball to `data/`, list mailboxes + file counts straight from the archive, pick subset (D7), extract only those.
1. Discovery: walk `data/maildir/<chosen>/...`, collect files.
2. Parse: decode bytes, parse headers, unfold, extract fields, split body.
3. Validate mandatory fields -> success record, or failure with reason.
4. Stats: totals + per-field completeness (% of parsed records with a non-empty value).
5. Spot-check ~20 records across mailboxes by eye against the raw files.

## Acceptance checklist
- [x] Subset is >= 5 mailboxes and >= 10,000 email files; choice + reasoning written down (D7: 5 mailboxes, 23,554 files).
- [x] Traversal finds every file: 23,554 discovered = 23,554 counted from the archive stream = 23,554 counted by PowerShell.
- [x] All 7 mandatory fields present on every successful record (100% for all; subject/body may be `""` by decision).
- [x] All 13 optional fields attempted; NULL/empty when absent.
- [x] Dates are UTC: unit tests for PST/CDT/EST/CEST/offset; real sample `07:16 -0700 (PDT)` -> `14:16Z` checked.
- [x] Addresses bare + lowercased; folded multi-line To lists captured (unit test; 2,995 folded To headers in data).
- [x] `source_file` relative, e.g. `maildir/allen-p/sent_items/221`.
- [x] Body split unit-tested and spot-checked on `-----Original Message-----`, `Forwarded by` (wrapped), Lotus reply headers, AOL embedded headers, inline `>` quotes.
- [x] Never crashes: `tests/test_extract.py` runs the full extractor over empty, binary and header-less files; real run has 0 "unexpected error" entries.
- [x] `error_log.txt`: 1,202 lines, `source_file<TAB>reason`.
- [x] Stats printed + saved to `output/extraction_stats.json`.
- [x] Spot-checked 20 random + 11 targeted records; 2 misclassifications found and fixed (FW: Outlook forwards, AOL forwards).

## Results (final run)
- 23,554 found, 22,352 parsed (94.9%), 1,202 failed: 1,171 missing To, 32 placeholder Date, 1 invalid From (`pep <performance.>`, truncated in source data).
- Completeness: mandatory 100% present (subject non-empty 89.4%, body non-empty 92.2%); cc 20.8%, x_bcc 0.1%, has_attachment True 20.3%, forwarded 14.6%, quoted 24.1%, headings 14.2%.
- Runtime ~22 s. 30 unit tests pass.

## Data profile (23,554 files, 2026-11-16)
- Message-ID, Date, From: 100%. Duplicate Message-IDs: 0.
- To header missing: 1,171 (5%). Mostly bulk mail (X-To `All Enron Worldwide`, `undisclosed-recipients`) + calendar/contacts/tasks items.
- Subject present but blank: 2,394 (10%). Subject absent: 0.
- Dates: only 2 shapes, `Mon, 9 Oct 2000 07:16:00 -0700 (PDT)`. 32 dated `1979-12-31 16:00 PST` = `1980-01-01 00:00 UTC` (DOS epoch placeholder). Real range 1998-2002.
- Content-Type: 100% `text/plain` (1 missing). CTE: 1,069 quoted-printable (must decode).
- 8 non-UTF-8 files. `email` lib returns `Header` objects for them (not `str`).
- Cc present 4,760 and Bcc present 4,760: Bcc equals Cc in 100% of cases (dataset conversion artifact). X-bcc non-empty only 13.
- Addresses: 1,990 with Enron artifacts like `'.hall@enron.com'`, 30 garbage tokens without `@`. IMCEANOTES: 0 in subset.
- Bodies: ~8,500 contain embedded headers; `-----Original Message-----` 4,153; `Forwarded by` 2,173 (marker can wrap onto 2 lines); Lotus reply blocks (`Name` / `MM/DD/YYYY HH:MM AM` / `To:`) 1,768; `>` quoted 739 (can be inline, interleaved with own text); `<<File: x>>` 930.

## Decisions (2026-11-16, with user)
| Topic | Rule |
|---|---|
| Missing To header | Fail, logged as missing To with the X-To hint. |
| To present but no valid address | Fail. |
| Blank subject (header present) | Accept as `""`. Fail only if Subject header absent. |
| Placeholder / implausible date | Fail: `1980-01-01 00:00 UTC` placeholder, or anything outside 1990-2010. |
| Body | `body` = sender's own text after splitting; may be `""` for pure forwards/replies. Fail only if raw body is empty/whitespace. |
| Garbage address tokens (no `@`) | Dropped from the list, counted in stats. Enron artifacts like `.hall@enron.com` kept as-is (lowercased). |
| Bcc mirroring Cc | Stored as-is (spec says capture Bcc); artifact documented in README. |
| D8 output paths | `error_log.txt` and `duplicates_report.csv` at repo root (literal reading of deliverables table); everything else under `output/`. |

## Open decisions
- None. Headings heuristic finalized after two review rounds on real data (rules in `enron_pipeline/headings.py` docstring; copy into README). Known residual noise: signature lines like `ENRON`, `CEO`.

## Our notes
- See `01_OVERVIEW.md` gotcha 1 (trailing dots on Windows) and gotcha 2 (synthetic Message-IDs).
- Mailbox selection idea: mix executives (e.g. `lay-k`, `skilling-j`) for recognizability with high-volume mailboxes that have `sent` / `_sent_mail` / `all_documents` folders (rich in duplicates, useful for Task 3). Decide after counting.
