"""Owner-lane regressions for task authorization and Reply-SLA error routing."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api.auth import AuthContext
from api.tasks import (
    UpdateTicketTaskRequest,
    _build_task_query,
    list_ticket_tasks,
    update_ticket_task,
)
from db.models import TicketTask
from services import reply_sla_escalation_service as reply_sla_service


class _TaskRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        if not self._rows:
            return None
        if len(self._rows) != 1:
            raise AssertionError("expected at most one task row")
        return self._rows[0]


class _CrossWorkspaceTaskSession:
    """Return a foreign-workspace source-linked task unless SQL excludes it."""

    def __init__(self, task: TicketTask) -> None:
        self.task = task
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.statement_texts: list[str] = []

    async def execute(self, statement):
        statement_text = str(statement).lower()
        self.statement_texts.append(statement_text)
        source_scope_enforced = (
            "ticket_tasks.email_id is null" in statement_text
            and "email_records.id is not null" in statement_text
        )
        return _TaskRows([] if source_scope_enforced else [(self.task, None)])


@pytest.fixture
def workspace_auth() -> AuthContext:
    return AuthContext(
        user_id="alice",
        role="member",
        organization_id="org-acme",
        group_ids=(),
        workspace_id="workspace-a",
    )


@pytest.fixture
def cross_workspace_task() -> TicketTask:
    now = datetime.datetime(2026, 9, 13, tzinfo=datetime.timezone.utc)
    return TicketTask(
        id=1,
        task_uid="cross-workspace-source-task",
        user_id="alice",
        organization_id="org-acme",
        title="foreign source task",
        status="open",
        priority="normal",
        source_type="email",
        related_email_id=991,
        related_thread_id="foreign-thread",
        created_at=now,
        updated_at=now,
    )


def test_task_query_requires_authorized_source_or_no_source(
    workspace_auth: AuthContext,
) -> None:
    """Keep unlinked tasks while excluding links whose scoped email join vanished."""
    statement_text = str(_build_task_query(workspace_auth)).lower()

    assert "email_records.workspace_id" in statement_text
    assert "ticket_tasks.email_id is null" in statement_text
    assert "email_records.id is not null" in statement_text


@pytest.mark.asyncio
async def test_list_tasks_excludes_source_linked_task_from_other_workspace(
    workspace_auth: AuthContext,
    cross_workspace_task: TicketTask,
) -> None:
    """Do not expose a task merely because its source-email columns were hidden."""
    database = _CrossWorkspaceTaskSession(cross_workspace_task)

    response = await list_ticket_tasks(db=database, auth_context=workspace_auth)

    assert response == []
    assert database.statement_texts


@pytest.mark.asyncio
async def test_update_task_rejects_source_linked_task_from_other_workspace(
    workspace_auth: AuthContext,
    cross_workspace_task: TicketTask,
) -> None:
    """Treat a task linked to an unauthorized workspace email as not found."""
    database = _CrossWorkspaceTaskSession(cross_workspace_task)

    with pytest.raises(HTTPException) as captured:
        await update_ticket_task(
            "cross-workspace-source-task",
            UpdateTicketTaskRequest(status="done"),
            db=database,
            auth_context=workspace_auth,
        )

    assert captured.value.status_code == 404
    assert cross_workspace_task.status == "open"
    database.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_non_unique_integrity_error_never_enters_unique_conflict_recovery(
    monkeypatch,
) -> None:
    """Propagate FK/check failures instead of treating them as uniqueness races."""
    now = datetime.datetime.now(datetime.timezone.utc)
    source_email = SimpleNamespace(
        id=71,
        date=now - datetime.timedelta(days=3),
    )
    database = SimpleNamespace(rollback=AsyncMock())
    driver_error = RuntimeError("foreign key failure")
    driver_error.sqlstate = "23503"
    bulk_error = IntegrityError("insert", {}, driver_error)

    async def pending_replies(*_args, **_kwargs):
        return [source_email]

    bulk_escalation = AsyncMock(side_effect=bulk_error)
    fallback_escalation = AsyncMock(
        side_effect=AssertionError("non-unique failure entered conflict recovery")
    )
    monkeypatch.setattr(reply_sla_service, "check_missing_replies", pending_replies)
    monkeypatch.setattr(
        reply_sla_service, "_process_bulk_escalation", bulk_escalation
    )
    monkeypatch.setattr(
        reply_sla_service, "_process_fallback_escalation", fallback_escalation
    )

    with pytest.raises(IntegrityError) as captured:
        await reply_sla_service.create_reply_sla_escalation_tasks(
            database,
            user_id="alice",
            organization_id="org-acme",
            workspace_id="workspace-a",
            overdue_hours=48,
            limit=10,
        )

    assert captured.value is bulk_error
    database.rollback.assert_awaited_once()
    fallback_escalation.assert_not_awaited()
