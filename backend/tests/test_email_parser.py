import base64
import datetime
import os
import tempfile
from email.message import Message
from unittest.mock import MagicMock, patch

import pytest
from services.email_parser import (
    EmailParseError,
    _attachment_part_content,
    _extract_thread_id,
    _format_display_address,
    _process_multipart_body,
    _process_singlepart_body,
    _sanitize_address_display_text,
    _sanitize_nul,
    parse_eml,
    parse_eml_bytes,
)


def test_parse_eml_basic():
    eml_content = b"""Message-ID: <123@test.com>
From: test@test.com\x00
To: recipient@test.com
Subject: Hello\x00World
Date: Mon, 27 Apr 2026 10:00:00 +0000

This is a test email.\x00"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["message_id"] == "<123@test.com>"
        assert parsed["sender"] == "test@test.com"  # NUL removed
        assert parsed["subject"] == "HelloWorld"  # NUL removed
        assert "This is a test email." in parsed["body"]
        assert "\x00" not in parsed["body"]
    finally:
        os.unlink(temp_path)


def test_parse_eml_multipart_html_fallback():
    eml_content = b"""Message-ID: <multi@test.com>
From: multi@test.com
To: recipient@test.com
Subject: Multipart HTML
Date: Mon, 27 Apr 2026 10:00:00 +0000
Content-Type: multipart/alternative; boundary="boundary-string"

--boundary-string
Content-Type: text/html; charset="utf-8"

<p>This is HTML content</p>
--boundary-string--"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["body"] == "This is HTML content"
        assert parsed["body_content_type"] == "text/html"
        assert parsed["body_parse_content"] == "<p>This is HTML content</p>"
    finally:
        os.unlink(temp_path)


def test_parse_eml_strips_active_html_from_display_fields():
    eml_content = b"""Message-ID: <xss@test.com>
From: Attacker <attacker@example.com>
To: recipient@test.com
Subject: <img src=x onerror=alert('subject')>Launch
Date: Mon, 27 Apr 2026 10:00:00 +0000
Content-Type: text/html; charset="utf-8"

<html><body>Hello<script>alert('body')</script><img src=x onerror=alert('body')></body></html>"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["subject"] == "Launch"
        assert parsed["body"] == "Hello"
        assert "<" not in parsed["body"]
        assert "script" not in parsed["body"].lower()
        assert parsed["message_id"] == "<xss@test.com>"
        assert parsed["sender"] == "Attacker <attacker@example.com>"
    finally:
        os.unlink(temp_path)


def test_parse_eml_strips_active_html_from_address_display_fields():
    eml_content = b"""Message-ID: <headers@test.com>
From: "<img src=x onerror=alert(1)>" <attacker@example.com>
To: "<script>alert(1)</script>" <recipient@test.com>
Reply-To: "&lt;svg onload=alert(1)&gt;" <reply@test.com>
Subject: Header display safety
Date: Mon, 27 Apr 2026 10:00:00 +0000

Plain body"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["sender"] == "attacker@example.com"
        assert parsed["recipients"] == "recipient@test.com"
        assert parsed["reply_to"] == "reply@test.com"
    finally:
        os.unlink(temp_path)


