"""Migrated PostgreSQL regression for scheduler connection ownership.

The mail excerpt is from the public 2014-04-27 pgsql-general queue question:
https://www.postgresql.org/message-id/CANsFX049q7C_vJAtn2BSJy_4hQPu0%3DJNtv-Lyzb%3DgbZu-be30A%40mail.gmail.com
Its question and UTC date are preserved; names, addresses, subject and message
identity are anonymized. The clock is replayed three days later, not the mail
date rewritten. Isolated scope IDs and fault injection are test controls, not
customer workload or reply-classification accuracy evidence.

Run scripts/migrate_db.py against an isolated PostgreSQL before this test.
No metadata-created substitute schema or unavailable-database skip is used.
"""

import asyncio
import datetime as date_time
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from db.models import Email, TenantConfig, TicketTask
from scripts.migrate_db import alembic_config
from services import reply_sla_escalation_service, reply_sla_scheduler
from services import reply_tracking_service

pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]


class ReplayDateTime(date_time.datetime):
    """Keep the recorded mail in its original seven-day tracking window."""

    @classmethod
    def now(cls, tz=None):
        """Return the fixed replay instant in the requested timezone."""
        replay_time = cls(2014, 4, 30, 19, 31, 42, tzinfo=date_time.timezone.utc)
        return replay_time.astimezone(tz) if tz else replay_time.replace(tzinfo=None)


async def _seed_observed_mail(session_factory, owner_key, workspace_key=None):
    """Persist an anonymized observed question using current ORM mappings."""
    mail_record = BytesParser(policy=policy.default).parsebytes(
        (Path(__file__).parent / "fixtures/reply_sla_observed_message.eml").read_bytes()
    )
    async with session_factory() as database_session:
        assert (
            await database_session.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            == ScriptDirectory.from_config(alembic_config()).get_current_head()
        )
        if (
            await database_session.scalar(
                select(TenantConfig.id).where(
                    TenantConfig.user_id == owner_key,
                    TenantConfig.organization_id == owner_key,
                )
            )
            is None
        ):
            database_session.add(
                TenantConfig(
                    user_id=owner_key,
                    organization_id=owner_key,
                    smtp_username="archive-author@example.invalid",
                )
            )
        email_record = Email(
            user_id=owner_key,
            organization_id=owner_key,
            workspace_id=workspace_key or owner_key,
            message_id=str(mail_record["Message-ID"]),
            sender=str(mail_record["From"]),
            recipients=str(mail_record["To"]),
            subject=str(mail_record["Subject"]),
            date=parsedate_to_datetime(str(mail_record["Date"])),
            body=mail_record.get_content(),
        )
        database_session.add(email_record)
        await database_session.commit()
        return email_record.id


async def _clear_observed_mail(session_factory, owner_key):
    """Remove only this test's related tasks, email and tenant configuration."""
    async with session_factory() as database_session:
        for record_type in (TicketTask, Email, TenantConfig):
            await database_session.execute(
                delete(record_type).where(
                    record_type.user_id == owner_key,
                    record_type.organization_id == owner_key,
                )
            )
        await database_session.commit()


