# Field Definitions (spec Section 3)

The raw data is inconsistent: not every email has every field, and formatting varies a lot.

## 3.1 Mandatory fields (must extract)
Must be present for every record stored in the DB. If a mandatory field cannot be extracted, log the email as a failed parse with the reason (do not store it).

| Field | Type | Description |
|---|---|---|
| `message_id` | STRING (unique) | The Message-ID header. Must be unique in DB. |
| `date` | DATETIME | Parsed and normalized to UTC. Handle timezone abbreviations (PST, EST, CDT, etc.) and offset formats. |
| `from_address` | STRING | Sender email address. Extract just the address, not the display name. |
| `to_addresses` | LIST of STRING | All recipients in the To field. Handle comma-separated lists, line continuations, and mixed formats. |
| `subject` | STRING | Full subject line. Preserve Re:/Fwd: prefixes. |
| `body` | TEXT | The email body content. Separate from forwarded/quoted content where possible. |
| `source_file` | STRING | Relative path to the original file (e.g. `maildir/lay-k/inbox/45`) for traceability. |

## 3.2 Optional fields (extract if present)
Store NULL/empty if not present.

| Field | Type | Description |
|---|---|---|
| `cc_addresses` | LIST of STRING | CC recipients. Same parsing rules as to_addresses. |
| `bcc_addresses` | LIST of STRING | BCC recipients. Rarely present but must be captured. |
| `x_from` | STRING | Display name from the X-From header (Enron-specific). |
| `x_to` | STRING | Display name(s) from the X-To header. |
| `x_cc` | STRING | Display name(s) from the X-cc header. |
| `x_bcc` | STRING | Display name(s) from the X-bcc header. |
| `x_folder` | STRING | The X-Folder header value indicating mailbox folder. |
| `x_origin` | STRING | The X-Origin header value. |
| `content_type` | STRING | MIME content type if specified. |
| `has_attachment` | BOOLEAN | Inferred from Content-Type, MIME boundaries, or body references to attachments. |
| `forwarded_content` | TEXT | Extracted forwarded email content, separated from the primary body. |
| `quoted_content` | TEXT | Extracted quoted reply content (lines beginning with `>` or similar markers). |
| `headings` | TEXT | Extract all the headings present in the email content if available. |

## Our notes (interpretation, confirm during Task 1)
- **Mandatory edge cases to decide:**
  - Empty `to_addresses`: some Enron emails have no To (only Bcc, drafts, calendar items). Spec says mandatory, so these fail with reason "missing To". Count them so the stat is visible.
  - Empty `subject`: header present but blank. Proposal: header present (even blank) = extracted; header absent = failure. Decide.
  - Empty `body`: same question as subject.
- **date:** try `email.utils.parsedate_to_datetime` first (handles `-0700 (PDT)` style). Fallback: `dateutil` with an explicit tz-abbreviation map (PST/PDT/MST/MDT/CST/CDT/EST/EDT/GMT/UT ...). Store ISO 8601 UTC.
- **Addresses:** `email.utils.getaddresses` after unfolding continuation lines. Enron has odd forms: `'name'@enron.com`, `<.name@enron.com>`, `IMCEANOTES-...@ENRON.com` (Lotus Notes leftovers), `undisclosed-recipients:;`. Lowercase + strip. Decide whether IMCEANOTES addresses are kept as-is.
- **Body split markers:** `-----Original Message-----`, `----- Forwarded by X on DATE -----`, `---------------------- Forwarded by ...`, `From: ... Sent: ...` blocks, lines starting with `>`. Primary body = text before the first marker. Forwarded vs quoted bucket depends on marker type. Nested forwards stay inside `forwarded_content`.
- **has_attachment:** `multipart/*` content type, MIME boundary, or body references like `<<File: x.doc>>`, ` - x.xls` lines, "see attached", "attachment". The Enron release stripped real attachments, so this is mostly body inference.
- **headings:** the spec is vague. Proposed heuristic: short lines (under ~80 chars) on their own line that are ALL CAPS, or end with `:`, or are followed by a `----` / `====` underline, or are numbered section titles (`1.`, `I.`, `A.`). Stored newline-joined. Document the heuristic in README.
- **Encoding:** read bytes, decode with fallback (`utf-8`, then `cp1252` / `latin-1`), never crash.
