# Spec Pack: Enron Email Pipeline Take-Home

Source: `R2 - Take Home Assignment.docx`, converted and split here so we never need to reopen it.
Deadline: 1 day from receipt.

## How we work
1. Pick the next task in the tracker below.
2. Load only: `00_RULES.md`, `01_OVERVIEW.md`, the active task file, and any shared reference it links to.
3. Build it.
4. Check the output against that task's **Acceptance checklist**. Iterate until every box passes.
5. Mark the task done here, note anything interesting in `AI_USAGE_LOG.md`, move on.

## Files
| File | What it holds | Load when |
|---|---|---|
| `00_RULES.md` | Hard constraints from the assignment + our working rules | Always |
| `01_OVERVIEW.md` | Goal, dataset, pipeline shape, architecture decisions, known gotchas | Always |
| `02_FIELDS.md` | Mandatory/optional field definitions + parsing notes | Task 1, Task 2 |
| `TASK_1_EXTRACTION.md` | Parse maildir into records, error log, stats | Task 1 |
| `TASK_2_DATABASE.md` | SQLite schema, normalization, indexes, sample queries | Task 2 |
| `TASK_3_DEDUP.md` | Duplicate definition, flagging, report, stats | Task 3 |
| `TASK_4_MCP_NOTIFY.md` | Gmail MCP setup, notification logic, dry-run/live, MCP docs | Task 4 |
| `EMAIL_TEMPLATE.md` | Exact notification email template + placeholder mapping | Task 4 |
| `DELIVERABLES.md` | Final repo contents, README/AI_USAGE requirements, submission checklist | Task 5, or any time for reference |
| `AI_USAGE_LOG.md` | Running journal of prompts, failures, fixes (raw material for AI_USAGE.md) | Append as we go |

## Tracker
| # | Task | Status | Notes |
|---|---|---|---|
| 0 | Spec split + architecture decisions | Done | D1, D2, D6, D9 decided. D3 (MCP server), D7 (mailboxes), D8 (output paths) deferred to their tasks. Spec verified against docx. |
| 1 | Data extraction pipeline | Done | 22,352 / 23,554 parsed (94.9%), 1,202 logged failures, 30 tests. OAuth keys for Task 4 in `~/.gmail-mcp/` (Desktop app type, verified). |
| 2 | Database storage | Done | SQLite `output/enron.db`: 22,352 emails, 11,739 addresses, 164,473 recipient links. Idempotent reload. 9 sample queries verified. 37 tests. |
| 3 | Duplicate detection & flagging | Done | 3,939 groups, 8,484 flagged, avg group size 3.15. `duplicates_report.csv` at root. Idempotent. 50 tests. |
| 4 | MCP notification emails | Not started | |
| 5 | Docs + deliverables wrap-up | Not started | README.md, AI_USAGE.md, final checklist |