async def test_real_escalation_commit_does_not_lend_lease_to_pool_reader(monkeypatch):
    """A task commit must not lend its still-held lease to another request."""
    worker_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=2, max_overflow=0
    )
    replica_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    seed_sessions = async_sessionmaker(worker_engine, expire_on_commit=False)
    replica_sessions = async_sessionmaker(replica_engine, expire_on_commit=False)
    owner_key = f"lease_scope_{uuid4().hex}"
    reader_connections = []
    worker_pids = []
    competing_lease_results = []

    class InterleavedSession(AsyncSession):
        """Pause only after real writes to let an unrelated pool reader enter."""

        async def commit(self):
            """Keep actual commit semantics, then borrow a competing connection."""
            worker_pids.append(await self.scalar(text("SELECT pg_backend_pid()")))
            await super().commit()
            if not reader_connections:
                reader_connections.append(await worker_engine.connect())
            async with replica_sessions() as replica_session:
                can_lead = await reply_sla_scheduler._try_acquire_sweep_lease(
                    replica_session
                )
                competing_lease_results.append(can_lead)
                if can_lead:
                    await reply_sla_scheduler._release_sweep_lease(replica_session)

    replay_clock = SimpleNamespace(
        datetime=ReplayDateTime,
        timedelta=date_time.timedelta,
        timezone=date_time.timezone,
    )
    monkeypatch.setattr(reply_sla_escalation_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_tracking_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_sla_scheduler, "engine", worker_engine, raising=False)
    monkeypatch.setattr(
        reply_sla_scheduler,
        "AsyncSessionLocal",
        async_sessionmaker(
            worker_engine, class_=InterleavedSession, expire_on_commit=False
        ),
    )
    try:
        source_email_id = await _seed_observed_mail(seed_sessions, owner_key)
        await reply_sla_scheduler.ReplySlaScheduler()._sync()
        assert competing_lease_results == [False]
        async with replica_sessions() as replica_session:
            task_record = await replica_session.scalar(
                select(TicketTask).where(TicketTask.user_id == owner_key)
            )
            assert task_record is not None
            assert task_record.related_email_id == source_email_id
            assert task_record.status == "blocked"
            assert task_record.priority == "urgent"
            assert task_record.task_uid
            replica_can_lead = await reply_sla_scheduler._try_acquire_sweep_lease(
                replica_session
            )
            if replica_can_lead:
                await reply_sla_scheduler._release_sweep_lease(replica_session)
            reader_pid = await reader_connections[0].scalar(
                text("SELECT pg_backend_pid()")
            )
            assert replica_can_lead is True, (
                f"completed scheduler stranded its lease: worker={worker_pids}, reader={reader_pid}"
            )
            assert reader_pid not in worker_pids
    finally:
        for reader_connection in reader_connections:
            await reader_connection.invalidate()
            await reader_connection.close()
        await _clear_observed_mail(seed_sessions, owner_key)
        await worker_engine.dispose()
        await replica_engine.dispose()


@pytest.mark.parametrize("conflict_path", ["scheduler_bulk", "service_savepoint"])
async def test_concurrent_task_creation_preserves_both_source_workspaces(
    monkeypatch, conflict_path
):
    """A manual writer racing a sweep must not defeat conflict recovery or skip its next workspace."""
    worker_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    replica_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    worker_sessions = async_sessionmaker(worker_engine, expire_on_commit=False)
    replica_sessions = async_sessionmaker(replica_engine, expire_on_commit=False)
    owner_key = f"lease_scope_{uuid4().hex}"
    source_email_ids = []
    competing_task_uid = uuid4().hex
    competing_email_ids = []
    fetch_existing = reply_sla_escalation_service._fetch_existing_tasks_by_email
    replay_clock = SimpleNamespace(
        datetime=ReplayDateTime,
        timedelta=date_time.timedelta,
        timezone=date_time.timezone,
    )
    monkeypatch.setattr(reply_sla_escalation_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_tracking_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_sla_scheduler, "engine", worker_engine, raising=False)
    monkeypatch.setattr(reply_sla_scheduler, "AsyncSessionLocal", worker_sessions)

    async def race_after_lookup(database_session, user_id, organization_id, email_ids):
        """Commit a competing task after the real initial lookup saw no task."""
        task_records = await fetch_existing(
            database_session, user_id, organization_id, email_ids
        )
        if not competing_email_ids:
            competing_email_ids.append(email_ids[0])
            async with replica_sessions() as replica_session:
                replica_session.add(
                    TicketTask(
                        task_uid=competing_task_uid,
                        user_id=user_id,
                        organization_id=organization_id,
                        title="Existing follow-up",
                        status="open",
                        priority="normal",
                        source_type="reply_sla",
                        related_email_id=email_ids[0],
                    )
                )
                await replica_session.commit()
        return task_records

    monkeypatch.setattr(
        reply_sla_escalation_service,
        "_fetch_existing_tasks_by_email",
        race_after_lookup,
    )
    try:
        for workspace_suffix in ("first", "second"):
            source_email_ids.append(
                await _seed_observed_mail(
                    worker_sessions, owner_key, f"{owner_key}_{workspace_suffix}"
                )
            )
        if conflict_path == "scheduler_bulk":
            await reply_sla_scheduler.ReplySlaScheduler()._sync()
        else:
            async with worker_sessions() as worker_session:
                overdue_emails = (
                    await worker_session.scalars(
                        select(Email)
                        .where(Email.id.in_(source_email_ids))
                        .order_by(Email.id)
                    )
                ).all()
                (
                    created_count,
                    _,
                ) = await reply_sla_escalation_service._process_fallback_escalation(
                    worker_session,
                    owner_key,
                    owner_key,
                    overdue_emails,
                    ReplayDateTime.now(date_time.timezone.utc),
                )
                assert created_count == 1
        async with replica_sessions() as replica_session:
            task_records = (
                await replica_session.scalars(
                    select(TicketTask).where(TicketTask.user_id == owner_key)
                )
            ).all()
            assert {task.related_email_id for task in task_records} == set(
                source_email_ids
            )
            assert len(task_records) == 2
            assert all(
                task.status == "blocked" and task.priority == "urgent"
                for task in task_records
            )
            assert any(task.task_uid == competing_task_uid for task in task_records)
    finally:
        await _clear_observed_mail(worker_sessions, owner_key)
        await worker_engine.dispose()
        await replica_engine.dispose()


