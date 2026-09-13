"""Unit edge contracts; scripted sessions do not model PostgreSQL races."""

import datetime
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import Email, TicketTask
from services import reply_sla_escalation_service as escalation_service

pytestmark = pytest.mark.asyncio
CURRENT_TIME = datetime.datetime(2026, 9, 5, 12, tzinfo=datetime.timezone.utc)


def _email_record(email_id, *, date=CURRENT_TIME - datetime.timedelta(days=3)):
    return Email(
        id=email_id,
        user_id="alice",
        organization_id="org-acme",
        workspace_id="workspace-acme",
        message_id=f"<reply-{email_id}@example.com>",
        thread_id=f"<thread-{email_id}@example.com>",
        subject=f"Reply {email_id}",
        date=date,
    )


def _task_record(email_record, *, task_uid="existing-task_record", status="open"):
    return TicketTask(
        task_uid=task_uid,
        user_id="alice",
        organization_id="org-acme",
        title="Manual follow-up",
        status=status,
        priority="normal",
        source_type="reply_sla",
        related_email_id=email_record.id,
        related_thread_id="manual-thread",
        created_at=CURRENT_TIME - datetime.timedelta(days=2),
        updated_at=CURRENT_TIME - datetime.timedelta(days=1),
    )


class TaskSession:
    """Script query visibility and discard staged inserts on savepoint failure."""

    def __init__(self, row_batches, *, flush_failures=(), fail_first_commit=False):
        self.pending = []
        self.committed = []
        self.fail_first_commit = fail_first_commit
        results = [
            SimpleNamespace(scalars=lambda rows=rows: SimpleNamespace(all=lambda: rows))
            for rows in row_batches
        ]
        self.execute = AsyncMock(side_effect=results)
        self.flush = AsyncMock(
            side_effect=[
                IntegrityError("concurrent source task_record", {}, None)
                if fail
                else None
                for fail in flush_failures
            ]
        )
        self.commit = AsyncMock(side_effect=self._commit)
        self.rollback = AsyncMock(side_effect=self.pending.clear)
        self.refresh = AsyncMock()

    def add(self, task_record):
        self.pending.append(task_record)

    async def _commit(self):
        if self.fail_first_commit:
            self.fail_first_commit = False
            raise IntegrityError("concurrent source task_record", {}, None)
        self.committed.extend(self.pending)
        self.pending.clear()

    @asynccontextmanager
    async def begin_nested(self):
        staged_before = list(self.pending)
        try:
            yield
        except IntegrityError:
            self.pending[:] = staged_before
            raise


@pytest.fixture
def fixed_clock(monkeypatch):
    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz):
            return CURRENT_TIME.astimezone(tz)

    monkeypatch.setattr(
        escalation_service,
        "datetime",
        SimpleNamespace(
            datetime=FixedDatetime,
            timedelta=datetime.timedelta,
            timezone=datetime.timezone,
        ),
    )


async def test_duplicate_existing_source_updates_first_task_only():
    email_record = _email_record(11)
    first_record = _task_record(email_record, task_uid="first_record-task_record")
    duplicate_record = _task_record(email_record, task_uid="older_record-task_record")
    duplicate_record.updated_at = CURRENT_TIME - datetime.timedelta(days=2)
    database_session = TaskSession([[first_record, duplicate_record]])

    created_count, task_records = await escalation_service._process_bulk_escalation(
        database_session, "alice", "org-acme", [email_record], CURRENT_TIME
    )

    assert created_count == 0
    assert task_records == [(first_record, "<reply-11@example.com>")]
    assert (first_record.status, first_record.priority) == ("blocked", "urgent")
    assert first_record.related_thread_id == "thread-11@example.com"
    assert first_record.updated_at == CURRENT_TIME
    assert (
        duplicate_record.title,
        duplicate_record.status,
        duplicate_record.priority,
    ) == (
        "Manual follow-up",
        "open",
        "normal",
    )
    assert duplicate_record.related_thread_id == "manual-thread"
    assert duplicate_record.updated_at == CURRENT_TIME - datetime.timedelta(days=2)
    assert database_session.committed == []


