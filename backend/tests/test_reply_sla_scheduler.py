import asyncio
from types import SimpleNamespace

import pytest

from db.models import TenantConfig
from services.reply_sla_scheduler import ReplySlaScheduler, _sysrand


@pytest.fixture(autouse=True)
def lease_connection(monkeypatch):
    """Keep fast unit tests separate from the real PostgreSQL lease tests."""

    class LeaseConnection:
        """Record whether a failed sweep retires its physical connection."""

        invalidated = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def invalidate(self):
            self.invalidated = True

    connection = LeaseConnection()
    monkeypatch.setattr(
        "services.reply_sla_scheduler.engine",
        SimpleNamespace(connect=lambda: connection),
    )
    return connection


@pytest.mark.asyncio
async def test_reply_sla_scheduler_escalates_configured_mailbox_owners(monkeypatch):
    calls: list[dict[str, object]] = []

    class MockScalars:
        def all(self):
            return [1, 2]

    class MockResult:
        def scalars(self):
            return MockScalars()

    class MockSession:
        async def get(self, record_type, config_id, *, populate_existing=False):
            assert record_type is TenantConfig
            return {
                1: TenantConfig(
                    user_id="alice",
                    organization_id="org-acme",
                    smtp_username="alice@example.com",
                ),
                2: TenantConfig(
                    user_id="bob",
                    organization_id="org-beta",
                    imap_username="bob@example.com",
                ),
            }[config_id]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            self.statement = stmt
            return MockResult()

        async def scalars(self, stmt):
            return ["workspace-a"]

    session = MockSession()

    async def fake_create_reply_sla_escalation_tasks(
        db,
        *,
        user_id,
        organization_id,
        workspace_id,
        overdue_hours,
        limit,
        tenant_config,
    ):
        calls.append(
            {
                "db": db,
                "user_id": user_id,
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "overdue_hours": overdue_hours,
                "limit": limit,
                "tenant_config": tenant_config,
            }
        )

    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal",
        lambda *, bind: session,
    )
    monkeypatch.setattr(
        "services.reply_sla_scheduler.create_reply_sla_escalation_tasks",
        fake_create_reply_sla_escalation_tasks,
    )

    scheduler = ReplySlaScheduler(overdue_hours=24, limit=7)

    await scheduler._sync()

    assert calls == [
        {
            "db": session,
            "user_id": "alice",
            "organization_id": "org-acme",
            "workspace_id": "workspace-a",
            "overdue_hours": 24,
            "limit": 7,
            "tenant_config": calls[0]["tenant_config"],
        },
        {
            "db": session,
            "user_id": "bob",
            "organization_id": "org-beta",
            "workspace_id": "workspace-a",
            "overdue_hours": 24,
            "limit": 7,
            "tenant_config": calls[1]["tenant_config"],
        },
    ]
    assert calls[0]["tenant_config"].smtp_username == "alice@example.com"
    assert calls[1]["tenant_config"].imap_username == "bob@example.com"


@pytest.mark.asyncio
async def test_reply_sla_scheduler_continues_after_owner_escalation_failure(
    monkeypatch,
):
    calls: list[str] = []

    class MockScalars:
        def all(self):
            return [1, 2]

    class MockResult:
        def scalars(self):
            return MockScalars()

    class MockSession:
        async def get(self, record_type, config_id, *, populate_existing=False):
            assert record_type is TenantConfig
            return {
                1: TenantConfig(user_id="alice", organization_id="org-acme"),
                2: TenantConfig(user_id="bob", organization_id="org-beta"),
            }[config_id]

        async def rollback(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            return MockResult()

        async def scalars(self, stmt):
            return ["workspace-a"]

    async def fake_create_reply_sla_escalation_tasks(
        db,
        *,
        user_id,
        organization_id,
        workspace_id,
        overdue_hours,
        limit,
        tenant_config,
    ):
        calls.append(user_id)
        if user_id == "alice":
            raise RuntimeError("tenant escalation failed")

    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal",
        lambda *, bind: MockSession(),
    )
    monkeypatch.setattr(
        "services.reply_sla_scheduler.create_reply_sla_escalation_tasks",
        fake_create_reply_sla_escalation_tasks,
    )

    await ReplySlaScheduler()._sync()

    assert calls == ["alice", "bob"]


@pytest.mark.asyncio
async def test_reply_sla_scheduler_start_stop_cancels_loop(monkeypatch):
    scheduler = ReplySlaScheduler(interval_seconds=60)
    started = asyncio.Event()

    async def fake_run_loop():
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(scheduler, "_run_loop", fake_run_loop)

    await scheduler.start()
    await started.wait()
    assert scheduler._is_running is True
    assert scheduler._task is not None

    await scheduler.stop()

    assert scheduler._is_running is False


