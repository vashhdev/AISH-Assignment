# Deliverables (spec Section 7) + AI usage docs (spec Section 6)

Submit a Git repository containing:

| Item | Description | Produced by |
|---|---|---|
| Source code | All scripts/modules for extraction, storage, duplicate detection, and MCP email sending | Tasks 1-4 |
| `README.md` | Setup instructions (including MCP server setup), how to run, architecture overview | Task 5 |
| `AI_USAGE.md` | AI tool usage documentation (Section 6), including the MCP integration section (4.3) | Task 5 (+ Task 4 notes) |
| `schema.sql` | DB schema. Must include `is_duplicate`, `duplicate_of`, `notification_sent`, `notification_date` columns | Task 2 |
| `sample_queries.sql` | At least 3 sample queries with expected output descriptions | Task 2 |
| `mcp_config.json.example` | MCP server config template with placeholder credentials | Task 4 |
| `output/replies/` | Generated draft reply `.eml` files for all flagged duplicates (dry-run output) | Task 4 |
| `output/send_log.csv` | Log of all emails sent in live mode: timestamp, recipient, subject, status, error | Task 4 |
| `duplicates_report.csv` | Summary CSV of all detected duplicates with similarity scores | Task 3 |
| `error_log.txt` | Log of all parse failures with file paths and reasons | Task 1 |
| `requirements.txt` | Python dependencies (or `package.json` for Node.js) | All |

## AI_USAGE.md required contents (spec Section 6, "a critical part of the evaluation")
Spec: "We want to understand how you collaborate with AI tools, not just see the final code."

1. **Tool used:** name and version of the AI coding tool.
2. **Prompting strategy:** how we broke the problem down for the AI. Task-by-task or full spec at once? Include 3-5 example prompts and explain why they were structured that way.
3. **Iterations & debugging:** at least 2 cases where AI-generated code did not work on the first attempt. What went wrong? How were prompts refined, or the issue fixed manually?
4. **What we wrote vs what AI wrote:** rough percentage breakdown, plus specific sections written manually vs AI-generated.
5. **Lessons learned:** what worked well with AI assistance, what was harder than expected.
6. **MCP integration section** (T4.5-T4.9 in `TASK_4_MCP_NOTIFY.md`): server + why, setup steps, example prompts for `send_email`, issues + fixes, screenshot/log of a successful live send.

## README.md required contents
- Setup instructions: Python env, dataset download + extract, MCP server setup.
- How to run: single command; `--send-live` for real sending.
- Architecture overview.
- Also required elsewhere in the spec: which mailboxes were chosen and why, fuzzy library choice. Worth adding: headings heuristic, duplicate tie-break rules.

## Final submission checklist
- [ ] Single command runs everything end to end in dry-run on a fresh clone (after dataset download).
- [ ] All 11 deliverable items present at the expected paths.
- [ ] No secrets anywhere in git history.
- [ ] No dataset files committed.
- [ ] No em/en dashes in the repo (grep).
- [ ] AI_USAGE.md covers all 6 sections above.
- [ ] `requirements.txt` installs clean in a fresh venv.
- [ ] Repo shared as instructed.
