"""Edge-case tests for the Task 1 parser (spec 4, Task 1 item 3)."""
from datetime import datetime, timezone

import pytest

from enron_pipeline.body_split import split_body
from enron_pipeline.headings import extract_headings
from enron_pipeline.parser import ParseError, parse_bytes, parse_date

HEADERS = (
    "Message-ID: <1.2.JavaMail.evans@thyme>\n"
    "Date: Mon, 9 Oct 2000 07:16:00 -0700 (PDT)\n"
    "From: phillip.allen@enron.com\n"
    "To: keith.holst@enron.com\n"
    "Subject: Test subject\n"
    "Mime-Version: 1.0\n"
    "Content-Type: text/plain; charset=us-ascii\n"
    "Content-Transfer-Encoding: 7bit\n"
    "X-From: Phillip K Allen\n"
    "X-To: Keith Holst\n"
    "X-cc: \n"
    "X-bcc: \n"
    "X-Folder: \\Phillip_Allen_Dec2000\\Notes Folders\\All documents\n"
    "X-Origin: Allen-P\n"
    "X-FileName: pallen.nsf\n"
)


def make(headers: str = HEADERS, body: str = "Hello Keith,\nSee you.\n") -> bytes:
    return (headers + "\n" + body).encode("utf-8")


def test_basic_fields():
    r = parse_bytes(make(), "maildir/allen-p/inbox/1")
    assert r.message_id == "<1.2.JavaMail.evans@thyme>"
    assert r.date == datetime(2000, 10, 9, 14, 16, tzinfo=timezone.utc)
    assert r.from_address == "phillip.allen@enron.com"
    assert r.to_addresses == ["keith.holst@enron.com"]
    assert r.subject == "Test subject"
    assert r.body == "Hello Keith,\nSee you."
    assert r.source_file == "maildir/allen-p/inbox/1"
    assert r.x_cc is None and r.x_folder.endswith("All documents")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Mon, 14 May 2001 16:39:00 PST", datetime(2001, 5, 15, 0, 39, tzinfo=timezone.utc)),
        ("Mon, 14 May 2001 16:39:00 CDT", datetime(2001, 5, 14, 21, 39, tzinfo=timezone.utc)),
        ("Mon, 14 May 2001 16:39:00 EST", datetime(2001, 5, 14, 21, 39, tzinfo=timezone.utc)),
        ("Mon, 14 May 2001 16:39:00 -0500", datetime(2001, 5, 14, 21, 39, tzinfo=timezone.utc)),
        ("Mon, 14 May 2001 16:39:00 CEST", datetime(2001, 5, 14, 14, 39, tzinfo=timezone.utc)),
    ],
)
def test_date_timezones(value, expected):
    assert parse_date(value) == expected


def test_unknown_timezone_fails_instead_of_guessing():
    with pytest.raises(ParseError, match="unknown timezone"):
        parse_date("Mon, 14 May 2001 16:39:00 XYZT")


def test_placeholder_date_fails():
    with pytest.raises(ParseError, match="placeholder"):
        parse_date("Mon, 31 Dec 1979 16:00:00 -0800 (PST)")


def test_multiline_to_and_cc():
    headers = HEADERS.replace(
        "To: keith.holst@enron.com\n",
        "To: a@enron.com, b@enron.com,\n\tc@enron.com, \"Doe, Jane\" <jane.doe@enron.com>\n"
        "Cc: x@enron.com, '.hall@enron.com'\n",
    )
    r = parse_bytes(make(headers), "f")
    assert r.to_addresses == ["a@enron.com", "b@enron.com", "c@enron.com", "jane.doe@enron.com"]
    assert "x@enron.com" in r.cc_addresses


def test_folded_subject_unfolds():
    headers = HEADERS.replace("Subject: Test subject\n", "Subject: RE: Long subject that\n wraps here\n")
    assert parse_bytes(make(headers), "f").subject == "RE: Long subject that wraps here"


def test_missing_to_fails_with_reason():
    headers = HEADERS.replace("To: keith.holst@enron.com\n", "")
    with pytest.raises(ParseError, match="missing To"):
        parse_bytes(make(headers), "f")


def test_blank_subject_is_accepted():
    headers = HEADERS.replace("Subject: Test subject\n", "Subject: \n")
    assert parse_bytes(make(headers), "f").subject == ""


def test_all_mandatory_problems_reported_together():
    headers = HEADERS.replace("To: keith.holst@enron.com\n", "").replace("Subject: Test subject\n", "")
    with pytest.raises(ParseError) as exc:
        parse_bytes(make(headers), "f")
    assert "missing To" in str(exc.value) and "missing Subject" in str(exc.value)


