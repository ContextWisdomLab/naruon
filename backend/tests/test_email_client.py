import base64
import logging

import pytest
from services.email_client import (
    EmailMessageParams,
    _sanitize_log_value,
    build_email_message,
    generate_oauth2_string,
    send_email,
)


def test_generate_oauth2_string():
    result = generate_oauth2_string("test@example.com", "dummy_token")
    decoded = base64.b64decode(result)
    assert b"user=test@example.com" in decoded
    assert b"auth=Bearer dummy_token" in decoded


@pytest.mark.parametrize(
    ("user", "access_token"),
    [
        ("victim@example.com\x01auth=Bearer attacker", "valid_token"),
        ("victim@example.com", "valid_token\x01user=attacker@example.com"),
    ],
)
def test_generate_oauth2_string_rejects_sasl_field_delimiters(user, access_token):
    with pytest.raises(
        ValueError,
        match="OAuth2 authentication fields must not contain SASL delimiters",
    ):
        generate_oauth2_string(user, access_token)


def test_build_email_message_sets_reply_headers():
    params = EmailMessageParams(
        to_address="test@example.com",
        subject="Re: Test",
        body="Reply body",
        in_reply_to="<parent@example.com>",
        references="<root@example.com> <parent@example.com>",
    )
    message = build_email_message(
        message_params=params,
        from_address="sender@example.com",
    )

    assert message["In-Reply-To"] == "<parent@example.com>"
    assert message["References"] == "<root@example.com> <parent@example.com>"
    assert message["From"] == "sender@example.com"
    assert message["To"] == "test@example.com"


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("to_address", "victim@example.com\r\nBcc: attacker@example.com"),
        ("from_address", "sender@example.com\nReply-To: attacker@example.com"),
        ("subject", "Status\r\nX-Injected: true"),
        ("in_reply_to", "<parent@example.com>\r\nBcc: attacker@example.com"),
        ("references", "<root@example.com>\nBcc: attacker@example.com"),
    ],
)
def test_build_email_message_rejects_newlines_in_header_fields(
    field_name,
    field_value,
):
    kwargs = {
        "to_address": "victim@example.com",
        "subject": "Status",
        "body": "Body text\nwith allowed body newlines",
        "in_reply_to": "<parent@example.com>",
        "references": "<root@example.com> <parent@example.com>",
    }

    from_address = "sender@example.com"
    if field_name == "from_address":
        from_address = field_value
    else:
        kwargs[field_name] = field_value

    params = EmailMessageParams(**kwargs)
    with pytest.raises(ValueError, match="Email header fields must not contain newlines"):
        build_email_message(message_params=params, from_address=from_address)


@pytest.mark.asyncio
async def test_send_email_logs_sanitized_recipient(caplog):
    caplog.set_level(logging.INFO, logger="services.email_client")

    params = EmailMessageParams(
        to_address="victim@example.com",
        subject="Test",
        body="Body",
    )
    result = await send_email(message_params=params)

    assert result == {"status": "simulated", "simulated": True}
    messages = [record.getMessage() for record in caplog.records]
    assert "Simulating sending email to victim@example.com (no SMTP server configured)" in messages
    assert all("\n" not in message and "\r" not in message for message in messages)


def test_log_value_sanitizer_removes_crlf():
    assert (
        _sanitize_log_value("victim@example.com\r\nINFO forged@example.com")
        == "victim@example.com  INFO forged@example.com"
    )
