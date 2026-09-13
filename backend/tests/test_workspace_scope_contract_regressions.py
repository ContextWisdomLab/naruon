"""Workspace-scoping regressions for import and reply-tracking boundaries."""

from __future__ import annotations

from typing import Any

import pytest

from db.models import TenantConfig
from services.email_import_service import _find_existing_email
from services.pop3_worker import Pop3SyncWorker
from services.reply_tracking_service import check_missing_replies


class _ScalarResult:
    def __init__(self, value: Any = None, rows: list[Any] | None = None) -> None:
        self._value = value
        self._rows = list(rows or [])

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _CaptureSession:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.statements: list[Any] = []
        self._rows = list(rows or [])

    async def execute(self, statement: Any) -> _ScalarResult:
        self.statements.append(statement)
        return _ScalarResult(rows=self._rows)


@pytest.mark.asyncio
async def test_email_import_duplicate_lookup_binds_workspace_in_where_clause() -> None:
    session = _CaptureSession()
    await _find_existing_email(
        session,  # type: ignore[arg-type]
        user_id="user-a",
        organization_id="org-a",
        workspace_id="workspace-a",
        message_id="message-a",
        fingerprint="fingerprint-a",
    )
    statement = session.statements[0]
    where_text = str(statement.whereclause).lower()
    params = dict(statement.compile().params)
    assert "email_records.workspace_id" in where_text
    assert "workspace-a" in params.values()


@pytest.mark.asyncio
async def test_reply_tracking_binds_workspace_in_email_query() -> None:
    session = _CaptureSession()
    tenant_config = TenantConfig(user_id="user-a", smtp_username="me@example.com")
    await check_missing_replies(
        session,  # type: ignore[arg-type]
        "user-a",
        "org-a",
        "workspace-a",
        tenant_config=tenant_config,
    )
    statement = session.statements[0]
    where_text = str(statement.whereclause).lower()
    params = dict(statement.compile().params)
    assert "email_records.workspace_id" in where_text
    assert "workspace-a" in params.values()


@pytest.mark.asyncio
async def test_pop3_import_passes_resolved_workspace_to_email_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        organization_id="org-pop3",
        pop3_username="pop3-user@example.com",
    )
    raw_message = (
        b"Message-ID: <pop3-workspace@example.com>\r\n"
        b"From: Sender <sender@example.com>\r\n"
        b"To: pop3-user@example.com\r\n"
        b"Subject: POP3 workspace scope\r\n"
        b"Date: Mon, 15 Jun 2026 10:00:00 +0000\r\n"
        b"\r\n"
        b"Workspace-scoped import.\r\n"
    )
    imported: list[dict[str, Any]] = []

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    async def _capture_import(
        session: Any,
        email_data: dict[str, Any],
        user_id: str,
        organization_id: str | None,
        workspace_id: str,
        owner_addresses: list[str] | None = None,
    ) -> None:
        imported.append(
            {
                "session": session,
                "email_data": email_data,
                "user_id": user_id,
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "owner_addresses": owner_addresses,
            }
        )

    monkeypatch.setattr("services.pop3_worker.AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr("services.pop3_worker.process_fetched_email", _capture_import)
    imported_count = await worker._import_messages(
        config,
        "workspace-pop3",
        [raw_message],
    )
    assert imported_count == 1
    assert len(imported) == 1
    assert imported[0]["workspace_id"] == "workspace-pop3"