@pytest.mark.parametrize(
    "raw, reason",
    [
        (b"", "empty file"),
        (b"\x00\x01\x02\xff\xfe binary junk", "binary"),
        (b"just some text without any headers at all\nsecond line\n", "no headers"),
    ],
)
def test_broken_files_fail_cleanly(raw, reason):
    with pytest.raises(ParseError, match=reason):
        parse_bytes(raw, "f")


def test_empty_body_fails():
    with pytest.raises(ParseError, match="empty body"):
        parse_bytes(make(body="   \n"), "f")


def test_quoted_printable_and_cp1252():
    headers = HEADERS.replace("Content-Transfer-Encoding: 7bit", "Content-Transfer-Encoding: quoted-printable")
    raw = (headers + "\n").encode() + b"Price is =E9lev=E9 and long line=\n continues\n"
    r = parse_bytes(raw, "f")
    assert r.body == "Price is élevé and long line continues"


def test_non_utf8_header_bytes():
    raw = make().replace(b"X-From: Phillip K Allen", b"X-From: Ren\xe9e Smith")
    assert parse_bytes(raw, "f").x_from == "Renée Smith"


def test_lotus_forward_split_wrapped_marker():
    body = (
        "FYI\n\n"
        "---------------------- Forwarded by Phillip K Allen/HOU/ECT on 10/09/2000 \n"
        "02:16 PM ---------------------------\n\n"
        "Richard Burchfield\n10/06/2000 06:59 AM\nTo: Phillip K Allen/HOU/ECT@ECT\n"
        "Subject: Positions\n\nPhillip, below is the list.\n"
    )
    own, fwd, quoted = split_body(body)
    assert own == "FYI"
    assert fwd.startswith("---------------------- Forwarded by") and "below is the list" in fwd
    assert quoted is None


def test_pure_forward_has_empty_own_body():
    own, fwd, _ = split_body("---------------------- Forwarded by X/HOU/ECT on 10/09/2000 02:16 PM ---\nText\n")
    assert own == "" and fwd


def test_original_message_goes_to_quoted():
    body = "Sounds good.\n\n-----Original Message-----\nFrom: A\nSent: Monday\nTo: B\nSubject: x\n\nOld text\n"
    own, fwd, quoted = split_body(body)
    assert own == "Sounds good." and fwd is None and "Old text" in quoted


def test_outlook_original_message_with_fw_subject_is_forward():
    body = "\n-----Original Message-----\nFrom: Turner, Nancy\nSent: Friday\nTo: Allen\nSubject: El Paso\n\nnumbers\n"
    own, fwd, quoted = split_body(body, "FW: El Paso 1110")
    assert own == "" and quoted is None and "numbers" in fwd


def test_aol_embedded_header_forward():
    body = (
        "Return-path: <Joe@aol.com>\nFrom: Joe@aol.com\nFull-name: Joe\nMessage-ID: <cd.1@aol.com>\n"
        "Date: Fri, 25 May 2001\nSubject: news\nTo: x@y.com\n\nArticle text\n"
    )
    own, fwd, _ = split_body(body, "Fwd: Diplomatic Nominations")
    assert own == "" and "Article text" in fwd


def test_lotus_reply_header_detected():
    body = "Thanks!\n\n\n\nJohn Arnold\n10/06/2000 06:59 AM\nTo: Phillip K Allen/HOU/ECT@ECT\ncc:\nSubject: Re: gas\n\nOld\n"
    own, _, quoted = split_body(body)
    assert own == "Thanks!" and quoted.startswith("John Arnold")


def test_inline_gt_quotes_are_separated():
    body = "Bob wrote:\n> line one\n> line two\nMy answer.\n"
    own, _, quoted = split_body(body)
    assert quoted == "> line one\n> line two"
    assert "My answer." in own and ">" not in own


def test_attachment_inference():
    r = parse_bytes(make(body="Here it is.\n\n - Pipeline.xls\n<<File: Pipeline.xls>>\n"), "f")
    assert r.has_attachment is True
    assert parse_bytes(make(), "f").has_attachment is False


def test_headings():
    text = (
        "Intro line.\n\n"
        "======== Sponsored by ========\nAd text.\n\n"
        "Market Summary\n--------------\nPrices up.\n\n"
        "ACTION ITEMS\n- call Bob\n\n"
        "Next steps:\nDo things.\n\n"
        "To: someone@enron.com\nTHANKS\n"
    )
    assert extract_headings(text).split("\n") == ["Sponsored by", "Market Summary", "ACTION ITEMS", "Next steps"]


def test_headings_noise_is_ignored():
    text = (
        "Jeff:\n\nThanks for the note.\n\n"
        "Dear Mr. Lay:\n\n"
        "[IMAGE]\n\n"
        "<<X20292.DOC>>\n - C.DTF\n"
        "TRADE DATE\tTRADE CNT\n\n"
        "Leslie\n----------------------------------------------------\n"
        "Subject: Re: plan\n\nLouise:\n\nok\n"
    )
    assert extract_headings(text) is None