def test_parse_eml_stores_non_ascii_display_names_decoded():
    # RFC 2047: non-ASCII From/To/Reply-To display names arrive as encoded-words
    # (e.g. =?UTF-8?B?...?=). policy.default header-decodes them; the stored
    # display fields must keep the decoded text rather than re-encoding it back
    # into an encoded-word (formataddr's behavior), which would render every
    # non-ASCII sender/recipient as garbled =?utf-8?...?= bytes in the UI.
    from_name = "박성호"
    to_name = "김천"
    reply_name = "응답"
    subject_text = "회 테스트"

    def encoded_word(text: str) -> bytes:
        token = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return f"=?UTF-8?B?{token}?=".encode("ascii")

    eml_content = (
        b"Message-ID: <i18n@test.com>\r\n"
        b"From: " + encoded_word(from_name) + b" <sender@example.com>\r\n"
        b"To: " + encoded_word(to_name) + b" <recipient@test.com>\r\n"
        b"Reply-To: " + encoded_word(reply_name) + b" <reply@test.com>\r\n"
        b"Subject: " + encoded_word(subject_text) + b"\r\n"
        b"Date: Mon, 27 Apr 2026 10:00:00 +0000\r\n"
        b"\r\n"
        b"Plain body"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["sender"] == f"{from_name} <sender@example.com>"
        assert parsed["recipients"] == f"{to_name} <recipient@test.com>"
        assert parsed["reply_to"] == f"{reply_name} <reply@test.com>"
        assert parsed["subject"] == subject_text
        assert "=?" not in parsed["sender"]
        assert "=?" not in parsed["recipients"]
    finally:
        os.unlink(temp_path)


def test_sanitize_address_display_text_keeps_decoded_unicode_and_quotes_specials():
    # A decoded non-ASCII name stays literal (formataddr would re-encode it).
    assert (
        _sanitize_address_display_text("박성호 <sender@example.com>")
        == "박성호 <sender@example.com>"
    )
    # A display name containing an RFC 5322 special is quoted so a ", "-joined
    # multi-address value stays unambiguous.
    assert (
        _sanitize_address_display_text('"Doe, John" <j@x.com>')
        == '"Doe, John" <j@x.com>'
    )
    # Multiple addresses with mixed scripts are each formatted and comma-joined.
    assert (
        _sanitize_address_display_text("박성호 <a@x.com>, Bob <b@x.com>")
        == "박성호 <a@x.com>, Bob <b@x.com>"
    )


def test_format_display_address_escapes_quotes_and_handles_empty_name():
    # No display name -> bare address.
    assert _format_display_address("", "a@x.com") == "a@x.com"
    # Non-ASCII name kept literal.
    assert _format_display_address("박성호", "s@x.com") == "박성호 <s@x.com>"
    # Embedded quotes/backslashes are escaped inside the quoted-string, matching
    # email.utils.formataddr's escaping.
    assert (
        _format_display_address('Fancy "Q"', "q@x.com") == '"Fancy \\"Q\\"" <q@x.com>'
    )


def test_process_multipart_body_ignores_non_string_part_content():
    # get_content() can return a non-str (e.g. undecodable bytes) even for a
    # text/* part; the isinstance guard must drop it rather than concatenate
    # bytes into the plain/html body.
    plain_part = MagicMock()
    plain_part.get_content_type.return_value = "text/plain"
    plain_part.get_filename.return_value = None
    plain_part.get_content.return_value = b"not-a-str"
    html_part = MagicMock()
    html_part.get_content_type.return_value = "text/html"
    html_part.get_filename.return_value = None
    html_part.get_content.return_value = b"not-a-str"
    msg = MagicMock()
    msg.walk.return_value = [plain_part, html_part]

    assert _process_multipart_body(msg) == ("", "", [])


def test_process_singlepart_body_ignores_non_string_content():
    # A single-part message whose get_content() returns a non-str yields an
    # empty body rather than a stringified bytes value.
    msg = MagicMock()
    msg.get_content_type.return_value = "text/plain"
    msg.get_content.return_value = b"not-a-str"

    assert _process_singlepart_body(msg) == ("", "", [])


def test_parse_eml_strips_active_html_from_attachment_display_fields():
    eml_content = b"""Message-ID: <attachment-xss@test.com>
From: sender@test.com
To: recipient@test.com
Subject: Attachment display safety
Date: Mon, 27 Apr 2026 10:00:00 +0000
Content-Type: multipart/mixed; boundary="mixed-boundary"

--mixed-boundary
Content-Type: text/plain; charset="utf-8"

See attached.
--mixed-boundary
Content-Type: text/plain; charset="utf-8"
Content-Disposition: attachment; filename="<img src=x onerror=alert(1)>.txt"

<script>alert(1)</script>report
--mixed-boundary--"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["attachments"] == [
            {
                "filename": ".txt",
                "content": "report",
                "content_type": "text/plain",
                "parse_content": "<script>alert(1)</script>report",
                "parse_content_type": "text/plain",
                "parser_key": "plain_text",
                "parse_status": "parsed",
                "parse_error_code": None,
            }
        ]
    finally:
        os.unlink(temp_path)


def test_parse_eml_extracts_supported_and_unsupported_attachment_metadata():
    eml_content = b"""Message-ID: <attachment-types@test.com>
From: sender@test.com
To: recipient@test.com
Subject: Attachment types
Date: Mon, 27 Apr 2026 10:00:00 +0000
Content-Type: multipart/mixed; boundary="mixed-boundary"

--mixed-boundary
Content-Type: text/plain; charset="utf-8"

See attached.
--mixed-boundary
Content-Type: text/html; charset="utf-8"
Content-Disposition: attachment; filename="page.html"

<h1>Launch</h1><p>Ship</p>
--mixed-boundary
Content-Type: text/markdown; charset="utf-8"
Content-Disposition: attachment; filename="plan.md"

# Plan

Ship graph
--mixed-boundary
Content-Type: application/json; charset="utf-8"
Content-Disposition: attachment; filename="status.json"

{"project":"Launch"}
--mixed-boundary
Content-Type: text/csv; charset="utf-8"
Content-Disposition: attachment; filename="status.csv"

name,status
Launch,Ready
--mixed-boundary
Content-Type: application/xml; charset="utf-8"
Content-Disposition: attachment; filename="status.xml"

<root>Launch</root>
--mixed-boundary
Content-Type: text/calendar; charset="utf-8"
Content-Disposition: attachment; filename="invite.ics"

BEGIN:VCALENDAR
SUMMARY:Launch
END:VCALENDAR
--mixed-boundary
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjcK
--mixed-boundary--"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["attachments"] == [
            {
                "filename": "page.html",
                "content": "Launch Ship",
                "content_type": "text/html",
                "parse_content": "<h1>Launch</h1><p>Ship</p>",
                "parse_content_type": "text/html",
                "parser_key": "html",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "plan.md",
                "content": "# Plan Ship graph",
                "content_type": "text/markdown",
                "parse_content": "# Plan\n\nShip graph",
                "parse_content_type": "text/markdown",
                "parser_key": "markdown",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "status.json",
                "content": '{"project":"Launch"}',
                "content_type": "application/json",
                "parse_content": '{"project":"Launch"}',
                "parse_content_type": "application/json",
                "parser_key": "json",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "status.csv",
                "content": "name,status Launch,Ready",
                "content_type": "text/csv",
                "parse_content": "name,status\nLaunch,Ready",
                "parse_content_type": "text/csv",
                "parser_key": "csv",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "status.xml",
                "content": "Launch",
                "content_type": "application/xml",
                "parse_content": "<root>Launch</root>",
                "parse_content_type": "application/xml",
                "parser_key": "xml",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "invite.ics",
                "content": "BEGIN:VCALENDAR SUMMARY:Launch END:VCALENDAR",
                "content_type": "text/calendar",
                "parse_content": "BEGIN:VCALENDAR\nSUMMARY:Launch\nEND:VCALENDAR",
                "parse_content_type": "text/calendar",
                "parser_key": "calendar",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "contract.pdf",
                # Deferred to the NewsDOM worker: the raw PDF bytes are retained
                # as a base64 payload (round-trips the fixture's %PDF-1.7\n) so
                # the worker can recognize them later.
                "content": "JVBERi0xLjcK",
                "content_type": "application/pdf",
                "parse_content": "",
                "parse_content_type": "application/pdf",
                "parser_key": "pdf",
                "parse_status": "pdf_dom_recognition_pending",
                "parse_error_code": None,
            },
        ]
    finally:
        os.unlink(temp_path)


