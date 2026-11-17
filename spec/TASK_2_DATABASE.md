# Task 2: Database Storage

Depends on: Task 1 records, `02_FIELDS.md`.
Status: Not started.

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
- `schema.sql`
- Loader that creates the DB from `schema.sql` and inserts Task 1 records.
- `sample_queries.sql` (>= 3 queries, each with an expected-output description comment).

## Draft shape (confirm in this task)
- `emails`: one row per email. Scalar mandatory + optional fields, `source_file`, `is_duplicate` (default 0), `duplicate_of` (references `emails.message_id`, NULL by default), `notification_sent` (default 0), `notification_date` (NULL), maybe `similarity_score`.
- `email_recipients`: `(email_id, address, kind IN ('to','cc','bcc'), position)`. Optionally an `addresses` lookup table if we normalize further.
- Indexes: `date`, `from_address`, `subject` (+ recipient address, + maybe normalized subject for Task 3).
- Insert with `INSERT OR IGNORE` (or catch `IntegrityError`) on `message_id`; count skipped exact duplicates.

## Acceptance checklist
- [ ] `schema.sql` runs clean on a fresh DB.
- [ ] Recipients live in a related table; no comma-joined address strings in `emails`.
- [ ] Re-running the load creates no duplicate rows (unique `message_id` proven).
- [ ] Indexes on `date`, `from_address`, `subject` exist (check with `PRAGMA index_list`).
- [ ] The 4 required columns exist with sensible defaults.
- [ ] Row count in DB == parsed count from Task 1, minus exact `message_id` duplicates (which are counted and reported).
- [ ] `sample_queries.sql` has >= 3 queries; each runs and its output matches its description.
- [ ] Load time reasonable (batched inserts inside transactions).

## Open decisions
- Separate `addresses` table, or address text directly in `email_recipients`?
- `date` stored as ISO 8601 UTC text (SQLite convention) unless there is a reason not to.