class _FakePostgresSession:
    """Session double whose bind reports postgresql and records scalar calls."""

    def __init__(self, lease_acquired: bool):
        self._lease_acquired = lease_acquired
        self.scalar_calls: list[object] = []
        self.executed = False

    def get_bind(self):
        from types import SimpleNamespace

        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def rollback(self):
        return None

    async def scalar(self, stmt, params=None):
        self.scalar_calls.append(stmt)
        if len(self.scalar_calls) == 1:
            return self._lease_acquired
        return True  # unlock result

    async def execute(self, stmt):
        self.executed = True

        class _Result:
            def scalars(self):
                class _Scalars:
                    def all(self):
                        return []

                return _Scalars()

        return _Result()


@pytest.mark.asyncio
async def test_sync_skips_sweep_when_lease_held_elsewhere(monkeypatch):
    session = _FakePostgresSession(lease_acquired=False)
    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal", lambda *, bind: session
    )

    scheduler = ReplySlaScheduler()
    await scheduler._sync()

    assert session.executed is False  # sweep skipped entirely
    assert len(session.scalar_calls) == 1  # only the try-lock, no unlock


@pytest.mark.asyncio
async def test_sync_sweeps_and_releases_lease_when_acquired(monkeypatch):
    session = _FakePostgresSession(lease_acquired=True)
    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal", lambda *, bind: session
    )

    scheduler = ReplySlaScheduler()
    await scheduler._sync()

    assert session.executed is True  # sweep ran
    assert len(session.scalar_calls) == 2  # try-lock + unlock


@pytest.mark.asyncio
async def test_sync_retires_lease_connection_when_sweep_fails(
    monkeypatch, lease_connection
):
    session = _FakePostgresSession(lease_acquired=True)

    async def boom(self, _session):
        raise RuntimeError("sweep failed")

    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal", lambda *, bind: session
    )
    monkeypatch.setattr(
        ReplySlaScheduler, "_sweep_configured_owners", boom, raising=True
    )

    scheduler = ReplySlaScheduler()
    with pytest.raises(RuntimeError):
        await scheduler._sync()

    assert len(session.scalar_calls) == 1
    assert lease_connection.invalidated is True


@pytest.mark.asyncio
async def test_start_ignores_second_call_while_running(monkeypatch):
    """A second start() must not spawn a duplicate loop task."""
    scheduler = ReplySlaScheduler(interval_seconds=60)
    started = asyncio.Event()

    async def fake_run_loop():
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(scheduler, "_run_loop", fake_run_loop)

    await scheduler.start()
    await started.wait()
    first_task = scheduler._task

    # Guard must short-circuit: same task, still running, no second create_task.
    await scheduler.start()
    assert scheduler._task is first_task
    assert scheduler._is_running is True

    await scheduler.stop()
    assert scheduler._is_running is False


@pytest.mark.asyncio
async def test_stop_is_noop_when_not_running():
    """stop() before start() must return without touching any task."""
    scheduler = ReplySlaScheduler()
    cancel_called = False

    class _StaleTask:
        def cancel(self):
            nonlocal cancel_called
            cancel_called = True

    # Simulate a stale reference while the scheduler is not running; the guard
    # must return before reaching the cancel path.
    scheduler._task = _StaleTask()

    await scheduler.stop()

    assert cancel_called is False
    assert scheduler._is_running is False


@pytest.mark.asyncio
async def test_run_loop_cancelled_during_startup_jitter_skips_sweep(monkeypatch):
    """Cancelling during the startup jitter returns before any sweep runs."""
    scheduler = ReplySlaScheduler(interval_seconds=600)
    # Long jitter so the loop is parked in the initial sleep when we cancel.
    monkeypatch.setattr(_sysrand, "uniform", lambda _a, _b: 600)

    swept = False

    async def fake_sync():
        nonlocal swept
        swept = True

    monkeypatch.setattr(scheduler, "_sync", fake_sync)

    await scheduler.start()
    await asyncio.sleep(0)  # let the loop reach the jitter sleep
    await scheduler.stop()  # cancels during startup jitter

    assert swept is False  # cancelled before the first sweep
    assert scheduler._is_running is False


@pytest.mark.asyncio
async def test_run_loop_sweeps_then_stops_on_interval_cancel(monkeypatch):
    """The loop performs a sweep, then stop() cancels the interval sleep."""
    scheduler = ReplySlaScheduler(interval_seconds=600)
    monkeypatch.setattr(_sysrand, "uniform", lambda _a, _b: 0)  # instant jitter

    sync_calls = 0
    swept = asyncio.Event()

    async def fake_sync():
        nonlocal sync_calls
        sync_calls += 1
        swept.set()

    monkeypatch.setattr(scheduler, "_sync", fake_sync)

    await scheduler.start()
    await asyncio.wait_for(swept.wait(), timeout=1)
    assert sync_calls >= 1

    # Scheduler is now parked in the interval sleep; stop() must cancel it.
    await scheduler.stop()
    assert scheduler._is_running is False