def test_parse_eml_missing_and_malformed_date():
    eml_content1 = b"""Message-ID: <nodate@test.com>
From: test@test.com
To: recipient@test.com
Subject: No Date

Test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content1)
        temp_path1 = f.name

    eml_content2 = b"""Message-ID: <baddate@test.com>
From: test@test.com
To: recipient@test.com
Subject: Bad Date
Date: Invalid-Date-Format

Test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content2)
        temp_path2 = f.name

    try:
        # Missing date
        parsed1 = parse_eml(temp_path1)
        assert isinstance(parsed1["date"], datetime.datetime)
        assert parsed1["date_evidence"] == "missing"

        # Malformed date
        parsed2 = parse_eml(temp_path2)
        assert isinstance(parsed2["date"], datetime.datetime)
        assert parsed2["date_evidence"] == "invalid"
    finally:
        os.unlink(temp_path1)
        os.unlink(temp_path2)


def test_present_date_that_parses_to_none_is_invalid(monkeypatch):
    monkeypatch.setattr(
        "services.email_parser.parsedate_to_datetime", lambda _value: None
    )
    parsed = parse_eml_bytes(
        b"Date: present-but-unparseable\r\n"
        b"From: sender@example.com\r\n\r\nBody"
    )

    assert parsed["date_evidence"] == "invalid"