@pytest.mark.parametrize(
    "process_batch",
    [
        escalation_service._process_bulk_escalation,
        escalation_service._process_fallback_escalation,
    ],
    ids=["bulk", "fallback"],
)
async def test_completed_task_keeps_user_edits_and_completion(process_batch):
    email_record = _email_record(12)
    completed_record = _task_record(email_record, status="done")
    database_session = TaskSession([[completed_record]])

    created_count, task_records = await process_batch(
        database_session, "alice", "org-acme", [email_record], CURRENT_TIME
    )

    assert created_count == 0
    assert task_records == [(completed_record, "<reply-12@example.com>")]
    assert (
        completed_record.title,
        completed_record.status,
        completed_record.priority,
    ) == (
        "Manual follow-up",
        "done",
        "normal",
    )
    assert completed_record.related_thread_id == "manual-thread"
    assert completed_record.created_at == CURRENT_TIME - datetime.timedelta(days=2)
    assert completed_record.updated_at == CURRENT_TIME - datetime.timedelta(days=1)
    assert database_session.committed == []


@pytest.mark.parametrize(
    "process_batch",
    [
        escalation_service._process_bulk_escalation,
        escalation_service._process_fallback_escalation,
    ],
    ids=["bulk", "fallback"],
)
async def test_empty_batch_does_not_commit(process_batch):
    database_session = TaskSession([[]])

    assert await process_batch(
        database_session, "alice", "org-acme", [], CURRENT_TIME
    ) == (0, [])
    database_session.commit.assert_not_awaited()
    assert database_session.pending == database_session.committed == []


@pytest.mark.parametrize("recent_count", [0, 1], ids=["empty", "not-overdue"])
async def test_no_overdue_mail_returns_evaluation_without_writes(
    monkeypatch, fixed_clock, recent_count
):
    pending = [_email_record(13, date=CURRENT_TIME)] if recent_count else []
    monkeypatch.setattr(
        escalation_service, "check_missing_replies", AsyncMock(return_value=pending)
    )
    database_session = TaskSession([])

    escalation_result = await escalation_service.create_reply_sla_escalation_tasks(
        database_session,
        user_id="alice",
        organization_id="org-acme",
        workspace_id="workspace-acme",
        overdue_hours=48,
        limit=10,
    )

    assert (
        escalation_result.evaluated,
        escalation_result.created,
        escalation_result.overdue_hours,
    ) == (
        recent_count,
        0,
        48,
    )
    assert escalation_result.tasks == []
    database_session.execute.assert_not_awaited()
    database_session.commit.assert_not_awaited()


async def test_naive_utc_deadline_is_inclusive_and_sorted_with_aware_mail(
    monkeypatch, fixed_clock
):
    boundary_record = _email_record(21, date=datetime.datetime(2026, 9, 3, 12))
    recent_record = _email_record(22, date=datetime.datetime(2026, 9, 3, 12, 0, 1))
    older_record = _email_record(
        23,
        date=datetime.datetime(
            2026, 9, 3, 20, tzinfo=datetime.timezone(datetime.timedelta(hours=9))
        ),
    )
    monkeypatch.setattr(
        escalation_service,
        "check_missing_replies",
        AsyncMock(return_value=[boundary_record, recent_record, older_record]),
    )
    persisted_boundary = _task_record(
        boundary_record, task_uid="boundary_record-task_record", status="done"
    )
    persisted_older = _task_record(
        older_record, task_uid="older_record-task_record", status="done"
    )
    database_session = TaskSession([[persisted_boundary, persisted_older]])

    escalation_result = await escalation_service.create_reply_sla_escalation_tasks(
        database_session,
        user_id="alice",
        organization_id="org-acme",
        workspace_id="workspace-acme",
        overdue_hours=48,
        limit=10,
    )

    assert (escalation_result.evaluated, escalation_result.created) == (3, 0)
    assert [task_entry.source_email_id for task_entry in escalation_result.tasks] == [
        "<reply-23@example.com>",
        "<reply-21@example.com>",
    ]
    assert [task_entry.task.task_uid for task_entry in escalation_result.tasks] == [
        "older_record-task_record",
        "boundary_record-task_record",
    ]
    assert boundary_record.date == datetime.datetime(2026, 9, 3, 12)


