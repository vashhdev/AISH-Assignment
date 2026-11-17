# AI Usage Log (raw notes)

Running journal, raw material for the final `AI_USAGE.md`. Append as we go; don't polish.

## Entry format
```
### <n>. <short title> (<task>)
- Prompt (quote or summary):
- Why structured this way:
- What the AI produced:
- Worked first time? If not: what broke, how fixed (prompt refinement vs manual edit):
- Who wrote what:
```

## Entries

### 1. Splitting the spec into per-task context files (Task 0)
- Prompt (summary): convert the assignment .docx into separate markdown files (overview, rules, one per task, the email template, deliverables) so each task can be worked on with only its own spec in context, and verified against its expected output before moving on. Asked the AI to raise architecture questions instead of deciding alone.
- Why structured this way: smaller, focused context per task (cheaper and less distraction), human stays in the loop on architecture, enforces a build -> check -> iterate loop.
- What the AI produced: `spec/` folder with acceptance checklists per task, an architecture decision log, and a list of dataset gotchas.
- Worked first time: (fill after review)
- Who wrote what: workflow and file-split idea = me; file content = AI, reviewed by me.

### 2. Verifying the spec split against the original doc (Task 0)
- Prompt (quote): "Also check all the files that we create against the original one so that we can make sure that we don't miss anything from the original doc."
- Why: AI summaries can silently drop requirements; a split spec is only useful if it is complete.
- What the AI did: converted the docx to plain text, wrote a small script that splits it into 148 sentences/table cells and finds the best-matching window in the spec files by token overlap, then flagged anything under 85% coverage for manual review. Also inspected docx headers, footers, footnotes and comments for hidden content (none).
- Result: 49 flagged on first pass. 4 real gaps fixed (allowed AI tool list, "representative subset" + "entire dataset not required", doc title/goal framing, "understand how you collaborate" line). Remaining 42 were paraphrase only.
- Who wrote what: the check request = me; script + review = AI.