@pytest.mark.asyncio
async def test_run_loop_breaks_when_sync_is_cancelled(monkeypatch):
    """A CancelledError from _sync stops the loop instead of retrying."""
    scheduler = ReplySlaScheduler(interval_seconds=600)
    monkeypatch.setattr(_sysrand, "uniform", lambda _a, _b: 0)

    sync_calls = 0
    done = asyncio.Event()

    async def cancelling_sync():
        nonlocal sync_calls
        sync_calls += 1
        done.set()
        raise asyncio.CancelledError

    monkeypatch.setattr(scheduler, "_sync", cancelling_sync)

    await scheduler.start()
    await asyncio.wait_for(done.wait(), timeout=1)
    done_tasks, pending_tasks = await asyncio.wait({scheduler._task}, timeout=1)

    assert scheduler._task in done_tasks
    assert pending_tasks == set()
    assert scheduler._task.result() is None

    assert sync_calls == 1  # no retry after cancellation

    await scheduler.stop()


@pytest.mark.asyncio
async def test_run_loop_survives_sync_exception(monkeypatch):
    """A non-cancel exception from _sync is logged and the loop keeps running."""
    scheduler = ReplySlaScheduler(interval_seconds=600)
    monkeypatch.setattr(_sysrand, "uniform", lambda _a, _b: 0)

    attempts = 0
    raised = asyncio.Event()

    async def flaky_sync():
        nonlocal attempts
        attempts += 1
        raised.set()
        raise RuntimeError("sweep boom")

    monkeypatch.setattr(scheduler, "_sync", flaky_sync)

    await scheduler.start()
    await asyncio.wait_for(raised.wait(), timeout=1)

    # The loop must survive the error and remain running (parked on interval sleep).
    assert attempts >= 1
    assert scheduler._is_running is True

    await scheduler.stop()
    assert scheduler._is_running is False


@pytest.mark.asyncio
@pytest.mark.parametrize("unlock_result", [False, None, 1, "true"])
async def test_unconfirmed_unlock_retires_the_connection(
    monkeypatch, lease_connection, unlock_result
):
    """False and truthy non-boolean replies cannot admit a connection back to the pool."""
    session = _FakePostgresSession(lease_acquired=True)

    async def scalar_result(statement, params=None):
        session.scalar_calls.append(statement)
        return True if len(session.scalar_calls) == 1 else unlock_result

    monkeypatch.setattr(session, "scalar", scalar_result)
    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal", lambda *, bind: session
    )
    with pytest.raises(RuntimeError, match="release was not confirmed"):
        await ReplySlaScheduler()._sync()
    assert lease_connection.invalidated is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delete_phase", ["before_workspaces", "before_first_workspace"]
)
async def test_deleted_owner_is_not_escalated(monkeypatch, delete_phase):
    """A configuration deleted after selection must not reach escalation."""
    session = _FakePostgresSession(lease_acquired=True)
    lookup_count = 0

    async def selected_owners(statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [42]))

    async def deleted_owner(record_type, record_key, *, populate_existing=False):
        nonlocal lookup_count
        lookup_count += 1
        assert record_type is TenantConfig and record_key == 42
        if delete_phase == "before_first_workspace" and lookup_count == 1:
            return TenantConfig(user_id="owner_scope", organization_id="tenant_scope")
        return None

    async def selected_workspaces(statement):
        return ["workspace_scope"]

    async def unexpected_escalation(*args, **kwargs):
        pytest.fail("Deleted owner reached escalation.")

    monkeypatch.setattr(session, "execute", selected_owners)
    monkeypatch.setattr(session, "get", deleted_owner, raising=False)
    monkeypatch.setattr(session, "scalars", selected_workspaces, raising=False)
    monkeypatch.setattr(
        "services.reply_sla_scheduler.AsyncSessionLocal", lambda *, bind: session
    )
    monkeypatch.setattr(
        "services.reply_sla_scheduler.create_reply_sla_escalation_tasks",
        unexpected_escalation,
    )
    await ReplySlaScheduler()._sync()
    assert len(session.scalar_calls) == 2


@pytest.mark.asyncio
async def test_stop_handles_running_state_without_task():
    """Stopping an incompletely started scheduler clears its running state."""
    scheduler = ReplySlaScheduler()
    scheduler._is_running = True
    await scheduler.stop()
    assert scheduler._is_running is False


@pytest.mark.asyncio
async def test_loop_exits_without_sleep_after_sweep_clears_running(monkeypatch):
    """A sweep that stops the scheduler must not park for another interval."""
    scheduler = ReplySlaScheduler()
    scheduler._is_running = True
    monkeypatch.setattr(_sysrand, "uniform", lambda *_args: 0)

    async def stopping_sweep():
        scheduler._is_running = False

    monkeypatch.setattr(scheduler, "_sync", stopping_sweep)
    await scheduler._run_loop()
    assert scheduler._is_running is False
