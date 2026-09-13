"""Owner-integration regressions for bounded Reply-SLA conflict recovery."""

import datetime
import inspect
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from services import reply_sla_escalation_service as service

NOW = datetime.datetime(2026, 9, 12, 10, tzinfo=datetime.timezone.utc)


def _mail(email_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=email_id,
        user_id="alice",
        organization_id="org-a",
        workspace_id="workspace-a",
        message_id=f"mail-{email_id}",
        thread_id=f"thread-{email_id}",
        subject=f"subject-{email_id}",
        date=NOW - datetime.timedelta(days=3),
    )


def _task(email_id: int, *, task_uid: str) -> SimpleNamespace:
    return SimpleNamespace(
        task_uid=task_uid,
        related_email_id=email_id,
        status="open",
        priority="normal",
        title="old title",
        related_thread_id=f"old-thread-{email_id}",
        updated_at=NOW - datetime.timedelta(days=1),
    )


class _AlwaysUniqueConflictSession:
    """Count SAVEPOINT/flush attempts while every insert loses a unique race."""

    def __init__(self) -> None:
        self.flush_count = 0
        self.savepoint_count = 0
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.no_autoflush = nullcontext()

    def add(self, _task_record) -> None:
        return None

    async def flush(self) -> None:
        self.flush_count += 1
        driver_error = RuntimeError("duplicate")
        driver_error.sqlstate = "23505"
        raise IntegrityError("insert", {}, driver_error)

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoint_count += 1
        yield


@pytest.mark.asyncio
async def test_repeated_unique_conflicts_never_fall_back_to_per_row_savepoints(
    monkeypatch,
):
    """Exhaust contention after three batch attempts instead of N row retries."""
    mails = [_mail(email_id) for email_id in range(1, 5)]
    winners = {email.id: _task(email.id, task_uid=f"winner-{email.id}") for email in mails}
    visibility = [
        {},
        {1: winners[1]},
        {2: winners[2]},
        {3: winners[3]},
    ]
    reads = 0

    async def fetch_existing(_db, _user_id, _organization_id, _email_ids):
        nonlocal reads
        result = visibility[min(reads, len(visibility) - 1)]
        reads += 1
        return result

    def create_task(_user_id, _organization_id, email):
        return _task(email.id, task_uid=f"candidate-{email.id}")

    def update_task(task, email, now):
        if task.status != "done":
            task.status = "blocked"
            task.priority = "urgent"
            task.title = f"follow up: {email.subject}"
            task.updated_at = now

    monkeypatch.setattr(service, "_fetch_existing_tasks_by_email", fetch_existing)
    monkeypatch.setattr(service, "_create_task_for_escalation", create_task)
    monkeypatch.setattr(service, "_update_task_for_escalation", update_task)

    database = _AlwaysUniqueConflictSession()
    with pytest.raises(service.ReplySlaTaskConflict) as captured:
        await service._process_fallback_escalation(
            database,
            "alice",
            "org-a",
            mails,
            NOW,
        )

    assert captured.value.error_code == "reply_sla_batch_retry_exhausted"
    assert database.flush_count == 3
    assert database.savepoint_count == 3
    database.rollback.assert_awaited_once()
    database.commit.assert_not_awaited()


def test_conflict_exposes_machine_readable_error_code() -> None:
    """Keep HTTP conflict classification independent of localized prose."""
    conflict = service.ReplySlaTaskConflict(
        "reply_sla_task_conflict",
        "concurrent winner not visible",
    )
    assert conflict.error_code == "reply_sla_task_conflict"
    assert str(conflict) == "concurrent winner not visible"


def test_rollback_reload_contract_includes_workspace_scope() -> None:
    """Preserve #1486 workspace ownership when batching expired-mail reloads."""
    reload_overdue_replies = getattr(service, "_reload_overdue_replies")
    parameters = inspect.signature(reload_overdue_replies).parameters
    assert tuple(parameters) == (
        "db",
        "user_id",
        "organization_id",
        "workspace_id",
        "email_ids",
    )
