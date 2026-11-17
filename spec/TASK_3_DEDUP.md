# Task 3: Duplicate Detection & Flagging

Depends on: Task 2 DB.
Status: Done (2026-11-16). All acceptance items pass. Code: `enron_pipeline/dedup.py` (rules in its docstring), `tests/test_dedup.py`, sample queries Q10-Q12.

## Definition of a duplicate (spec)
Two or more emails are duplicates if they share:
1. the same `from_address`,
2. the same `subject` after normalizing Re:/Fwd: prefixes, and
3. body content that fuzzy-matches with at least 90% similarity.

Among a set of duplicates, the email with the **latest** timestamp is the duplicate that needs confirmation (likely a re-send or accidental repeat). The **earliest** email in the group is the original record.

## Requirements (spec)
| ID | Requirement |
|---|---|
| T3.1 | Scan the DB after ingestion to identify all duplicate groups. |
| T3.2 | For each group, mark the latest email (by date) as the duplicate and keep the earliest as the original. On the flagged email set `is_duplicate = true` and `duplicate_of = <original (earliest) message_id>`. |
| T3.3 | If a group has more than two emails, flag all except the earliest. The latest is the primary target for notification (Task 4), but all flagged records appear in the report. |
| T3.4 | Generate `duplicates_report.csv` with columns: `duplicate_message_id, original_message_id, subject, from_address, duplicate_date, original_date, similarity_score`. |
| T3.5 | Log stats: total groups found, total emails flagged, average group size. |

## Outputs
- DB flags updated (`is_duplicate`, `duplicate_of`, plus `similarity_score`).
- `duplicates_report.csv` at repo root (one row per flagged email, grouped by original).
- Stats printed, logged and saved to `output/dedup_stats.json`.

## Decisions (2026-11-16, with user)
| Topic | Rule |
|---|---|
| Text compared | Sender's own body, whitespace-normalized. If empty (pure forward/reply), the full text (body + forwarded + quoted). Body-only would form 311 groups purely from two empty bodies; full text lets shared quoted threads push different replies over 90%. |
| Metric | `rapidfuzz.fuzz.ratio` 3.14.6 (MIT), threshold >= 90. `token_sort_ratio` gave nearly the same result (8,467 vs 8,484 flagged). |
| Subject normalization | Strip leading stacked `re`/`fw`/`fwd` prefixes (any case, optional `[n]`, spaces before the colon), collapse whitespace, casefold. |
| Clustering | Block by (from_address, normalized subject). Anchor clustering in original-first order; each email joins the group whose original it matches best at >= 90%; score reported against the original. |
| Tie-break (equal dates, 96% of groups) | `(date, folder rank, source_file)`. Folder rank: sent folders (`sent`, `_sent`, `_sent_mail`, `sent_items`) < inbox (`inbox`, `notes_inbox`) < user folders < Lotus views (`all_documents`, `discussion_threads`) < `deleted_items`. |
| Short texts | Follow the rule as written (68 short-text pairs flagged). Documented as a limitation. |
| Reruns | Clear all duplicate flags, recompute. Notification state untouched. |

## Acceptance checklist
- [x] Subject normalization strips stacked/mixed prefixes, case-insensitive, whitespace-trimmed (7 parametrized cases incl. `re[2]:`, `Fwd :`, `Regarding:` kept, mid-subject `re:` kept).
- [x] Recognized fuzzy library (rapidfuzz), threshold enforced: real data min flagged score 90.0, max 100; recomputing all 8,484 scores matches stored values (max diff 0.005, rounding).
- [x] Every group has exactly one unflagged original: 0 originals flagged, 0 flagged rows without `duplicate_of`; all 8,484 pairs share sender + normalized subject, and the original sorts strictly earlier.
- [x] Tie-break deterministic and documented (module docstring + table above); test proves the `sent` copy beats the `all_documents` copy at the same timestamp.
- [x] CSV has exactly the 7 columns in spec order, 8,484 rows = flagged count in DB.
- [x] Stats logged: 3,939 groups, 8,484 flagged, average group size 3.15 (also Q10 in SQL).
- [x] Manual check: 10 random groups are real duplicates (folder copies, re-sent forwards, a marketing re-send 4 minutes later). 73 near-miss pairs at 85-90 inspected by sample: different expense-report owners, different short BlackBerry notes with the same signature. Correctly excluded.
- [x] Rerun is idempotent: identical CSV hash and identical DB flags on the real data; test also proves stale flags are cleared and `notification_sent` survives.

## Results (final run)
- 22,352 emails scanned, 3,668 candidate blocks, 3,939 groups, 8,484 flagged (7,980 at 100, 504 at 90-99.99), average group size 3.15, largest 28.
- Per mailbox flagged: allen-p 59.6%, arnold-j 51.3%, lay-k 39.5%, skilling-j 44.4%, kitchen-l 7.7%. Lotus Notes mailboxes store each email in several folders; Outlook-only kitchen-l does not.
- Runtime about 1.5 s for detection.

## Known limitations (for README)
- Templated automatic mail is flagged when only a number or name changes: overdue reminders ("5 days" vs "55 days"), weekly deal reports for consecutive weeks, mail-merge greetings ("Kenneth:" vs "Jeffrey:"). Fuzzy body similarity cannot tell these from re-sends; the brief's rule flags them.
- Short messages with a long shared signature score high on the signature alone; different short notes can approach the threshold (seen at 86-88%).
- 68 flagged pairs have under 40 characters of text (e.g. a one-line note sent twice two weeks apart, blank subject).
- Source timestamps: many copies of the same email differ by exactly 10 or 12 hours across folders (timezone artifact in the dataset); "latest" follows those raw timestamps.
- Recipients are not part of the rule, so the same note sent separately to different people is a duplicate group.

## Open decisions
- None. For Task 4: 8,484 flagged emails in 3,939 groups. "Latest" per group = last member in `sort_key` order (`DuplicateGroup.latest`).
