# Task 2: Database Storage

Depends on: Task 1 records, `02_FIELDS.md`.
Status: Done (2026-11-16). All acceptance items pass. Code: `schema.sql`, `enron_pipeline/database.py`, `sample_queries.sql`, `enron_pipeline/queries.py`, `tests/test_database.py`.

## Requirements (spec)
Design and implement a local database to store the extracted data:

| ID | Requirement |
|---|---|
| T2.1 | Use SQLite or PostgreSQL (local). Provide the schema as a `.sql` file or migration script. |
| T2.2 | The schema must properly normalize the data, e.g. email addresses in to/cc/bcc stored in a related table, not as comma-separated strings. |
| T2.3 | Unique constraint on `message_id` to prevent exact duplicates on insert. |
| T2.4 | Indexes on `date`, `from_address`, and `subject` for efficient querying. |
| T2.5 | At least 3 sample queries that demonstrate the DB works (e.g. count emails per sender, find all emails in a date range, find emails with CC recipients). |

From Deliverables: `schema.sql` must include `is_duplicate`, `duplicate_of`, `notification_sent`, `notification_date` columns. `sample_queries.sql` must include expected output descriptions.

## Outputs
- `schema.sql` (repo root)
- Loader `enron_pipeline/database.py`: creates `output/enron.db` from `schema.sql`, inserts Task 1 records, writes `output/db_stats.json`. Wired into `python main.py` (`--reset-db` rebuilds).
- `sample_queries.sql` (repo root): 9 queries, each with an expected-output comment. Runner: `python -m enron_pipeline.queries`.

## Final shape
- `emails`: one row per email. Mandatory + optional scalar fields, `source_file` (UNIQUE), `message_id` (UNIQUE), `is_duplicate` (0), `duplicate_of` (FK to `emails.message_id`, NULL), `similarity_score` (NULL, 0-100), `notification_sent` (0), `notification_date` (NULL). CHECKs: flags are 0/1, `duplicate_of` only when `is_duplicate = 1`, `notification_date` only when `notification_sent = 1`.
- `addresses(id, address UNIQUE)`: each distinct address once.
- `email_recipients(email_id, address_id, kind IN ('to','cc','bcc'), position)`, PK `(email_id, kind, position)`, WITHOUT ROWID.
- View `recipients`: recipients with address text joined in.
- Indexes: `date`, `from_address`, `subject` (required); `email_recipients(address_id, kind)`; partial index on `duplicate_of`.
- Insert: `INSERT ... ON CONFLICT (message_id) DO NOTHING`. Only the message_id clash is swallowed (unlike `INSERT OR IGNORE`, which would also hide NOT NULL / CHECK bugs). Existing rows are never touched, so reruns keep duplicate flags and notification history (no accidental re-sends).

## Acceptance checklist
- [x] `schema.sql` runs clean on a fresh DB, and again on an existing one (`test_schema_is_rerunnable`).
- [x] Recipients live in a related table; `emails` has no address-list columns; 0 stored addresses contain a comma.
- [x] Re-running the load creates no duplicate rows: rerun on the real data inserted 0, 22,352 "already in DB"; test also proves notification state survives.
- [x] Indexes on `date`, `from_address`, `subject` exist (`PRAGMA index_list`/`index_info` in test). `EXPLAIN QUERY PLAN` confirms Q1/Q2/Q8 use them.
- [x] The 4 required columns exist with defaults 0/NULL (test checks `PRAGMA table_info` + a loaded row).
- [x] Row count 22,352 == Task 1 parsed 22,352, minus 0 exact `message_id` duplicates (counted in `db_stats.json`; in-batch duplicates tested).
- [x] Recipient rows per kind equal the parsed list lengths (to 121,737, cc 21,368, bcc 21,368); 11,739 distinct addresses match; `PRAGMA foreign_key_check` empty, `integrity_check` ok.
- [x] `sample_queries.sql` has 9 queries; each ran on the real DB and matched its description; test runs all of them.
- [x] Load time: 1.2 s for 22,352 emails (one transaction).
- [x] Spot check: `kitchen-l/sent_items/987` raw headers match its DB row and recipients (Q6).

## Decisions (2026-11-16, with user)
| Topic | Rule |
|---|---|
| Address normalization | Separate `addresses` lookup table; recipients link by id. `from_address` stays text on `emails` (required index, Task 3 groups by it). |
| Date storage | ISO 8601 UTC text `YYYY-MM-DDTHH:MM:SSZ`: sorts as text, SQLite date functions read it. |
| DB file | `output/enron.db`, gitignored (66 MB). Rebuilt by `python main.py`. |
| Reruns | Idempotent; `--reset-db` deletes the DB (warns that flags and notification history go). |

## Findings for later tasks
- Same email in two mailboxes with different message_ids and Date headers exactly 5 h apart in the raw files (`lay-k/inbox/33` vs `kitchen-l/_americas/hr/216`). Task 3 "latest = duplicate" will follow those raw timestamps.
- 1,124 "Demand Ken Lay Donate Proceeds..." emails from 1,116 senders: same subject, different senders, so not duplicates under the brief's rule.
- 914 emails have subject exactly `Re:`/`RE:` (empty after prefix normalization). Task 3 must decide how to group those.
- `kenneth.lay@` and `klay@` are the same person; kept separate (stored as written).

## Open decisions
- None.
