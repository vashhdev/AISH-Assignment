# Task 3: Duplicate Detection & Flagging

Depends on: Task 2 DB.
Status: Not started.

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
- DB flags updated (`is_duplicate`, `duplicate_of`).
- `duplicates_report.csv` (one row per flagged email).
- Stats logged.

## Acceptance checklist
- [ ] Subject normalization strips stacked/mixed prefixes (`Re:`, `RE:`, `Fwd:`, `FW:`, `Fw:`, `Re: Re:` ...), case-insensitive, whitespace-trimmed.
- [ ] Similarity computed with a recognized fuzzy library; threshold >= 90 enforced.
- [ ] In every group exactly one email (the earliest) has `is_duplicate = 0`; all others have `is_duplicate = 1` and `duplicate_of` pointing to the earliest.
- [ ] Tie-break for identical timestamps is deterministic and documented.
- [ ] CSV has exactly the 7 columns in spec order, one row per flagged email.
- [ ] Stats logged: groups, flagged, average group size.
- [ ] Manual check of ~10 groups: they really are duplicates. A few near-misses (85-90%) are correctly excluded.
- [ ] Re-running detection is idempotent (resets flags first, gives the same result).

## Open decisions
- Which text is compared: primary `body` only, or body + forwarded/quoted? Spec says "body content". Proposal: primary body; fall back to full text when the primary body is empty.
- Similarity metric: `rapidfuzz.fuzz.ratio` (strict, order-aware) vs `token_sort_ratio`. Proposal: `ratio` on whitespace-normalized text.
- Non-transitive similarity (A~B, B~C, but A not ~C). Proposal: anchor clustering. Sort by date; each email joins the first earlier group whose original it matches at >= 90%, otherwise it starts a new group. Reported score = similarity vs the original.
- Tie-break for equal dates. Proposal: `(date, message_id)` or `(date, source_file)`.
- Empty bodies: two empty bodies score 100%. Include or exclude?

## Our notes
- Blocking: group by `(from_address, normalized_subject)` first, fuzzy-compare only inside each block. Keeps it fast.
- Expect many groups caused by the same email living in several folders (`01_OVERVIEW.md` gotcha 2). That is legit under the spec's definition, but worth calling out in README.