def test_parse_eml_unknown_timezone_date_is_timezone_aware():
    # RFC 5322 section 3.3: a "-0000" zone means the time zone is unknown, for
    # which parsedate_to_datetime returns a *naive* datetime. Every other parse
    # path yields an aware datetime, so the parser must normalize this to aware
    # too -- otherwise sorting/comparing it against another message's date raises
    # "can't compare offset-naive and offset-aware datetimes" and it misbinds the
    # instant in a timestamptz column.
    eml_content = b"""Message-ID: <unknownzone@test.com>
From: test@test.com
To: recipient@test.com
Subject: Unknown zone
Date: Mon, 27 Apr 2026 10:00:00 -0000

Test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["date"].tzinfo is not None
        # must not raise offset-naive/aware TypeError
        assert parsed["date"] <= datetime.datetime.now(datetime.timezone.utc)
    finally:
        os.unlink(temp_path)


def test_parse_eml_records_message_id_provenance():
    embedded = parse_eml_bytes(
        b"Message-ID: <embedded@example.com>\r\n"
        b"From: sender@example.com\r\n"
        b"To: owner@example.com\r\n"
        b"Date: Mon, 27 Apr 2026 10:00:00 +0000\r\n"
        b"Subject: Embedded\r\n\r\nBody"
    )
    missing = parse_eml_bytes(
        b"From: sender@example.com\r\n"
        b"To: owner@example.com\r\n"
        b"Date: Mon, 27 Apr 2026 10:00:00 +0000\r\n"
        b"Subject: Missing\r\n\r\nBody"
    )

    assert embedded["message_id_evidence"] == "embedded"
    assert missing["message_id_evidence"] == "missing"
def test_parse_eml_io_error():
    with pytest.raises(EmailParseError):
        parse_eml("/path/to/nonexistent/file.eml")


def test_parse_eml_thread_id():
    # 1. Has References
    eml1 = b"""Message-ID: <msg1@test.com>
References: <ref1@test.com> <ref2@test.com>
From: test@test.com
To: user@test.com
Subject: Test

Test"""
    # 2. No References, has In-Reply-To
    eml2 = b"""Message-ID: <msg2@test.com>
In-Reply-To: <ref3@test.com>
From: test@test.com
To: user@test.com
Subject: Test

Test"""
    # 3. Neither -> use Message-ID
    eml3 = b"""Message-ID: <msg3@test.com>
From: test@test.com
To: user@test.com
Subject: Test

Test"""

    for i, content in enumerate([eml1, eml2, eml3]):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
            f.write(content)
            temp_path = f.name
        try:
            parsed = parse_eml(temp_path)
            if i == 0:
                assert parsed["thread_id"] == "<ref1@test.com>"
            elif i == 1:
                assert parsed["thread_id"] == "<ref3@test.com>"
            elif i == 2:
                assert parsed["thread_id"] == "<msg3@test.com>"
        finally:
            os.unlink(temp_path)


def test_extract_thread_id_uses_first_reference_from_long_header():
    msg = Message()
    msg["References"] = " ".join(
        ["<root@test.com>", *(f"<ref-{index}@test.com>" for index in range(200))]
    )
    msg["In-Reply-To"] = "<reply@test.com>"

    assert _extract_thread_id(msg, "<message@test.com>") == "<root@test.com>"


def test_sanitize_address_display_text_keeps_name_only_and_falls_back_to_text():
    # A token with a display name but an empty address part keeps the name
    # (rather than dropping it), and a header that yields no address at all
    # falls back to the sanitized raw text.
    assert _sanitize_address_display_text("Display Name <>") == "Display Name"
    assert _sanitize_address_display_text("") == ""


def test_attachment_part_content_falls_back_to_raw_payload_on_decode_error():
    # A part whose get_content() cannot decode (unknown charset / malformed
    # transfer-encoding) falls back to the raw decoded payload, and to "" when
    # the payload is absent, instead of propagating the decode error.
    raw_part = MagicMock()
    raw_part.get_content.side_effect = LookupError("unknown charset")
    raw_part.get_payload.return_value = b"raw-bytes"
    assert _attachment_part_content(raw_part) == b"raw-bytes"

    empty_part = MagicMock()
    empty_part.get_content.side_effect = ValueError("bad encoding")
    empty_part.get_payload.return_value = None
    assert _attachment_part_content(empty_part) == ""


def test_parse_eml_bytes_parses_provider_bytes_and_wraps_parse_errors():
    parsed = parse_eml_bytes(
        b"Message-ID: <bytes@test.com>\r\n"
        b"From: sender@test.com\r\n"
        b"To: user@test.com\r\n"
        b"Subject: Bytes\r\n\r\n"
        b"Body"
    )
    assert parsed["message_id"] == "<bytes@test.com>"
    assert parsed["subject"] == "Bytes"

    # A parser failure is wrapped as the sanitized public EmailParseError rather
    # than leaking the internal exception chain at the ingest boundary.
    with patch(
        "services.email_parser.message_from_bytes", side_effect=ValueError("boom")
    ):
        with pytest.raises(EmailParseError):
            parse_eml_bytes(b"anything")


def test_extract_thread_id_falls_through_whitespace_only_headers():
    # A References/In-Reply-To header that unfolds to only whitespace is present
    # but yields no token when split; _extract_thread_id must fall through to the
    # next source rather than return a blank thread id.
    fell_to_in_reply_to = Message()
    fell_to_in_reply_to["References"] = "   "
    fell_to_in_reply_to["In-Reply-To"] = "<parent@test.com>"
    assert (
        _extract_thread_id(fell_to_in_reply_to, "<message@test.com>")
        == "<parent@test.com>"
    )

    fell_to_message_id = Message()
    fell_to_message_id["References"] = "  "
    fell_to_message_id["In-Reply-To"] = " \t "
    assert (
        _extract_thread_id(fell_to_message_id, "<message@test.com>")
        == "<message@test.com>"
    )


def test_parse_eml_extracts_reply_to_header():
    eml_content = b"""Message-ID: <reply-to@test.com>
