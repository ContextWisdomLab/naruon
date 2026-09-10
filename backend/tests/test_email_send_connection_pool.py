"""Regression coverage for bounded-pool email-send connection ordering."""

import asyncio
from types import SimpleNamespace

import pytest

from api import emails as emails_api
from api.auth import AuthContext
from services.email_send_rate_limiter import EmailSendRateLimitDecision


class _TenantResult:
    def __init__(self, tenant_config):
        self._tenant_config = tenant_config

    def scalar_one_or_none(self):
        return self._tenant_config


class _SingleSlotRequestSession:
    """Model a request session that holds the only pool slot after a read."""

    def __init__(self):
        self.connection_slot = asyncio.Semaphore(1)
        self.holds_connection = False
        self.events: list[str] = []
        self.tenant_config = SimpleNamespace(
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_username="testuser",
            smtp_password=None,
        )

    async def execute(self, _query):
        await self.connection_slot.acquire()
        self.holds_connection = True
        self.events.append("tenant-config-read")
        return _TenantResult(self.tenant_config)

    async def rollback(self):
        self.events.append("request-read-transaction-ended")
        if self.holds_connection:
            self.holds_connection = False
            self.connection_slot.release()


@pytest.mark.asyncio
async def test_send_releases_request_read_connection_before_limiter_session(monkeypatch):
    """A one-slot pool must not self-deadlock when the limiter opens its session."""

    session = _SingleSlotRequestSession()
    auth_context = AuthContext(
        user_id="testuser",
        role="member",
        organization_id="org-acme",
        group_ids=(),
        workspace_id="workspace-org-acme",
    )

    monkeypatch.setattr(
        emails_api,
        "validate_smtp_destination",
        lambda smtp_server, smtp_port, *, resolve_host=True: (smtp_server, smtp_port),
    )

    async def bounded_pool_rate_limit(_auth_context):
        await asyncio.wait_for(session.connection_slot.acquire(), timeout=0.05)
        session.events.append("limiter-session-acquired")
        session.connection_slot.release()
        return EmailSendRateLimitDecision(allowed=True, reason="allowed")

    async def fake_send_email(*, message_params, smtp_config):
        assert message_params.to_address == "test@example.com"
        assert smtp_config.smtp_server == "smtp.example.com"
        return {"status": "sent", "simulated": False}

    monkeypatch.setattr(
        emails_api, "enforce_send_email_rate_limit", bounded_pool_rate_limit
    )
    monkeypatch.setattr(emails_api, "send_email", fake_send_email)

    result = await emails_api.send_email_endpoint(
        emails_api.SendEmailRequest(
            to="test@example.com",
            subject="Pool regression",
            body="Body",
        ),
        db=session,
        auth_context=auth_context,
    )

    assert result == {"status": "sent", "simulated": False}
    assert session.events == [
        "tenant-config-read",
        "request-read-transaction-ended",
        "limiter-session-acquired",
    ]