async def test_missing_refresh_row_preserves_task_and_original_source_reference():
    first_record, second_record = _email_record(31), _email_record(32)
    stale_record = _task_record(first_record, task_uid="stale_record-task_record")
    refreshed_record = _task_record(first_record, task_uid="persisted-task_record")
    retained_record = _task_record(
        second_record, task_uid="retained_record-task_record"
    )
    task_records = [(stale_record, "<reply-31@example.com>"), (retained_record, None)]
    database_session = TaskSession([[refreshed_record]])

    await escalation_service._refresh_escalated_tasks(
        database_session, "alice", "org-acme", [31, 32], task_records
    )

    assert task_records == [
        (refreshed_record, "<reply-31@example.com>"),
        (retained_record, None),
    ]
    database_session.commit.assert_not_awaited()


@pytest.mark.parametrize("late_visibility", [False, True], ids=["batch", "individual"])
async def test_all_insert_conflicts_reuse_winners_without_counting_failed_inserts(
    late_visibility,
):
    email_records = [_email_record(41), _email_record(42)]
    winner_records = [
        _task_record(email_records[0], task_uid="winner_record-first_record"),
        _task_record(email_records[1], task_uid="winner_record-second_record"),
    ]
    database_session = TaskSession(
        [[], [] if late_visibility else winner_records, winner_records, winner_records],
        flush_failures=[True, True, True, True] if late_visibility else [True],
    )

    created_count, task_records = await escalation_service._process_fallback_escalation(
        database_session, "alice", "org-acme", email_records, CURRENT_TIME
    )

    assert created_count == 0
    assert task_records == [
        (winner_records[0], "<reply-41@example.com>"),
        (winner_records[1], "<reply-42@example.com>"),
    ]
    assert [
        (task_record.status, task_record.priority) for task_record, _ in task_records
    ] == [
        ("blocked", "urgent"),
        ("blocked", "urgent"),
    ]
    assert [task_record.related_thread_id for task_record, _ in task_records] == [
        "thread-41@example.com",
        "thread-42@example.com",
    ]
    assert database_session.pending == database_session.committed == []
    database_session.commit.assert_awaited_once()


async def test_late_individual_conflict_preserves_successful_sibling_insert(
    monkeypatch, fixed_clock
):
    first_record, second_record = _email_record(51), _email_record(52)
    winner_record = _task_record(second_record, task_uid="late-winner_record")
    monkeypatch.setattr(
        escalation_service,
        "check_missing_replies",
        AsyncMock(return_value=[first_record, second_record]),
    )
    database_session = TaskSession(
        [[], [], [], [winner_record], [winner_record]],
        flush_failures=[True, True, False, True],
        fail_first_commit=True,
    )

    escalation_result = await escalation_service.create_reply_sla_escalation_tasks(
        database_session,
        user_id="alice",
        organization_id="org-acme",
        workspace_id="workspace-acme",
        overdue_hours=48,
        limit=10,
    )

    assert (escalation_result.evaluated, escalation_result.created) == (2, 1)
    assert [task_entry.source_email_id for task_entry in escalation_result.tasks] == [
        "<reply-51@example.com>",
        "<reply-52@example.com>",
    ]
    [inserted_record] = database_session.committed
    assert escalation_result.tasks[0].task is inserted_record
    assert escalation_result.tasks[1].task is winner_record
    assert (
        inserted_record.user_id,
        inserted_record.organization_id,
        inserted_record.source_type,
    ) == (
        "alice",
        "org-acme",
        "reply_sla",
    )
    assert (inserted_record.related_email_id, inserted_record.related_thread_id) == (
        51,
        "thread-51@example.com",
    )
    assert [
        (task_entry.task.status, task_entry.task.priority)
        for task_entry in escalation_result.tasks
    ] == [
        ("blocked", "urgent"),
        ("blocked", "urgent"),
    ]
    assert database_session.pending == []
    database_session.rollback.assert_awaited_once()
