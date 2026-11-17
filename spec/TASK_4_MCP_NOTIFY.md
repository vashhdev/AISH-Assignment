# Task 4: Send Notification Emails via MCP

Depends on: Task 3 flags, `EMAIL_TEMPLATE.md`.
Status: Done (2026-11-17). All acceptance items pass. Code: `enron_pipeline/notify.py`, `main.py --send-live --limit N`, `tests/test_notify.py` + `tests/fake_gmail_mcp.py`, `mcp_config.json.example`, `gcp-oauth.keys.json.example`, `.env.example`.

Spec intent: configure and use a Gmail MCP server to actually send duplicate notification emails from the pipeline to an email address (preferably our own Gmail). Tests our ability to integrate external services with AI-assisted tooling.

## Requirements (spec)

### 4.1 MCP server setup
| ID | Requirement |
|---|---|
| T4.1 | Set up a Gmail MCP server that the AI tool can use to send emails. Must support a `send_email` tool. |
| T4.2 | Include the MCP server configuration in the project with credentials redacted. Provide `mcp_config.json.example` showing the structure. |

### 4.2 Notification email logic
| ID | Requirement |
|---|---|
| T4.3 | For each duplicate group, send a notification email to the sender of the latest (duplicate) email, informing them their message has been flagged. |
| T4.4 | The notification must follow the template in `EMAIL_TEMPLATE.md`. |

### 4.3 MCP integration documentation (dedicated section in AI_USAGE.md)
| ID | Must cover |
|---|---|
| T4.5 | Which MCP server we chose and why. |
| T4.6 | Step-by-step setup: how to configure credentials, how to register the MCP server with the AI tool. |
| T4.7 | How we prompted the AI tool to use the MCP `send_email` tool, with example prompts. |
| T4.8 | Issues hit during MCP setup or sending, and how we resolved them. |
| T4.9 | Screenshot or log excerpt showing at least one successful send in live mode. |

### Related rules and deliverables
- Default run = dry-run. Real sending only with `--send-live` (R7).
- `output/replies/`: generated draft reply `.eml` files for **all flagged duplicates** (dry-run output).
- `output/send_log.csv`: log of all emails sent in live mode with `timestamp, recipient, subject, status, error`.
- DB columns `notification_sent` and `notification_date` exist (schema requirement); update them after successful sends.

## Acceptance checklist
- [x] Gmail MCP server runs locally and is registered with Claude Code (`claude mcp add gmail --scope local ...`, status Connected); `send_email` visible and used from a prompt.
- [x] `mcp_config.json.example` (+ `gcp-oauth.keys.json.example` with REDACTED values, `.env.example`) committed; real config, keys, token and `.env` gitignored or outside the repo.
- [x] Dry run writes one `.eml` per flagged duplicate: 8,484 files in `output/replies/`. Body tested against the literal template text; headers To/Subject/Date/References, unfolded.
- [x] `--send-live` sends through MCP `send_email`, only to `NOTIFY_LIVE_TO`, refused for @enron.com or any dataset address, capped by `--limit` (default 5, max 50).
- [x] Live email received in our Gmail; screenshot `docs/images/live_send_gmail.png`. "Show original" confirmed `In-Reply-To` and `References` = the flagged Message-ID.
- [x] `output/send_log.csv`: one row per attempt; the 5 required columns first, plus `intended_recipient`, `flagged_message_id`. Failure rows with error text proven in tests.
- [x] `notification_sent` / `notification_date` set only after the server confirms; real rerun picked the next 4 groups; tests prove failed sends are retried and sent ones skipped.
- [x] Failures logged, not raised: server that cannot start, server error text, timeouts (tests with a stand-in MCP server over real stdio).
- [x] Example prompts captured in `AI_USAGE_LOG.md` (entries 12-13).

## Results (2026-11-17)
- Pipeline live runs: `--limit 1` then `--limit 4`: 5 attempted, 5 sent, 0 failed. Intended recipients: jan_levine@travisintl.com, markskilling@hotmail.com (3), sherri.reinartz@enron.com.
- Prompt-driven send from Claude Code: 1 sent (Summer Interns notice), first try. Not in `send_log.csv` or the DB on purpose: that log covers pipeline live mode only.

