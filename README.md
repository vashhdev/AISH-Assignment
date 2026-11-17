# AISH Assignment: Enron Email Pipeline

Raw Enron maildir files -> parsed, validated records -> normalized SQLite database -> fuzzy duplicate detection -> duplicate notification emails, drafted as `.eml` files and sent live through a Gmail MCP server.

One command runs everything: `python main.py`.

| Stage | Result on the 5-mailbox subset |
|---|---|
| Extraction | 23,554 files found, 22,352 parsed (94.9%), 1,202 failures logged with reasons |
| Database | 22,352 emails, 11,739 distinct addresses, 164,473 recipient links |
| Duplicates | 3,939 groups, 8,484 emails flagged, average group size 3.15 |
| Notifications | 8,484 draft `.eml` files; 5 live sends through the Gmail MCP server, all delivered |
| Tests | 65 passing (`python -m pytest`) |

How AI tools were used to build this is documented in [`AI_USAGE.md`](AI_USAGE.md).

---

## Contents
1. [Setup](#setup)
2. [Running](#running)
3. [Gmail MCP server setup](#gmail-mcp-server-setup) (only needed for `--send-live`)
4. [Architecture](#architecture)
5. [Dataset subset](#dataset-subset)
6. [Task 1: extraction](#task-1-extraction)
7. [Task 2: database](#task-2-database)
8. [Task 3: duplicate detection](#task-3-duplicate-detection)
9. [Task 4: notifications](#task-4-notifications)
10. [Dataset quirks found along the way](#dataset-quirks-found-along-the-way)
11. [Deliverables map](#deliverables-map)

---

## Setup

Prerequisites: Python 3.10+ (built with 3.11.9), git. Node.js 18+ only for live sending (the Gmail MCP server runs through `npx`).

```bash
git clone <repo-url>
cd AISH-Assignment
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

Dependencies (all open source): `python-dateutil` (timezone abbreviations in Date headers), `rapidfuzz` (fuzzy matching, MIT), `mcp` (official MCP Python SDK, used as the client), `pytest`.

The dataset is downloaded automatically on the first run (443 MB, from `https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz`) into `data/`, which is gitignored. To skip the download, place the tarball at `data/enron_mail_20150507.tar.gz` yourself. Only the 5 chosen mailboxes are extracted (about 50 s); later runs skip both steps.

## Running

```bash
python main.py                        # full pipeline, dry run: drafts only, nothing is sent
python main.py --send-live            # also send up to 5 notifications via the Gmail MCP server
python main.py --send-live --limit 1  # cap live sends for this run (1-50)
python main.py --reset-db             # rebuild the database from scratch
python -m enron_pipeline.queries      # run sample_queries.sql, expected vs actual side by side
python -m pytest                      # 65 tests
```

A full dry run takes about 15 s after the dataset is extracted. Every stage prints its statistics and writes them to `output/`.

Re-running is safe. The database load skips emails already stored, duplicate detection clears and recomputes its flags, and live mode skips groups that were already notified, so a rerun never re-sends.

## Gmail MCP server setup

Only needed for `--send-live`. The server is [GongRzhe/Gmail-MCP-Server](https://github.com/GongRzhe/Gmail-MCP-Server), pinned to npm version `1.1.11`. Why this server and what we checked before using it: [`AI_USAGE.md`](AI_USAGE.md#6-mcp-integration).

1. **Google Cloud OAuth client.** In the Google Cloud Console: create a project, enable the Gmail API, configure the OAuth consent screen (External, add your Gmail address as a test user), then create an OAuth client ID of type **Desktop app** and download its JSON.
2. **Place the keys** at `~/.gmail-mcp/gcp-oauth.keys.json` (outside the repo). The expected structure, with values redacted, is in [`gcp-oauth.keys.json.example`](gcp-oauth.keys.json.example).
3. **Sign in once** (opens a browser, needs port 3000 free):
   ```bash
   npx -y @gongrzhe/server-gmail-autoauth-mcp@1.1.11 auth
   ```
   Google shows "app not verified" for a personal OAuth client: Advanced -> continue. The token is saved to `~/.gmail-mcp/credentials.json`.
4. **Set the live recipient.** Copy `.env.example` to `.env` (gitignored) and set `NOTIFY_LIVE_TO` to your own address. Live mode refuses any `@enron.com` address and any address that appears in the dataset.
5. **Optional:** copy [`mcp_config.json.example`](mcp_config.json.example) to `mcp_config.json` (gitignored) to point at keys/token files in other locations. Without it the pipeline launches the pinned server with the default `~/.gmail-mcp/` paths.
6. **Send:** `python main.py --send-live --limit 1`, check your inbox, then raise the limit.

**Registering the same server with Claude Code** (to call `send_email` from a prompt):
```bash
claude mcp add gmail --scope local -- npx -y @gongrzhe/server-gmail-autoauth-mcp@1.1.11
```
The server exposes 19 tools, including delete and filter tools. We denied the 18 non-send tools in `.claude/settings.local.json` (`permissions.deny`: `mcp__gmail__delete_email`, `mcp__gmail__read_email`, ...), leaving `send_email` as the only usable tool, still approved per call. A server added this way is visible only in Claude Code sessions started afterwards.

## Architecture

```
data/maildir/<5 mailboxes>/...
   |  dataset.py   stream tarball, extract chosen mailboxes (fixes trailing-dot filenames)
   v
   |  extract.py   discover files -> parser.py (+ body_split.py, headings.py) per file
   |               -> error_log.txt, output/extraction_stats.json
   v
output/enron.db  (schema.sql)
   |  database.py  idempotent insert: emails, addresses, email_recipients
   |               -> output/db_stats.json            queries.py -> sample_queries.sql
   v
   |  dedup.py     block by sender + normalized subject, rapidfuzz >= 90, flag in DB
   |               -> duplicates_report.csv, output/dedup_stats.json
   v
   |  notify.py    dry run: output/replies/*.eml (one per flagged email)
                   --send-live: Python MCP client -> npx Gmail MCP server -> send_email
                   -> output/send_log.csv, emails.notification_sent / notification_date
```

| Module | Responsibility |
|---|---|
| `main.py` | Single entry point and CLI flags |
| `enron_pipeline/config.py` | Paths, dataset URL, chosen mailboxes |
| `enron_pipeline/dataset.py` | Download, streaming extraction with path sanitization |
| `enron_pipeline/parser.py` | One raw file -> `EmailRecord` or `ParseError` with all reasons |
| `enron_pipeline/body_split.py` | Splits own text from forwarded and quoted content |
| `enron_pipeline/headings.py` | Heading heuristic for plain-text bodies |
| `enron_pipeline/extract.py` | Traversal, failure log, completeness statistics |
| `enron_pipeline/database.py` | Schema creation and idempotent load |
| `enron_pipeline/queries.py` | Runs `sample_queries.sql` with expected-output notes |
| `enron_pipeline/dedup.py` | Duplicate groups, flags, report |
| `enron_pipeline/notify.py` | Template rendering, `.eml` drafts, MCP client and live-send safety |

Design principles:
- **Never crash on bad input.** Every file is parsed inside a catch-all; failures carry the file path and every reason found (not just the first).
- **Idempotent stages.** Each stage can be rerun without duplicating rows, flags or emails.
- **Safety first for live email.** Recipient override, dataset-address refusal, per-run cap, DB marked only after the server confirms.
- **Standard library first.** `email`, `sqlite3`, `csv`, `tarfile`, `logging`; a dependency only where it clearly earns its place.

## Dataset subset

5 mailboxes, 23,554 files (2.3x the 10,000 minimum):

| Mailbox | Person | Role | Files |
|---|---|---|---|
| `lay-k` | Kenneth Lay | CEO / Chairman | 5,937 |
| `skilling-j` | Jeff Skilling | CEO | 4,139 |
| `kitchen-l` | Louise Kitchen | President, EnronOnline | 5,546 |
| `arnold-j` | John Arnold | Gas trader | 4,898 |
| `allen-p` | Phillip Allen | Gas trader | 3,034 |

Why these: a mix of roles (executives with heavy inbound mail and assistants writing on their behalf, traders with terse high-volume mail) and of mailbox styles. Four use Lotus Notes folders (`all_documents`, `discussion_threads`, `sent` + `_sent_mail`), which store the same email several times and give duplicate detection real work; `kitchen-l` is Outlook only, a useful contrast (7.7% flagged vs 40-60% for the others). Mailbox sizes were counted for all 150 mailboxes straight from the tarball before choosing.

## Task 1: extraction

**Fields.** Mandatory: `message_id`, `date` (UTC), `from_address`, `to_addresses`, `subject`, `body`, `source_file`. Optional: `cc_addresses`, `bcc_addresses`, `x_from`, `x_to`, `x_cc`, `x_bcc`, `x_folder`, `x_origin`, `content_type`, `has_attachment`, `forwarded_content`, `quoted_content`, `headings`.

**Failure policy** (a record missing any mandatory field is not stored; it is logged):

| Case | Rule |
|---|---|
| Missing `To` header | Fail (1,171 files: bulk mail, calendar items), reason includes the X-To hint |
| `To` present but no valid address | Fail |
| Blank subject (header present) | Accepted as `""` (2,394 files); fail only if the header is absent |
| Placeholder or implausible date | Fail: `1980-01-01 00:00 UTC` (DOS epoch placeholder, 32 files) or outside 1990-2010 |
| Empty raw body | Fail. A body that is only a forward or quote is kept, with `body = ""` |
| Garbage address tokens (no `@`) | Dropped and counted; Enron artifacts like `'.hall@enron.com'` kept as written |

Result: 22,352 parsed; 1,202 failures in `error_log.txt` (1,171 missing To, 32 placeholder dates, 1 truncated From). Zero unexpected errors.

**Parsing details**
- Headers are decoded at byte level (UTF-8, then cp1252, then latin-1) before parsing, because Python's `email` package otherwise returns `Header` objects for non-ASCII header bytes. Folded multi-line headers are unfolded; RFC 2047 encoded words decoded; quoted-printable and base64 bodies decoded.
- Dates are normalized to UTC. Unknown timezone abbreviations fail loudly instead of being silently treated as UTC (the standard library returns a naive datetime for e.g. `CEST`; a test caught this).
- Addresses are bare and lowercased; duplicates within one header removed.
- **Body splitting** (`body_split.py`): the earliest forward or reply marker splits the body. Forward markers (`----- Forwarded by`, `Begin forwarded message:`) -> `forwarded_content`. Lotus reply headers (`Name` / date line / `To:`) -> `quoted_content`. Ambiguous markers (`-----Original Message-----`, an Outlook `From:`/`Sent:` block, an embedded AOL header block) are classified by the subject: `FW:`/`Fwd:` -> forwarded, otherwise quoted. Inline `>` lines before the marker go to `quoted_content`; the rest is the sender's own `body`.
- **`has_attachment`**: every Content-Type in the data is `text/plain`, so attachments are inferred from body evidence: `<<File: ...>>` and `<<name.ext>>` references, ` - name.ext` lines, or the words attached/attachment.

**Headings heuristic** (`headings.py`). Plain text has no markup, so a line (max 80 chars) counts as a heading by layout:
1. Banner: text framed by runs of `= * - _ ~ # +`.
2. Underlined: followed by a rule line of roughly the same length (0.5x to 1.5x); longer rules are separators.
3. ALL CAPS: at least 3 letters, at most 10 words, no sentence punctuation, not a lone sign-off (THANKS, FYI, ...).
4. Label: alone after a blank line, at most 6 words, ends with `:`, and not opening a message (there `Jeff:` is a salutation).
5. Numbered section title: `1. Overview`, `II) Background`.

Never headings: embedded mail headers, URLs and addresses, `>` quotes, list lines, tab-separated rows, salutations, separator lines, attachment references; `[IMAGE]` placeholders are stripped first. Tuned over two review rounds on real output; residual noise is signature lines such as `ENRON`. 14.2% of emails have headings.

## Task 2: database

SQLite, schema in [`schema.sql`](schema.sql), database at `output/enron.db` (66 MB, gitignored, rebuilt by `python main.py`).

- `emails`: one row per email. `message_id` UNIQUE, `source_file` UNIQUE, all optional fields, plus `is_duplicate`, `duplicate_of` (FK to `emails.message_id`), `similarity_score`, `notification_sent`, `notification_date`. CHECK constraints keep flags 0/1 and `duplicate_of` / `notification_date` consistent with their flags.
- `addresses`: every distinct address once. `email_recipients(email_id, address_id, kind IN ('to','cc','bcc'), position)`: recipients in header order, no comma-joined strings anywhere. View `recipients` joins the address text back in.
- Indexes on `date`, `from_address`, `subject` (required), plus recipient address and a partial index on `duplicate_of`. `EXPLAIN QUERY PLAN` confirms the date range, sender and subject queries use them.
- Dates are ISO 8601 UTC text (`2001-05-14T23:39:00Z`): they sort as strings and SQLite date functions read them.
- `from_address` stays as text on `emails` because it is indexed and grouped on directly.
- Load: `INSERT ... ON CONFLICT (message_id) DO NOTHING` in one transaction (1.2 s). Unlike `INSERT OR IGNORE`, this swallows only the message_id clash, so NOT NULL or CHECK bugs still raise.

[`sample_queries.sql`](sample_queries.sql) has 12 queries, each with its expected output recorded on this subset: emails per sender, date ranges, CC recipients, recipient lists, top recipients, subject lookup, a Bcc data check, and duplicate summaries. `python -m enron_pipeline.queries` prints expected and actual side by side.

## Task 3: duplicate detection

**Rule** (from the brief): same `from_address`, same subject after removing Re:/Fw:/Fwd: prefixes, and body similarity >= 90%. The earliest email is the original; every later member is flagged (`is_duplicate = 1`, `duplicate_of` = original's message_id); the latest is the notification target.

**Implementation** (`dedup.py`):
1. Block emails by (sender, normalized subject). Normalization strips leading stacked prefixes in any case (`Re: FW: re[2]: Fwd :`), collapses whitespace and casefolds.
2. Order each block original-first (see tie-break).
3. Anchor clustering: each email is compared with the original of every group already formed in its block and joins the best match at >= 90; otherwise it starts a group. Scores are always against the original, so every flagged email is within 90% of the email it is reported against (similarity is not transitive).

**Fuzzy library: `rapidfuzz` (`fuzz.ratio`).** MIT licensed, a C++ implementation of normalized Indel similarity (0-100), word-order aware, and fast enough to need no sampling (detection runs in about 1.5 s). `token_sort_ratio` was measured too: 8,467 vs 8,484 flagged, so the stricter, order-aware score was kept.

**Text compared:** the sender's own body, whitespace-normalized. If it is empty (pure forward or reply), the full text (body + forwarded + quoted) is used instead. Measured alternatives: own body only forms 311 groups purely from two empty bodies; full text lets long shared quoted threads push different replies over 90%.

**Tie-break.** 96% of groups have identical timestamps (the same email stored in several folders), so order is `(date, folder rank, source_file)`. Folder rank: sent folders (`sent`, `_sent`, `_sent_mail`, `sent_items`) < inbox folders < user folders < Lotus Notes views (`all_documents`, `discussion_threads`) < `deleted_items`. The original is the copy in the folder where the mail actually lives; view and trash copies are the duplicates. Deterministic and independent of load order.

**Results:** 3,939 groups, 8,484 flagged (7,980 at 100%, 504 at 90-99.99), average group size 3.15, largest 28 (a daily "Approval is Overdue" reminder). Report: [`duplicates_report.csv`](duplicates_report.csv), one row per flagged email, in the brief's 7 columns. Rerunning gives a byte-identical report.

**Known limitations**
- Templated automatic mail is flagged when only a number or name changes ("overdue 5 days" vs "55 days", weekly reports for consecutive weeks, mail-merge greetings). Body similarity cannot tell these from re-sends; the brief's rule flags them, and we kept the rule as written.
- Short notes with a long shared signature score high on the signature alone.
- 68 flagged pairs have under 40 characters of text, e.g. a one-line note sent twice, two weeks apart, with a blank subject.
- Recipients are not part of the rule, so one note sent separately to different people forms a group.
- "Latest" follows the raw timestamps, which are skewed between some folders (see quirks).

## Task 4: notifications

**Template** (followed literally; tested against the exact text):
- `Subject: [Duplicate Notice] Re: <original subject>`: the original subject is inserted as stored, so `Re: Re: ...` (1,383 groups) and a trailing `Re: ` for blank subjects (468) are kept rather than rewritten.
- `Date`, and both `Date Sent` lines: RFC 2822 in UTC. `References`: the flagged email's Message-ID (not double-wrapped). Similarity: two decimals, as in the report.

**Dry run (default):** one `.eml` per flagged duplicate in `output/replies/` (8,484 files, named by Message-ID). Stale drafts are removed on each run.

**Live (`--send-live`):** one notification per duplicate group, about its latest duplicate, in report order. Python acts as the MCP client: it spawns the server over stdio (official `mcp` SDK), checks `send_email` is offered, and calls it with `to`, `subject`, `body` and `inReplyTo` (the server turns that into both `In-Reply-To` and `References`). Safety rails:
- Mail goes only to `NOTIFY_LIVE_TO`; @enron.com and any dataset address are refused before anything is sent. The intended Enron recipient is recorded in the log.
- At most `--limit` groups per run (default 5, max 50); groups already notified are skipped.
- A send counts as successful only when the server replies `Email sent successfully`. This server reports failures as ordinary text without the MCP `isError` flag, so trusting the flag would mark failed sends as sent.
- `notification_sent` / `notification_date` are set right after each confirmed send, so a crash mid-run cannot cause a re-send.
- Server start-up failures, error replies and timeouts become `failed` rows in the log; nothing is raised.

[`output/send_log.csv`](output/send_log.csv): `timestamp, recipient, subject, status, error` (the required columns), then `intended_recipient, flagged_message_id`.

Tests drive the real MCP client over stdio against a stand-in server (`tests/fake_gmail_mcp.py`) that replies the way the real one does, covering success, error text, a missing server, the limit, and the recipient guard.

## Dataset quirks found along the way

- **Trailing dots.** Every one of the 517,401 filenames in the archive ends in `.`, which Windows silently drops. Extraction strips trailing dots and spaces per path component (`1.` -> `1`) and blocks path traversal, so paths match the documented form `maildir/lay-k/inbox/45`.
- **Bcc mirrors Cc.** In all 4,760 emails with a Bcc header, it is identical to Cc (a conversion artifact). Bcc is still stored as given; sample query Q9 demonstrates it.
- **Skewed timestamps.** Copies of the same email in different folders sometimes differ by exactly 5, 10 or 12 hours in their raw Date headers (e.g. `lay-k/inbox/33` vs `kitchen-l/_americas/hr/216`). Not a parsing error; duplicate ordering follows the raw values.
- **Placeholder dates.** 32 emails are dated `1979-12-31 16:00 PST`, i.e. `1980-01-01 00:00 UTC`, the DOS epoch. Treated as invalid.
- **Synthetic Message-IDs.** Every stored copy has its own Message-ID, so exact-ID deduplication finds nothing (0 collisions) and all duplicates come from fuzzy matching.
- **Same person, several addresses.** `kenneth.lay@enron.com` and `klay@enron.com`; addresses like `k..allen@enron.com`. Stored as written.

## Deliverables map

| Deliverable | Location |
|---|---|
| Source code | `main.py`, `enron_pipeline/`, `tests/` |
| README | this file |
| AI usage documentation (incl. MCP section) | [`AI_USAGE.md`](AI_USAGE.md) |
| Schema with `is_duplicate`, `duplicate_of`, `notification_sent`, `notification_date` | [`schema.sql`](schema.sql) |
| Sample queries with expected outputs | [`sample_queries.sql`](sample_queries.sql) |
| MCP config template | [`mcp_config.json.example`](mcp_config.json.example) (+ `gcp-oauth.keys.json.example`, `.env.example`) |
| Draft replies for all flagged duplicates | [`output/replies/`](output/replies) |
| Live send log | [`output/send_log.csv`](output/send_log.csv) |
| Duplicates report | [`duplicates_report.csv`](duplicates_report.csv) |
| Parse failure log | [`error_log.txt`](error_log.txt) |
| Dependencies | [`requirements.txt`](requirements.txt) |

Also included: `spec/`, the working spec the project was built from (the brief split into one file per task, with acceptance checklists, the architecture decision log and the raw AI usage journal), and run statistics in `output/*.json`.
