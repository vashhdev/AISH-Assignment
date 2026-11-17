-- Sample queries for output/enron.db (schema: schema.sql).
--
-- Run all of them with:   python -m enron_pipeline.queries
-- or one at a time with any SQLite client.
--
-- Expected outputs below were recorded on the 5-mailbox subset after a full `python main.py` run
-- (lay-k, skilling-j, kitchen-l, arnold-j, allen-p): 22,352 emails loaded.
-- Dates are ISO 8601 UTC text, so ranges are plain string comparisons that use idx_emails_date.


-- Q1. Count emails per sender (top 10).
-- Uses idx_emails_from_address (covering index scan, no table reads).
-- Expected output: 10 rows (from_address, emails), largest first:
--   john.arnold@enron.com 3477, phillip.allen@enron.com 2112, louise.kitchen@enron.com 1162,
--   rosalee.fleming@enron.com 859, sherri.sera@enron.com 670, ... ending with david.forster@enron.com 144.
--   Rosalee Fleming and Sherri Sera were the assistants to Ken Lay and Jeff Skilling, which is
--   why they outrank the executives themselves.
SELECT from_address, COUNT(*) AS emails
FROM emails
GROUP BY from_address
ORDER BY emails DESC, from_address
LIMIT 10;


-- Q2. Find all emails in a date range: 2 to 3 December 2001 (UTC). Enron filed for bankruptcy
--     on Sunday 2 December; this covers that day and the next.
-- Uses idx_emails_date (range search).
-- Expected output: 59 rows (date, from_address, subject), oldest first, all dated
--   2001-12-02T.. or 2001-12-03T.. .
SELECT date, from_address, subject
FROM emails
WHERE date >= '2001-12-02T00:00:00Z'
  AND date <  '2001-12-04T00:00:00Z'
ORDER BY date, id;


-- Q3. Monthly email volume in 2001 (date range + grouping).
-- Expected output: 12 rows (month, emails) from 2001-01 (484) to 2001-12 (834).
--   October 2001 is the peak with 2327 emails, the month Enron reported its third-quarter loss
--   and the SEC inquiry became public.
SELECT substr(date, 1, 7) AS month, COUNT(*) AS emails
FROM emails
WHERE date >= '2001-01-01T00:00:00Z'
  AND date <  '2002-01-01T00:00:00Z'
GROUP BY month
ORDER BY month;


-- Q4. How many emails have CC recipients?
-- Expected output: 1 row, emails_with_cc = 4651 (about 21% of loaded emails).
SELECT COUNT(*) AS emails_with_cc
FROM emails AS e
WHERE EXISTS (
    SELECT 1 FROM email_recipients AS r
    WHERE r.email_id = e.id AND r.kind = 'cc'
);


-- Q5. Emails with CC recipients, most CC'd first (top 10).
-- Expected output: 10 rows (date, from_address, subject, cc_count). First row:
--   2001-10-05T18:30:39Z, jan_levine@travisintl.com, "Program Date Change", 171 CC recipients.
--   Rows 2 and 3 are the same "Analyst & Associate Program - Summer Interns" email from
--   billy.lemmons@enron.com (102 CCs each, identical body), stored in two mailboxes
--   (lay-k and kitchen-l) with different message_ids. Their raw Date headers differ by exactly
--   5 hours, a timestamp artifact in the source data. Duplicate detection has to catch pairs like this.
SELECT e.date, e.from_address, e.subject, COUNT(*) AS cc_count
FROM emails AS e
JOIN email_recipients AS r ON r.email_id = e.id AND r.kind = 'cc'
GROUP BY e.id
ORDER BY cc_count DESC, e.date
LIMIT 10;


-- Q6. All recipients of one email, in header order (shows the normalized recipient tables).
-- Expected output: 6 rows (kind, position, address) for Louise Kitchen's "LNG people" email:
--   to 0 wes.colwell@enron.com, to 1 faith.killen@enron.com,
--   cc 0 robert.virgo@enron.com, cc 1 mike.coleman@enron.com,
--   bcc 0 robert.virgo@enron.com, bcc 1 mike.coleman@enron.com.
--   The Bcc list repeating the Cc list is a known artifact of the dataset (see Q9).
SELECT r.kind, r.position, r.address
FROM recipients AS r
JOIN emails AS e ON e.id = r.email_id
WHERE e.message_id = '<26051316.1075853021755.JavaMail.evans@thyme>'
ORDER BY CASE r.kind WHEN 'to' THEN 0 WHEN 'cc' THEN 1 ELSE 2 END, r.position;


