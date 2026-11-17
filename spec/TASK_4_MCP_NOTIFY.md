# Task 4: Send Notification Emails via MCP

Depends on: Task 3 flags, `EMAIL_TEMPLATE.md`.
Status: Not started.

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
- [ ] Gmail MCP server runs locally and is registered with the AI tool; `send_email` tool is visible.
- [ ] `mcp_config.json.example` committed; real config + credentials gitignored.
- [ ] Dry-run writes one `.eml` per flagged duplicate into `output/replies/`, each matching the template exactly.
- [ ] `--send-live` sends through MCP `send_email`, respecting the recipient policy and cap (D2).
- [ ] At least one live email received in our Gmail; screenshot / log excerpt saved for AI_USAGE.md.
- [ ] `output/send_log.csv` has one row per attempt with the 5 columns; failures included with error text.
- [ ] `notification_sent = 1` and `notification_date` set only on successful sends; a re-run skips already-notified groups.
- [ ] Send failures (bad token, network) are logged, not crashes.
- [ ] Example prompts used to drive the MCP `send_email` tool captured in `AI_USAGE_LOG.md`.

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
- D1: decided, see `01_OVERVIEW.md`.
- D2: decided, see `01_OVERVIEW.md`.
- D3: leaning GongRzhe 1.1.11 with the mitigations above; final call after smoke test at Task 4 start.
- Per-group vs per-flagged-email: spec says live notification per **group** (to the latest), but `.eml` drafts for **all flagged** duplicates. Proposal: follow both literally.
- How the template's `Date:` / `References:` headers survive a live send (`01_OVERVIEW.md` gotcha 4).
