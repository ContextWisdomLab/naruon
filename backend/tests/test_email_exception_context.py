"""Regression coverage for email exception-context suppression."""

import traceback
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import emails as emails_api

_SENSITIVE_EXCEPTION_TEXT = "sensitive-provider-detail"


@pytest.mark.asyncio
async def test_send_email_endpoint_suppresses_internal_exception_context() -> None:
    request = emails_api.SendEmailRequest(
        to="recipient@example.com",
        subject="Security regression",
        body="Body",
    )
    tenant_config = MagicMock(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password=None,
    )
    auth_context = MagicMock(user_id="testuser", organization_id="org-acme")

    with patch.object(
        emails_api,
        "get_scoped_tenant_config",
        new=AsyncMock(return_value=tenant_config),
    ), patch.object(
        emails_api, "validate_smtp_destination"
    ), patch.object(
        emails_api, "_enforce_send_email_rate_limit"
    ), patch.object(
        emails_api,
        "send_email",
        new=AsyncMock(side_effect=RuntimeError(_SENSITIVE_EXCEPTION_TEXT)),
    ):
        with pytest.raises(emails_api.HTTPException) as raised:
            await emails_api.send_email_endpoint(
                request,
                db=MagicMock(),
                auth_context=auth_context,
            )

    rendered = "".join(
        traceback.format_exception(
            type(raised.value), raised.value, raised.value.__traceback__
        )
    )
    assert raised.value.status_code == 500
    assert raised.value.detail == "An internal error occurred while sending the email"
    assert raised.value.__suppress_context__ is True
    assert raised.value.__cause__ is None
    assert _SENSITIVE_EXCEPTION_TEXT not in rendered