async def test_deleted_mailbox_after_first_workspace_stops_remaining_work(monkeypatch):
    """A configuration removed after a successful commit must not authorize the next workspace."""
    worker_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    replica_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    worker_sessions = async_sessionmaker(worker_engine, expire_on_commit=False)
    replica_sessions = async_sessionmaker(replica_engine, expire_on_commit=False)
    owner_key = f"lease_scope_{uuid4().hex}"
    visited_workspaces = []
    create_tasks = reply_sla_scheduler.create_reply_sla_escalation_tasks
    replay_clock = SimpleNamespace(
        datetime=ReplayDateTime,
        timedelta=date_time.timedelta,
        timezone=date_time.timezone,
    )
    monkeypatch.setattr(reply_sla_escalation_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_tracking_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_sla_scheduler, "engine", worker_engine, raising=False)
    monkeypatch.setattr(reply_sla_scheduler, "AsyncSessionLocal", worker_sessions)

    async def remove_after_commit(database_session, **owner_scope):
        """Apply an independent committed mailbox deletion after the first actual task write."""
        visited_workspaces.append(owner_scope["workspace_id"])
        result = await create_tasks(database_session, **owner_scope)
        async with replica_sessions() as replica_session:
            await replica_session.execute(
                delete(TenantConfig).where(
                    TenantConfig.user_id == owner_key,
                    TenantConfig.organization_id == owner_key,
                )
            )
            await replica_session.commit()
        return result

    monkeypatch.setattr(
        reply_sla_scheduler, "create_reply_sla_escalation_tasks", remove_after_commit
    )
    try:
        for workspace_suffix in ("first", "second"):
            await _seed_observed_mail(
                worker_sessions, owner_key, f"{owner_key}_{workspace_suffix}"
            )
        await reply_sla_scheduler.ReplySlaScheduler()._sync()
        assert len(visited_workspaces) == 1
        async with replica_sessions() as replica_session:
            task_ids = (
                await replica_session.scalars(
                    select(TicketTask.task_uid).where(TicketTask.user_id == owner_key)
                )
            ).all()
            assert len(task_ids) == 1
    finally:
        await _clear_observed_mail(worker_sessions, owner_key)
        await worker_engine.dispose()
        await replica_engine.dispose()


