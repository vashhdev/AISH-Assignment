-- SQLite schema for the Enron email pipeline.
--
-- Design:
--   emails            one row per parsed email (mandatory + optional fields, plus
--                     duplicate and notification state used by later stages)
--   addresses         every distinct email address, stored once
--   email_recipients  to / cc / bcc links between emails and addresses, in header order
--
-- Dates are ISO 8601 UTC text ('2001-05-14T23:39:00Z'): they sort correctly as
-- strings and SQLite's date functions read them directly.
-- from_address stays as text on emails: it is filtered, grouped and indexed on
-- directly (sender queries, duplicate detection groups by sender).
--
-- Safe to run more than once (IF NOT EXISTS everywhere).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS emails (
    id                INTEGER PRIMARY KEY,
    -- Mandatory fields
    message_id        TEXT    NOT NULL UNIQUE,          -- blocks exact duplicates on insert
    date              TEXT    NOT NULL,                 -- ISO 8601 UTC
    from_address      TEXT    NOT NULL,
    subject           TEXT    NOT NULL DEFAULT '',      -- may be blank in the source data
    body              TEXT    NOT NULL DEFAULT '',      -- sender's own text, forwarded/quoted parts split out
    source_file       TEXT    NOT NULL UNIQUE,          -- path relative to the dataset root
    -- Optional fields (NULL when absent)
    x_from            TEXT,
    x_to              TEXT,
    x_cc              TEXT,
    x_bcc             TEXT,
    x_folder          TEXT,
    x_origin          TEXT,
    content_type      TEXT,
    has_attachment    INTEGER NOT NULL DEFAULT 0 CHECK (has_attachment IN (0, 1)),
    forwarded_content TEXT,
    quoted_content    TEXT,
    headings          TEXT,                             -- one heading per line
    -- Duplicate detection state
    is_duplicate      INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate IN (0, 1)),
    duplicate_of      TEXT    REFERENCES emails (message_id),  -- message_id of the original
    similarity_score  REAL    CHECK (similarity_score IS NULL OR similarity_score BETWEEN 0 AND 100),
    -- Notification state
    notification_sent INTEGER NOT NULL DEFAULT 0 CHECK (notification_sent IN (0, 1)),
    notification_date TEXT,                             -- ISO 8601 UTC, set when the notification is sent
    CHECK (duplicate_of IS NULL OR is_duplicate = 1),
    CHECK (notification_date IS NULL OR notification_sent = 1)
);

CREATE TABLE IF NOT EXISTS addresses (
    id      INTEGER PRIMARY KEY,
    address TEXT NOT NULL UNIQUE                        -- bare, lowercased
);

CREATE TABLE IF NOT EXISTS email_recipients (
    email_id   INTEGER NOT NULL REFERENCES emails (id) ON DELETE CASCADE,
    address_id INTEGER NOT NULL REFERENCES addresses (id),
    kind       TEXT    NOT NULL CHECK (kind IN ('to', 'cc', 'bcc')),
    position   INTEGER NOT NULL,                        -- order within that header, from 0
    PRIMARY KEY (email_id, kind, position)
) WITHOUT ROWID;

-- Required indexes
CREATE INDEX IF NOT EXISTS idx_emails_date         ON emails (date);
CREATE INDEX IF NOT EXISTS idx_emails_from_address ON emails (from_address);
CREATE INDEX IF NOT EXISTS idx_emails_subject      ON emails (subject);
-- Supporting indexes
CREATE INDEX IF NOT EXISTS idx_recipients_address  ON email_recipients (address_id, kind);
CREATE INDEX IF NOT EXISTS idx_emails_duplicate_of ON emails (duplicate_of) WHERE duplicate_of IS NOT NULL;

-- Convenience view: recipients with the address text joined in
CREATE VIEW IF NOT EXISTS recipients AS
SELECT r.email_id, a.address, r.kind, r.position
FROM email_recipients AS r
JOIN addresses AS a ON a.id = r.address_id;