-- Q7. Who receives the most email (top 10 To recipients).
-- Uses idx_recipients_address.
-- Expected output: 10 rows (address, emails_received), led by louise.kitchen@enron.com 3931,
--   kenneth.lay@enron.com 2433, jeff.skilling@enron.com 2134, klay@enron.com 1912.
--   kenneth.lay@ and klay@ are two addresses for the same person; they are kept separate
--   because addresses are stored exactly as written in the headers.
SELECT a.address, COUNT(DISTINCT r.email_id) AS emails_received
FROM email_recipients AS r
JOIN addresses AS a ON a.id = r.address_id
WHERE r.kind = 'to'
GROUP BY a.id
ORDER BY emails_received DESC, a.address
LIMIT 10;


-- Q8. Exact subject lookup: the January 2002 "Demand Ken Lay Donate Proceeds" campaign.
-- Uses idx_emails_subject (equality search).
-- Expected output: 1 row: emails 1124, distinct_senders 1116, first 2002-01-29T23:30:00Z,
--   last 2002-01-30T19:48:06Z. Same subject, but almost every copy has a different sender,
--   so these are NOT duplicates under the brief's rule (which requires the same sender).
SELECT COUNT(*) AS emails,
       COUNT(DISTINCT from_address) AS distinct_senders,
       MIN(date) AS first,
       MAX(date) AS last
FROM emails
WHERE subject = 'Demand Ken Lay Donate Proceeds from Enron Stock Sales';


-- Q9. Data-quality check: does every Bcc entry just repeat the Cc entry at the same position?
-- Expected output: 1 row: cc_rows 21368, bcc_rows 21368, bcc_rows_not_matching_cc 0.
--   In this dataset the Bcc header always mirrors Cc (a conversion artifact). Bcc is still
--   stored as given, because the brief asks for it as a captured field.
SELECT
    (SELECT COUNT(*) FROM email_recipients WHERE kind = 'cc')  AS cc_rows,
    (SELECT COUNT(*) FROM email_recipients WHERE kind = 'bcc') AS bcc_rows,
    (SELECT COUNT(*)
     FROM email_recipients AS b
     WHERE b.kind = 'bcc'
       AND NOT EXISTS (
           SELECT 1 FROM email_recipients AS c
           WHERE c.email_id = b.email_id AND c.kind = 'cc'
             AND c.position = b.position AND c.address_id = b.address_id
       )) AS bcc_rows_not_matching_cc;


-- Q10. Duplicate detection summary (after `python main.py` has run duplicate detection).
-- Expected output: 1 row: groups 3939, flagged 8484, avg_group_size 3.15
--   (same numbers as output/dedup_stats.json; group size counts the original plus its duplicates).
SELECT COUNT(DISTINCT duplicate_of) AS groups,
       COUNT(*) AS flagged,
       ROUND((COUNT(*) + COUNT(DISTINCT duplicate_of)) * 1.0 / COUNT(DISTINCT duplicate_of), 2) AS avg_group_size
FROM emails
WHERE is_duplicate = 1;


-- Q11. Largest duplicate groups: each original with how many emails were flagged as its duplicates.
-- Expected output: 5 rows (from_address, subject, original_date, duplicates, latest_duplicate). First row:
--   arsystem@mailman.enron.com, "Your Approval is Overdue: Access Request for matt.smith@enron.com",
--   2001-10-18T00:33:15Z, 27 duplicates, latest 2002-01-02T01:19:40Z (a daily automated reminder).
--   Row 2 is john.arnold@enron.com with a blank subject: one market note sent 4 times within an hour,
--   each copy stored in several folders, 18 duplicates.
SELECT o.from_address, o.subject, o.date AS original_date,
       COUNT(*) AS duplicates, MAX(d.date) AS latest_duplicate
FROM emails AS d
JOIN emails AS o ON o.message_id = d.duplicate_of
WHERE d.is_duplicate = 1
GROUP BY d.duplicate_of
ORDER BY duplicates DESC, original_date
LIMIT 5;


-- Q12. Share of each mailbox flagged as duplicate.
-- Expected output: 5 rows (mailbox, emails, flagged, pct_flagged):
--   allen-p 2961/1765 59.6, arnold-j 4756/2442 51.3, kitchen-l 5304/406 7.7,
--   lay-k 5593/2211 39.5, skilling-j 3738/1660 44.4.
--   kitchen-l is an Outlook-only mailbox. The other four have Lotus Notes folders
--   (all_documents, discussion_threads, sent + _sent_mail) that store the same email several
--   times, which is where most duplicates come from.
SELECT substr(source_file, 9, instr(substr(source_file, 9), '/') - 1) AS mailbox,
       COUNT(*) AS emails,
       SUM(is_duplicate) AS flagged,
       ROUND(100.0 * SUM(is_duplicate) / COUNT(*), 1) AS pct_flagged
FROM emails
GROUP BY mailbox
ORDER BY mailbox;