@pytest.mark.parametrize(
    "exit_mode",
    ["complete", "acquire_cancel", "work_cancel", "unlock_error", "close_wait"],
)
async def test_one_slot_sweep_releases_lease_before_session_cleanup(
    monkeypatch, exit_mode
):
    """Real writes need one pool slot; cancellation cannot wait on session cleanup holding a lease."""
    worker_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    replica_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    worker_sessions = async_sessionmaker(worker_engine, expire_on_commit=False)
    replica_sessions = async_sessionmaker(replica_engine, expire_on_commit=False)
    owner_key = f"lease_scope_{uuid4().hex}"
    ready_event = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_allowed = asyncio.Event()
    never_ready = asyncio.Event()
    acquire_lease = reply_sla_scheduler._try_acquire_sweep_lease
    release_lease = reply_sla_scheduler._release_sweep_lease
    sweep_owners = reply_sla_scheduler.ReplySlaScheduler._sweep_configured_owners
    replay_clock = SimpleNamespace(
        datetime=ReplayDateTime,
        timedelta=date_time.timedelta,
        timezone=date_time.timezone,
    )
    monkeypatch.setattr(reply_sla_escalation_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_tracking_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_sla_scheduler, "engine", worker_engine, raising=False)

    class GatedCleanupSession(AsyncSession):
        """Model blocked session teardown while retaining real SQLAlchemy operations."""

        async def __aexit__(self, *error_state):
            """Expose the point before the normal shielded close is allowed."""
            if exit_mode == "close_wait":
                cleanup_started.set()
                await cleanup_allowed.wait()
            return await super().__aexit__(*error_state)

    monkeypatch.setattr(
        reply_sla_scheduler,
        "AsyncSessionLocal",
        async_sessionmaker(
            worker_engine, class_=GatedCleanupSession, expire_on_commit=False
        ),
    )

    async def acquire_then_pause(database_session):
        """Cancel after PostgreSQL acquired the lease but before caller acknowledgement."""
        acquired = await acquire_lease(database_session)
        assert acquired is True
        ready_event.set()
        await never_ready.wait()

    async def sweep_then_pause(scheduler, database_session):
        """Execute actual escalation before cancelling an in-progress cycle."""
        await sweep_owners(scheduler, database_session)
        ready_event.set()
        await never_ready.wait()

    async def fail_unlock(database_session):
        """Raise at the release boundary while the real lease remains held."""
        raise RuntimeError("Injected release failure.")

    if exit_mode == "acquire_cancel":
        monkeypatch.setattr(
            reply_sla_scheduler, "_try_acquire_sweep_lease", acquire_then_pause
        )
    elif exit_mode in {"work_cancel", "close_wait"}:
        monkeypatch.setattr(
            reply_sla_scheduler.ReplySlaScheduler,
            "_sweep_configured_owners",
            sweep_then_pause,
        )
    elif exit_mode == "unlock_error":
        monkeypatch.setattr(reply_sla_scheduler, "_release_sweep_lease", fail_unlock)

    sweep_task = None
    try:
        source_email_id = await _seed_observed_mail(worker_sessions, owner_key)
        sweep_task = asyncio.create_task(
            reply_sla_scheduler.ReplySlaScheduler()._sync()
        )
        if exit_mode.endswith("cancel") or exit_mode == "close_wait":
            await asyncio.wait_for(ready_event.wait(), 5)
            sweep_task.cancel()
            if exit_mode == "close_wait":
                await asyncio.wait_for(cleanup_started.wait(), 5)
                async with replica_sessions() as replica_session:
                    assert await acquire_lease(replica_session) is True
                    await release_lease(replica_session)
                cleanup_allowed.set()
            with pytest.raises(asyncio.CancelledError):
                await sweep_task
        elif exit_mode == "unlock_error":
            with pytest.raises(RuntimeError, match="Injected release failure"):
                await asyncio.wait_for(sweep_task, 5)
        else:
            await asyncio.wait_for(sweep_task, 5)
        async with replica_sessions() as replica_session:
            assert await acquire_lease(replica_session) is True
            await release_lease(replica_session)
            task_ids = (
                await replica_session.scalars(
                    select(TicketTask.related_email_id).where(
                        TicketTask.user_id == owner_key
                    )
                )
            ).all()
            assert task_ids == (
                [] if exit_mode == "acquire_cancel" else [source_email_id]
            )
        assert worker_engine.pool.checkedout() == 0
    finally:
        cleanup_allowed.set()
        if sweep_task is not None:
            if not sweep_task.done():
                sweep_task.cancel()
            await asyncio.gather(sweep_task, return_exceptions=True)
        await _clear_observed_mail(worker_sessions, owner_key)
        await worker_engine.dispose()
        await replica_engine.dispose()