### 3. Vetting the Gmail MCP server before committing to it (Task 4 prep)
- Prompt (summary): "this is what I found from my research ... GongRzhe/Gmail-MCP-Server, check if this is good and won't give any issues going forward, or we can choose something else later on together."
- Why: a bad MCP server choice found late would be costly on a 1-day deadline.
- What the AI did: pulled repo metadata via `gh api` (found it archived), read `send_email` schema and MIME builder in source, downloaded the published npm 1.1.11 build to confirm it matches source (it sets `References` via `inReplyTo`, contradicting open issue #66), checked the MCP protocol version of its SDK (`2024-11-05`) against the Python `mcp` 2.3.0 client's supported list, scanned top open issues (found #96: Claude Code passes arrays as strings).
- Result: keep it, pinned to 1.1.11, with mitigations; fallback = custom FastMCP server. Details in `TASK_4_MCP_NOTIFY.md`.
- Who wrote what: server pick = me; verification = AI.

### 4. Profile the data before writing the parser (Task 1)
- Approach: before any parser code, the AI streamed the tarball to count all 150 mailboxes (found every one of 517,401 files ends in `.`, which Windows drops), then profiled the chosen 23,554 files: header presence, date shapes, encodings, address oddities, body marker frequencies.
- Why: parser rules and the "what counts as a failure" decisions were made from real counts (1,171 missing To, 2,394 blank subjects, 32 placeholder dates, Bcc always equal to Cc) instead of guesses. I made the 4 policy calls with those numbers in front of me.
- Who: decisions = me; profiling scripts = AI.

### 5. Failure: profiler crashed on `Header` objects (Task 1)
- What broke: `TypeError: argument of type 'Header' is not iterable`. Python's `email` package returns `email.header.Header` objects instead of `str` when a header has non-ASCII bytes (8 files).
- Fix: parser splits header/body at byte level, decodes headers itself (UTF-8 -> cp1252 -> latin-1) and parses the decoded string, so every header is a `str`.

### 6. Failure: unit test caught silent wrong timezone (Task 1)
- What broke: `CEST` date came back 2 hours off. `email.utils.parsedate_to_datetime` does not raise on unknown abbreviations; it returns a naive datetime, which the first version labelled UTC.
- Fix: naive result -> re-parse with `dateutil` + explicit abbreviation table; still unknown -> fail with "unknown timezone" instead of guessing. Added a test for it.
- Lesson: the AI's first version looked right and the real data never hits this case; only a deliberately chosen test case exposed it.

### 7. Iteration: headings heuristic, two rounds on real output (Task 1)
- Round 1 output had filenames (`<<X20292.DOC>>`), separators read as underlines ("Leslie" + long dash line) and sentences.
- Round 2 top-60 list was dominated by `[IMAGE]` (365x) and salutations (`Jeff:`, `Dear Mr. Skilling:`).
- Fixes: underline must be 0.5x-1.5x the text length, skip file references, list lines, tab rows, salutations, and label lines that open a message; strip `[IMAGE]` placeholders. Regression test added with each noise case.

### 8. Failure: forwards classified as quoted replies (Task 1)
- Found in random 20-record spot-check: Outlook writes `-----Original Message-----` for forwards too (`FW: El Paso 1110` landed in quoted_content), and AOL forwards embed raw headers with no separator (`Fwd: Diplomatic Nominations` not split at all).
- Fix: ambiguous markers (Original Message, From/Sent, embedded header block) classified by subject prefix (`FW:`/`Fwd:` -> forwarded, else quoted). forwarded_content rose from 8.5% to 14.6%.

### 9. Git setup: commit history that follows the real work order (Task 0/1)
- Prompt (quote): "yes we can setup our git repo since it will better to see multiple commit history, let's do it" and "name it AISH Assignment".
- What the AI did: scanned the tree before the first commit (no personal email, no local paths, no secrets, no long dashes), kept the original brief docx out of git, then split the work so far into 5 commits in the order it was built (repo setup, spec, dataset, parser, extraction). Created a private GitHub repo only after asking.
- Bug found on the way: `Path.write_text` on Windows writes CRLF, so `error_log.txt` had mixed line endings. Fixed by writing with `newline="\n"` and adding `.gitattributes`.
- Who: repo name, visibility and commit cadence = me; checks + commits = AI.

### 10. Task 2 design: insert strategy and verifying the AI's own claims (Task 2)
- Decision (mine): separate `addresses` lookup table, chosen from two schema previews the AI showed side by side.
- AI choice worth noting: `ON CONFLICT (message_id) DO NOTHING` instead of the common `INSERT OR IGNORE`, because OR IGNORE also silently drops rows that break NOT NULL or CHECK constraints, which would hide loader bugs. Reruns also never touch existing rows, so notification state survives and a rerun cannot re-send email.
- Self-check: while writing the expected output for a sample query, the AI claimed two "Summer Interns" rows were the same email, then noticed their timestamps were 5 hours apart. It opened both raw files before keeping the claim: bodies identical, two different mailboxes, and the raw Date headers themselves differ by 5 hours (source data artifact, not a parser bug). That fed into the Task 3 notes.
- Verification beyond tests: recipient row counts per kind and distinct address count were recomputed from the parsed records and matched the DB exactly; `EXPLAIN QUERY PLAN` used to confirm the required indexes are actually used.

### 11. Task 3: profile first, then four decisions with numbers attached (Task 3)
- Approach: before writing dedup code, the AI ran the candidate algorithm on the real DB under three text choices (own body, full text, own body with full-text fallback) and two metrics, and measured tie frequency, empty-text groups, short texts and the 85-90 near-miss band. Each decision question then carried the measured counts (e.g. "body only forms 311 groups purely from two empty bodies", "96% of groups have identical timestamps").
- Decisions (mine): fallback text, folder-priority tie-break, follow the brief's rule for short texts, `fuzz.ratio`.
- Found by the AI while checking folder names: `_sent` is a fourth sent-folder name (261 emails) that the first draft of the priority list missed.
- Manual review beyond the checklist: sampled flagged pairs in the 90-99 band with different timestamps and found templated automated mail (overdue reminders, weekly reports, mail-merge greetings) flagged under the brief's rule. Kept the rule, documented as a limitation instead of silently changing the definition.
- Small slip: a scripted edit inserted the rapidfuzz pin under the dateutil comment in requirements.txt; caught on read-back and rewritten.

### 12. Task 4: MCP client in the pipeline, verified against the server's real behaviour (Task 4)
- Decisions (mine): literal template subject (keeps `Re: Re:`), commit all 8,484 drafts, live sends in report order, commit send_log.csv as-is.
- Smoke test before any code: the AI wrote a 15-line Python MCP client, spawned the pinned server over stdio and listed its tools (19, `send_email` schema as researched) before the OAuth sign-in existed.
- Found by reading the published server code, not the README: errors come back as ordinary text (`Error: ...`) without the MCP `isError` flag. A client that trusted `isError` would have logged failed sends as sent and marked them notified. Fixed by requiring the `Email sent successfully` prefix; a stand-in MCP server in the tests replies the same way, so the real client code path (stdio, handshake, tool call) is tested without Gmail.
- Failure on the way: the test server first used `FastMCP`, which `mcp` 2.x renamed to `MCPServer`; the import error message named the fix.
- Safety designed in, not bolted on: live recipient from `.env` only, refused for @enron.com or any address in the DB, `--limit` cap, DB marked only after a confirmed send. First live run used `--limit 1`; I checked the received email and its headers ("Show original": In-Reply-To and References correct) before sending 4 more.
- Sign-in: I ran `npx -y @gongrzhe/server-gmail-autoauth-mcp@1.1.11 auth` myself; the token stays in `~/.gmail-mcp/`, outside the repo.
- Small slip: one long shell heredoc for the doc updates failed to parse; moved the edit script into a file and reran.
- Who: decisions, OAuth setup, inbox checks = me; client code, tests, server-code reading = AI.

### 13. Prompting Claude Code to use the MCP send_email tool directly (Task 4)
- Setup: `claude mcp add gmail --scope local -- npx -y @gongrzhe/server-gmail-autoauth-mcp@1.1.11`, then `.claude/settings.local.json` denying the 18 non-send Gmail tools, so `send_email` is the only usable one (it still asks for approval each time). Session restarted so the new server was loaded.
- Prompt (verbatim): "Use the gmail MCP server's send_email tool to send the duplicate notice in output/replies/348269.1075840857152.JavaMail.evans@thyme.eml to <my-gmail> instead of the Enron address in its To header. Keep the subject and body exactly as in the file, and pass the file's References value as inReplyTo."
- Why structured this way: points at a generated draft so the content is the pipeline's, not invented by the AI; names the tool explicitly; overrides the recipient explicitly (safety); asks for exact subject/body; maps the template's References header to the tool's `inReplyTo` parameter.
- Result: the AI read the .eml, loaded the tool, and called `send_email` with `to` as a real array, the exact subject/body and `inReplyTo`. Server replied "Email sent successfully with ID: 1a1e7ebb98bf2fec". Worked first time; the known issue #96 (arrays passed as strings) did not occur.