## Decisions (2026-11-16/17, with user)
| Topic | Rule |
|---|---|
| D3 server | GongRzhe 1.1.11 confirmed by smoke test: Python `mcp` 2.3.0 handshake on protocol 2024-11-05, 19 tools, `send_email` schema as researched. |
| Subject | Literal template: `[Duplicate Notice] Re: <original subject as stored>`, even when that gives `Re: Re:` (1,383 groups) or a trailing `Re: ` (468). |
| Date values | RFC 2822 in UTC (`Wed, 26 Jul 2000 10:46:00 +0000`) for `Date:` and both `Date Sent:` lines. |
| Similarity | Two decimals, same as `duplicates_report.csv`. |
| Drafts | All 8,484 committed (about 7 MB on disk, under 2 MB in git). Regenerated each run; only the Date header changes. |
| Live order | Report order, skipping notified groups. |
| send_log.csv | Committed as-is with the real live recipient (user's choice). |
| Claude Code | Local-scope registration; `.claude/settings.local.json` denies the 18 other Gmail tools; `send_email` stays on ask. |

## Issues hit and fixes (for AI_USAGE.md T4.8)
1. Server reports failures as a normal text result (`Error: ...`) without the MCP `isError` flag (read in the published `dist/index.js`). Fix: success only when the text starts with `Email sent successfully`. A test server reproduces this.
2. Server starts and lists tools without any OAuth token; auth problems only surface at send time. So "handshake OK" is not "can send"; the first live run used `--limit 1`.
3. `mcp` 2.x renamed FastMCP to `MCPServer` (`from mcp.server.mcpserver import MCPServer`); the first import attempt for the test server failed with the migration message.
4. Requested scopes are broad (`gmail.modify`, `gmail.settings.basic`). Mitigated: pipeline calls only `send_email`; Claude Code denies the other 18 tools.
5. A server added with `claude mcp add` is not visible in a Claude Code session that was already running; the session had to be restarted (`claude --continue`).
6. Issue #96 (arrays sent as strings from Claude Code) did not occur with Claude Code 2.1.326.
7. Sign-in shows Google's "app not verified" screen for a personal OAuth client; expected, continue via Advanced.

## D3 research: GongRzhe/Gmail-MCP-Server (checked 2026-11-16)
Candidate from user: https://github.com/GongRzhe/Gmail-MCP-Server (npm `@gongrzhe/server-gmail-autoauth-mcp`).

Facts (verified from repo source, the published npm 1.1.11 build, and GitHub API):
- MIT, ~1.17k stars, ~418 forks. **Archived** (read-only), last push 2025-08-06, 70 open issues. No fixes will ever land.
- Latest npm version 1.1.11. Pin it: `npx -y @gongrzhe/server-gmail-autoauth-mcp@1.1.11`.
- Tool is named exactly `send_email`. Params: `to` (array), `subject`, `body`, `htmlBody`, `mimeType`, `cc`, `bcc`, `threadId`, `inReplyTo`, `attachments`.
- `inReplyTo` sets both `In-Reply-To` and `References` headers (confirmed in published `dist/utl.js`), so the template's `References:` line is achievable. Issue #66 claims otherwise; it does not match the 1.1.11 code.
- `Date` header is not settable; Gmail stamps it at send time, which equals `<current_timestamp>` anyway.
- Auth: Google Cloud OAuth client (Desktop app or Web app with redirect `http://localhost:3000/oauth2callback`). Keys at `~/.gmail-mcp/gcp-oauth.keys.json`, tokens at `~/.gmail-mcp/credentials.json`. Both overridable via `GMAIL_OAUTH_PATH` / `GMAIL_CREDENTIALS_PATH` env vars (useful for `mcp_config.json.example`). One-time `npx ... auth` opens a browser, needs port 3000 free.
- Scopes requested: `gmail.modify` + `gmail.settings.basic` (read, label, trash, filters). Much broader than our send-only need. Server also exposes ~17 tools incl. delete and filter tools.
- Built on `@modelcontextprotocol/sdk ^0.4.0` (protocol `2024-11-05`). Python `mcp` 2.3.0 / `mcp-types` 2.3.0 still lists `2024-11-05` in `HANDSHAKE_PROTOCOL_VERSIONS`, so our Python client should connect. Not yet tested live.
- Open issue #96: when called **from Claude Code**, array params (`to`, `cc`, `bcc`) can arrive as JSON strings and fail with `Expected array, received string`. Our Python client sends real lists, so the pipeline path is unaffected; the Claude Code demo path might hit it.

Mitigations if we keep it:
- Pin 1.1.11.
- In Claude Code, allow only `send_email` for this server; deny delete/filter tools.
- Smoke test early: Python client handshake + `list_tools` + one send to own Gmail.
- If #96 bites in Claude Code: document it as an "issue encountered" (T4.8), fix by prompt or a tiny patched fork.

Fallback: custom Python MCP server (FastMCP) exposing `send_email` with `gmail.send` scope only, full header control (`Date`, `References`), modern protocol. ~100 lines. Spec explicitly allows "build a custom one".

## Open decisions
- None.