@pytest.mark.parametrize(
    "failure_mode", ["transaction_error", "explicit_rollback", "disconnect"]
)
async def test_owner_failure_recovers_only_while_physical_lease_is_valid(
    monkeypatch, failure_mode
):
    """Recover healthy rollback, but never continue the sweep on a replacement backend."""
    worker_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    replica_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=1, max_overflow=0
    )
    worker_sessions = async_sessionmaker(worker_engine, expire_on_commit=False)
    replica_sessions = async_sessionmaker(replica_engine, expire_on_commit=False)
    owner_keys = [f"lease_scope_{uuid4().hex}" for _ in range(2)]
    visited_owners = []
    create_tasks = reply_sla_scheduler.create_reply_sla_escalation_tasks
    replay_clock = SimpleNamespace(
        datetime=ReplayDateTime,
        timedelta=date_time.timedelta,
        timezone=date_time.timezone,
    )
    monkeypatch.setattr(reply_sla_escalation_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_tracking_service, "datetime", replay_clock)
    monkeypatch.setattr(reply_sla_scheduler, "engine", worker_engine, raising=False)
    monkeypatch.setattr(reply_sla_scheduler, "AsyncSessionLocal", worker_sessions)

    async def fail_first_owner(database_session, **owner_scope):
        """Inject one real database failure before letting remaining owners proceed."""
        visited_owners.append(owner_scope["user_id"])
        if len(visited_owners) == 1:
            if failure_mode == "transaction_error":
                await database_session.execute(text("SELECT 1 / 0"))
            elif failure_mode == "explicit_rollback":
                await database_session.rollback()
                raise RuntimeError("Escalation operation failed.")
            else:
                worker_pid = await database_session.scalar(
                    text("SELECT pg_backend_pid()")
                )
                async with replica_sessions() as replica_session:
                    assert (
                        await replica_session.scalar(
                            text("SELECT pg_terminate_backend(:worker_pid)"),
                            {"worker_pid": worker_pid},
                        )
                        is True
                    )
                await database_session.scalar(text("SELECT 1"))
        return await create_tasks(database_session, **owner_scope)

    monkeypatch.setattr(
        reply_sla_scheduler, "create_reply_sla_escalation_tasks", fail_first_owner
    )
    try:
        for owner_key in owner_keys:
            await _seed_observed_mail(worker_sessions, owner_key)
        if failure_mode == "disconnect":
            with pytest.raises(DBAPIError) as error_info:
                await reply_sla_scheduler.ReplySlaScheduler()._sync()
            assert error_info.value.connection_invalidated
            assert len(visited_owners) == 1
        else:
            await reply_sla_scheduler.ReplySlaScheduler()._sync()
            assert set(visited_owners) == set(owner_keys)
        async with replica_sessions() as replica_session:
            task_owners = (
                await replica_session.scalars(
                    select(TicketTask.user_id).where(TicketTask.user_id.in_(owner_keys))
                )
            ).all()
            assert task_owners == (
                [] if failure_mode == "disconnect" else visited_owners[1:]
            )
            assert (
                await reply_sla_scheduler._try_acquire_sweep_lease(replica_session)
                is True
            )
            await reply_sla_scheduler._release_sweep_lease(replica_session)
    finally:
        for owner_key in owner_keys:
            await _clear_observed_mail(worker_sessions, owner_key)
        await worker_engine.dispose()
        await replica_engine.dispose()
