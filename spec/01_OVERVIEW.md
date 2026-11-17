# Overview

Doc title: **Take-Home Assignment: Data Extraction & Structuring. Enron Email Dataset, AI-Assisted Pipeline with MCP Integration.** Using Claude Code or any AI coding tool of your choice.

## Goal (spec Section 1)
The assignment evaluates our ability to use AI-assisted development tools (preferably Claude Code) to build a data extraction, structuring, and automated notification pipeline. We work with the Enron Email Dataset (one of the most widely used real-world unstructured datasets) to:
raw email files -> parsed structured fields -> local database -> duplicate detection -> automated notification emails sent through a Gmail MCP (Model Context Protocol) server.

Stated goal: demonstrate we can leverage AI coding tools effectively to solve a real data engineering problem end to end, from raw data ingestion to automated action.

Evaluators care about process as much as code: how we prompt, iterate, debug and refine with AI assistance, and how we integrate external services via MCP.

Deadline: 1 day from receipt.

## Dataset (spec Section 2)
- Source: Enron Email Dataset
- Download: https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz
- Size: ~500,000+ email files across ~150 employee mailboxes
- Format: raw RFC 2822 text files in `maildir/<employee_name>/<folder>/<email_file>`
- Subset rule: the entire dataset is NOT required. A representative subset of at least 5 employee mailboxes (minimum 10,000 emails total) is enough to demonstrate the pipeline. Document which mailboxes were selected and why.

## Pipeline at a glance
```
maildir/ (chosen subset)
   |  Task 1: discover + parse + validate      -> error_log.txt, extraction stats
   v
SQLite DB (schema.sql)
   |  Task 2: normalized insert, unique message_id, indexes, sample_queries.sql
   v
Duplicate scan
   |  Task 3: group + flag is_duplicate/duplicate_of -> duplicates_report.csv, stats
   v
Notifications
      Task 4: dry-run      -> output/replies/*.eml
              --send-live  -> Gmail MCP send_email -> output/send_log.csv,
                              DB notification_sent / notification_date
```

## Task map
| Task | File | Main outputs |
|---|---|---|
| 1 | `TASK_1_EXTRACTION.md` | parser, `error_log.txt`, stats |
| 2 | `TASK_2_DATABASE.md` | `schema.sql`, DB loader, `sample_queries.sql` |
| 3 | `TASK_3_DEDUP.md` | flags in DB, `duplicates_report.csv`, stats |
| 4 | `TASK_4_MCP_NOTIFY.md` | `.eml` drafts, live sends via MCP, `send_log.csv`, `mcp_config.json.example` |
| 5 | `DELIVERABLES.md` | `README.md`, `AI_USAGE.md`, final checklist |

## Local environment (checked 2026-11-16)
- Windows 11, PowerShell + Git Bash
- Python 3.11.9, Node 22.22.2, npm 10.9.7, git 2.51.1, uv 0.11.10
- ~46 GB free on C:

## Architecture decisions log
| ID | Decision | Status | Choice |
|---|---|---|---|
| D1 | How live sending reaches Gmail (Python as MCP client vs AI tool calling the MCP tool vs both) | Decided 2026-11-16 | Python MCP client: `main.py --send-live` uses the official `mcp` Python SDK to spawn the Gmail MCP server over stdio and call `send_email`. Same server also registered with Claude Code for prompt-driven demo sends (AI_USAGE.md evidence). |
| D2 | Live recipient policy (override to own Gmail, send cap) | Decided 2026-11-16 | All live sends go to our own Gmail (address from `.env`). Intended Enron sender kept in DB + log. `--limit N` flag, small default (e.g. 5). Email body stays exactly per template. |
| D3 | Which Gmail MCP server | Leaning, confirm at Task 4 smoke test | GongRzhe/Gmail-MCP-Server pinned to npm 1.1.11 (archived but works on paper). Fallback: custom FastMCP server. Research in `TASK_4_MCP_NOTIFY.md`. |
| D4 | Database engine + normalization | Decided 2026-11-16 | SQLite (spec preference, zero setup, single file). Separate `addresses` lookup table; recipients link by id. Dates as ISO 8601 UTC text. |
| D5 | Fuzzy matching library | Proposed | `rapidfuzz` (MIT, fast, widely used) |
| D6 | How AI_USAGE.md names the AI tool, given the "no Claude mentions in pushed content" preference | Decided 2026-11-16 | Exception only where the assignment requires it: AI_USAGE.md, README's MCP registration steps, and `spec/` (AI process docs, ships per D9). Commits, code, comments: no mentions. |
| D7 | Which mailboxes form the subset | Decided 2026-11-16 | `lay-k` (5,937), `skilling-j` (4,139), `kitchen-l` (5,546), `arnold-j` (4,898), `allen-p` (3,034) = 23,554 files. Mix of roles (2 CEOs, EnronOnline president, 2 gas traders) and mailbox styles (Lotus-era `all_documents`/`_sent_mail` vs Outlook-only `kitchen-l`), duplicate-rich, ~2.3x the minimum. Full per-mailbox counts in `data/mailbox_counts.json`. |
| D8 | Where `duplicates_report.csv` and `error_log.txt` live (repo root vs `output/`) | Decided 2026-11-16 (default) | Repo root, literal reading of the deliverables table. Everything else under `output/`. |
| D9 | Whether `spec/` ships in the final repo | Decided 2026-11-16 | Ship it. Evidence of the task-breakdown + acceptance-check workflow for AI_USAGE.md "prompting strategy". |

## Known gotchas (our notes, verify as we go)
1. **Trailing-dot filenames on Windows. CONFIRMED:** all 517,401 files in the archive (150 mailboxes) end in `.`. Windows drops trailing dots. Solved in `enron_pipeline/dataset.py`: streams the tarball, writes only the chosen mailboxes, strips trailing dots/spaces per path component (`1.` -> `1`), blocks path traversal. Resulting paths match the spec example `maildir/lay-k/inbox/45`. Folders `calendar`, `contacts`, `tasks` hold non-email items: expected parse failures.
2. **Message-IDs are synthetic per file.** The same email stored in `sent`, `_sent_mail` and `all_documents` (or in both sender's and recipient's mailbox) usually carries different Message-IDs. Expect many fuzzy duplicate groups, often with identical timestamps, so Task 3 needs a deterministic tie-break.
3. **Notification volume.** There may be hundreds or thousands of duplicate groups. Gmail has daily send limits and we must not spam. Live mode needs a cap.
4. **Template headers vs MCP tool.** The template has `Date:` and `References:` headers. Mostly resolved for GongRzhe: `inReplyTo` sets `References`, and Gmail sets `Date` at send time. Dry-run `.eml` files carry full headers.
5. **Spec errata.** The Deliverables table says AI_USAGE.md is "described in Section 7"; it is actually Section 6. Nothing to act on, just don't get confused.
