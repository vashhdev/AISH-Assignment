# Notification Email Template (spec 4.2)

Every notification must follow this template.

```
To: <sender_of_latest_duplicate>
Subject: [Duplicate Notice] Re: <original_subject>
Date: <current_timestamp>
References: <message_id_of_latest_duplicate>

This is an automated notification from the Email Deduplication System.

Your email has been identified as a potential duplicate:

Your Email (Flagged):
Message-ID: <message_id_of_latest_duplicate>
Date Sent: <date_of_latest_duplicate>
Subject: <subject>

Original Email on Record:
Message-ID: <message_id_of_earliest_original>
Date Sent: <date_of_earliest_original>

Similarity Score: <similarity_percentage>%

If this was NOT a duplicate and you intended to send this email,
please reply with CONFIRM to restore it to active status.

No action is required if this is indeed a duplicate.
```

Layout note: in the docx every line is its own paragraph, so blank-line grouping above is our reading. Text and line order are exact.

## Placeholder mapping
| Placeholder | Source |
|---|---|
| `sender_of_latest_duplicate` | `from_address` of the latest flagged email in the group. Live mode: overridden per D2. |
| `original_subject` | `subject` of the group's earliest (original) email, as stored |
| `current_timestamp` | Time the notification is generated, RFC 2822 format |
| `message_id_of_latest_duplicate` | `message_id` of the latest flagged email |
| `date_of_latest_duplicate` | `date` of the latest flagged email |
| `subject` | `subject` of the latest flagged email |
| `message_id_of_earliest_original` | `message_id` of the group's earliest email |
| `date_of_earliest_original` | `date` of the group's earliest email |
| `similarity_percentage` | Similarity of latest vs original, e.g. `97.4` |

## Our notes
- `Re: <original_subject>`: if the original subject already starts with `Re:`, the result is `Re: Re: ...`. Literal is safest for "follow the template"; decide in Task 4.
- `Date:` header in RFC 2822 form (`Mon, 16 Nov 2026 14:03:00 +0000`). `Date Sent` values: UTC, one consistent format.
- Enron Message-IDs already include `<...>`. Don't double-wrap in `References:`.
- Dry-run `.eml` files carry all headers. Live send header support: `01_OVERVIEW.md` gotcha 4.
- If live mail is redirected to our own Gmail, keep the body exact and record the intended Enron recipient in the log/DB rather than editing the template.
