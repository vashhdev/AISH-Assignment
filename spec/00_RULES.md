# Rules

## A. Hard rules from the assignment
Straight from the spec (Section 5 and task text). Breaking one = failing a requirement.

| ID | Rule |
|---|---|
| R1 | Language: Python 3.10+. (Local machine: Python 3.11.9.) |
| R2 | Database: SQLite (preferred, portable) or local PostgreSQL. |
| R3 | Dependencies listed in `requirements.txt` (or `package.json` for Node). No proprietary or paid libraries. |
| R4 | Fuzzy matching uses a recognized library. Document the choice. |
| R5 | Pipeline must never crash on malformed input. Every exception is caught, logged, and the item skipped. |
| R6 | One command (e.g. `python main.py` or `make run`) runs the full pipeline end to end. |
| R7 | Real email sending happens only with the `--send-live` flag. Default run is dry-run. |
| R8 | MCP server is Gmail-compatible and supports a `send_email` tool (existing open-source or custom-built). |
| R9 | MCP config is included with credentials redacted; ship `mcp_config.json.example` with placeholder credentials. |
| R10 | A record missing any mandatory field is NOT stored; it is logged as a failed parse with file path and reason. |
| R11 | AI tool: Claude Code (preferred), GitHub Copilot, Cursor, or any AI coding assistant. Document which tool (name + version) was used. |
| R12 | Dataset: a representative subset of at least 5 employee mailboxes AND at least 10,000 emails total. Processing the entire dataset is NOT required. Document which mailboxes were selected and why. |

## B. Our working rules
| ID | Rule |
|---|---|
| W1 | One task at a time. A task is done only when every item in its acceptance checklist passes. |
| W2 | Spec text stays faithful. Our interpretations go under "Our notes" / "Open decisions", never mixed into requirement text. |
| W3 | Safety: never send live email to real Enron addresses. Live mode sends only to our own Gmail. Exact policy: decision D2 in `01_OVERVIEW.md`. |
| W4 | Secrets never touch git: OAuth client JSON, tokens, `.env`, the real `mcp_config.json`. Add them to `.gitignore` before the first commit. |
| W5 | Raw dataset (tarball, extracted maildir) is never committed. It lives under `data/` (gitignored). |
| W6 | No em dashes or en dashes anywhere (code, comments, docs, commits). Use `-`, commas, or periods. |
| W7 | No AI co-author trailers in commits, no "generated with" footers. How AI_USAGE.md names the tool: decision D6. |
| W8 | Log prompts, failures and fixes in `AI_USAGE_LOG.md` as they happen. Reconstructing them at the end is hard. |
| W9 | Standard library first (`email`, `sqlite3`, `csv`, `logging`, `pathlib`). Add a dependency only when it clearly earns its place. |