From: Sender Name <sender@test.com>
Reply-To: Reply Target <reply-target@test.com>
To: user@test.com
Subject: Reply-To Test

Test"""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".eml") as f:
        f.write(eml_content)
        temp_path = f.name

    try:
        parsed = parse_eml(temp_path)
        assert parsed["reply_to"] == "Reply Target <reply-target@test.com>"
    finally:
        os.unlink(temp_path)


def test_parse_eml_mocked_oserror():
    with patch("builtins.open", side_effect=OSError("Mocked OS Error")):
        with pytest.raises(
            EmailParseError,
            match=r"Failed to read file dummy\.eml: Mocked OS Error",
        ):
            parse_eml("dummy.eml")


def test_sanitize_nul():
    # Normal string
    assert _sanitize_nul("hello world") == "hello world"

    # Strings with NUL characters
    assert _sanitize_nul("hello\x00world") == "helloworld"
    assert _sanitize_nul("\x00hello world") == "hello world"
    assert _sanitize_nul("hello world\x00") == "hello world"
    assert _sanitize_nul("hello\x00\x00world") == "helloworld"
    assert _sanitize_nul("\x00") == ""

    # Empty string
    assert _sanitize_nul("") == ""

    # None value
    assert _sanitize_nul(None) == ""

    # Non-string types (should be cast to string representations without NUL)
    assert _sanitize_nul(123) == "123"
    assert _sanitize_nul(12.3) == "12.3"
    assert _sanitize_nul(True) == "True"


def test_sanitize_display_text():
    from services.email_parser import _sanitize_display_text

    # Normal string
    assert _sanitize_display_text("hello world") == "hello world"

    # Strings with NUL characters
    assert _sanitize_display_text("hello\x00world") == "helloworld"

    # Strings with HTML tags
    assert _sanitize_display_text("<b>hello</b> world") == "hello world"
    assert _sanitize_display_text("<script>alert('xss')</script>") == ""
    assert (
        _sanitize_display_text("hello <img src=x onerror=alert(1)>world")
        == "hello world"
    )

    # Strings combining NUL and HTML
    assert _sanitize_display_text("<b>hello\x00</b>") == "hello"
    assert _sanitize_display_text("<script\x00>alert('xss')</script>") == ""
    # Let's see what happens exactly - _sanitize_nul strips NUL first, then strip_html_markup acts on the rest.
    # So "<script\x00>..." becomes "<script>..." and then strip_html_markup strips it.
    assert _sanitize_display_text("<script\x00>alert('xss\x00')</script>") == ""

    # Empty string
    assert _sanitize_display_text("") == ""

    # None value (falls back to _sanitize_nul which converts None to "")
    assert _sanitize_display_text(None) == ""
