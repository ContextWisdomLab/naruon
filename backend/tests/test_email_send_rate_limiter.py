import asyncio
import datetime
import time
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
import jwt
from httpx import ASGITransport, AsyncClient

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import AuthContext
from api import emails as emails_api
from core.config import settings
from db.models import SecurityAuditEvent, TenantConfig
from db.session import get_db
from main import app
import services.email_send_rate_limiter as limiter_module


class _Result:
    def __init__(self, row=0):
        self.row = row

    def scalar_one(self):
        return self.row


class _SharedAttemptStore:
    def __init__(self):
        self.events = []
        self.lock = asyncio.Lock()


class _PostgresSession:
    def __init__(self, store, *, database_now: datetime.datetime | None = None):
        self.store = store
        self.added = []
        self.queries = []
        self.lock_held = False
        self.pending = []
        self.isolation_level = None
        self.database_now = database_now or datetime.datetime(
            2026, 8, 19, tzinfo=datetime.timezone.utc
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        if self.lock_held:
            self.store.lock.release()
            self.lock_held = False

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def connection(self, *, execution_options):
        self.isolation_level = execution_options["isolation_level"]
        return self

    async def execute(self, query, params=None):
        query_text = str(query).lower()
        self.queries.append(query_text)
        if "pg_advisory_xact_lock" in query_text:
            await self.store.lock.acquire()
            self.lock_held = True
            return _Result()
        if "clock_timestamp" in query_text:
            return _Result(self.database_now)
        if query_text.startswith("delete from security_audit_events"):
            values = tuple(query.compile().params.values())
            resource_uid = next(
                value for value in values if str(value).startswith("email_send_scope:")
            )
            event_action = next(
                value
                for value in values
                if str(value).startswith("email_send_rate_limit.")
            )
            cutoff = next(
                value for value in values if isinstance(value, datetime.datetime)
            )
            retained_events = [
                event
                for event in self.store.events
                if not (
                    event.resource_uid == resource_uid
                    and event.event_action == event_action
                    and event.observed_at <= cutoff
                )
            ]
            deleted_count = len(self.store.events) - len(retained_events)
            self.store.events = retained_events
            return _Result(deleted_count)
        if "security_audit_events" in query_text:
            values = tuple(query.compile().params.values())
            resource_uid = next(
                value for value in values if str(value).startswith("email_send_scope:")
            )
            event_action = next(
                value
                for value in values
                if str(value).startswith("email_send_rate_limit.")
            )
            window_started_at = next(
                value for value in values if isinstance(value, datetime.datetime)
            )
            return _Result(
                sum(
                    event.resource_uid == resource_uid
                    and event.event_action == event_action
                    and event.observed_at > window_started_at
                    for event in self.store.events
                )
            )
        raise AssertionError(f"unexpected query: {query_text}")

    def add(self, item):
        self.added.append(item)
        if isinstance(item, SecurityAuditEvent):
            self.pending.append(item)

    async def commit(self):
        self.store.events.extend(self.pending)
        self.pending.clear()
        if self.lock_held:
            self.store.lock.release()
            self.lock_held = False

    async def rollback(self):
        self.pending.clear()
        if self.lock_held:
            self.store.lock.release()
            self.lock_held = False


def _context(
    user_id="user-1", organization_id="org-1", workspace_id: str | None = None
):
    return AuthContext(
        user_id=user_id,
        role="member",
        organization_id=organization_id,
        group_ids=(),
        workspace_id=workspace_id or f"workspace-{organization_id or user_id}",
    )


@pytest.mark.asyncio
async def test_sliding_window_limits_concurrent_workers_without_cross_scope_leakage(
    monkeypatch,
):
    store = _SharedAttemptStore()
    monkeypatch.setattr(
        limiter_module, "AsyncSessionLocal", lambda: _PostgresSession(store)
    )
    observed_at = datetime.datetime(2026, 8, 19, tzinfo=datetime.timezone.utc)

    async def attempt(user_id):
        return await limiter_module.enforce_send_email_rate_limit(
            _context(user_id), now=observed_at
        )

    same_scope = await asyncio.gather(*(attempt("user-1") for _ in range(11)))
    other_scope = await asyncio.gather(*(attempt("user-2") for _ in range(10)))
    other_workspace = await asyncio.gather(
        *(
            limiter_module.enforce_send_email_rate_limit(
                _context("user-1", workspace_id="workspace-2"), now=observed_at
            )
            for _ in range(10)
        )
    )

    assert sum(decision.allowed for decision in same_scope) == 10
    assert sum(not decision.allowed for decision in same_scope) == 1
    assert all(decision.allowed for decision in other_scope)
    assert all(decision.allowed for decision in other_workspace)

    rollover = await limiter_module.enforce_send_email_rate_limit(
        _context("user-1"),
        now=observed_at + datetime.timedelta(seconds=61),
    )
    assert rollover.allowed is True
    scope_uid = (
        "email_send_scope:"
        f"{limiter_module.rate_limit_scope_hash('user-1', 'org-1', 'workspace-org-1')}"
    )
    assert sum(event.resource_uid == scope_uid for event in store.events) == 2


@pytest.mark.asyncio
async def test_sliding_window_blocks_boundary_burst(monkeypatch):
    store = _SharedAttemptStore()
    monkeypatch.setattr(
        limiter_module, "AsyncSessionLocal", lambda: _PostgresSession(store)
    )
    started_at = datetime.datetime(2026, 8, 19, tzinfo=datetime.timezone.utc)

    for offset_seconds in range(50, 60):
        decision = await limiter_module.enforce_send_email_rate_limit(
            _context(),
            now=started_at + datetime.timedelta(seconds=offset_seconds),
        )
        assert decision.allowed is True

    blocked = await limiter_module.enforce_send_email_rate_limit(
        _context(),
        now=started_at + datetime.timedelta(seconds=61),
    )
    assert blocked.allowed is False
    for offset_seconds in range(62, 72):
        assert not (
            await limiter_module.enforce_send_email_rate_limit(
                _context(),
                now=started_at + datetime.timedelta(seconds=offset_seconds),
            )
        ).allowed
    assert (
        sum(
            event.event_action == "email_send_rate_limit.quota_exhausted"
            for event in store.events
        )
        == 1
    )


@pytest.mark.asyncio
async def test_limiter_prunes_expired_allowed_state_but_keeps_denial_evidence(
    monkeypatch,
):
    store = _SharedAttemptStore()
    observed_at = datetime.datetime(2026, 8, 19, 12, 0, tzinfo=datetime.timezone.utc)
    scope_hash = limiter_module.rate_limit_scope_hash(
        "user-1", "org-1", "workspace-org-1"
    )
    scope_uid = f"email_send_scope:{scope_hash}"
    expired_at = observed_at - datetime.timedelta(seconds=61)
    expired_allowed = SecurityAuditEvent(
        actor_user_id="user-1",
        actor_role="member",
        organization_id="org-1",
        workspace_id="workspace-org-1",
        event_action="email_send_rate_limit.allowed",
        resource_type="email_send_rate_limit",
        resource_uid=scope_uid,
        evidence_source="services.email_send_rate_limiter",
        observed_at=expired_at,
    )
    durable_denial = SecurityAuditEvent(
        actor_user_id="user-1",
        actor_role="member",
        organization_id="org-1",
        workspace_id="workspace-org-1",
        event_action="email_send_rate_limit.quota_exhausted",
        resource_type="email_send_rate_limit",
        resource_uid=scope_uid,
        evidence_source="services.email_send_rate_limiter",
        observed_at=expired_at,
    )
    store.events.extend([expired_allowed, durable_denial])
    session = _PostgresSession(store)
    monkeypatch.setattr(limiter_module, "AsyncSessionLocal", lambda: session)

    decision = await limiter_module.enforce_send_email_rate_limit(
        _context(), now=observed_at
    )

    assert decision.allowed is True
    assert expired_allowed not in store.events
    assert durable_denial in store.events
    assert (
        sum(
            event.event_action == "email_send_rate_limit.allowed"
            and event.resource_uid == scope_uid
            for event in store.events
        )
        == 1
    )
    delete_query_index = next(
        index
        for index, query in enumerate(session.queries)
        if query.startswith("delete from security_audit_events")
    )
    count_query_index = next(
        index
        for index, query in enumerate(session.queries)
        if "count(" in query and "security_audit_events" in query
    )
    assert delete_query_index < count_query_index


@pytest.mark.asyncio
async def test_limiter_uses_owned_transaction_and_non_sensitive_audit_state(
    monkeypatch,
):
    store = _SharedAttemptStore()
    session = _PostgresSession(store)
    monkeypatch.setattr(limiter_module, "AsyncSessionLocal", lambda: session)
    decision = await limiter_module.enforce_send_email_rate_limit(
        _context(),
        now=datetime.datetime(2026, 8, 19, tzinfo=datetime.timezone.utc),
    )

    assert decision.allowed is True
    assert any("pg_advisory_xact_lock" in query for query in session.queries)
    assert session.isolation_level == "READ COMMITTED"
    audit = next(item for item in session.added if isinstance(item, SecurityAuditEvent))
    assert "user-1" not in repr(audit)
    assert "org-1" not in repr(audit)
    assert audit.event_action == "email_send_rate_limit.allowed"


@pytest.mark.asyncio
async def test_limiter_uses_database_clock_after_scope_lock(monkeypatch):
    store = _SharedAttemptStore()
    database_now = datetime.datetime(
        2026, 8, 19, 12, 34, 56, tzinfo=datetime.timezone.utc
    )
    session = _PostgresSession(store, database_now=database_now)
    monkeypatch.setattr(limiter_module, "AsyncSessionLocal", lambda: session)

    decision = await limiter_module.enforce_send_email_rate_limit(_context())

    assert decision.allowed is True
    lock_query_index = next(
        index
        for index, query in enumerate(session.queries)
        if "pg_advisory_xact_lock" in query
    )
    clock_query_index = next(
        index
        for index, query in enumerate(session.queries)
        if "clock_timestamp" in query
    )
    assert lock_query_index < clock_query_index
    audit = next(item for item in session.added if isinstance(item, SecurityAuditEvent))
    assert audit.observed_at == database_now


@pytest.mark.asyncio
async def test_rate_limiter_fails_closed_when_shared_state_is_unavailable():
    class _UnavailableSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    original_factory = limiter_module.AsyncSessionLocal
    limiter_module.AsyncSessionLocal = lambda: _UnavailableSession()
    try:
        with pytest.raises(limiter_module.EmailSendRateLimitUnavailable):
            await limiter_module.enforce_send_email_rate_limit(_context())
    finally:
        limiter_module.AsyncSessionLocal = original_factory


@pytest_asyncio.fixture
async def migrated_limiter_sessions(monkeypatch):
    """Use the runner's migrated schema, never create missing runtime tables."""
    from asyncpg.exceptions import InvalidAuthorizationSpecificationError
    from asyncpg.exceptions import InvalidPasswordError
    from sqlalchemy.exc import OperationalError

    engine = create_async_engine(settings.DATABASE_URL, pool_size=4, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    scope_suffix = uuid.uuid4().hex
    try:
        try:
            async with session_factory() as session:
                await session.execute(select(SecurityAuditEvent.event_uid).limit(0))
        except (
            InvalidAuthorizationSpecificationError,
            InvalidPasswordError,
            OperationalError,
            OSError,
        ):
            pytest.skip("PostgreSQL smoke database unavailable")
        monkeypatch.setattr(limiter_module, "AsyncSessionLocal", session_factory)
        try:
            yield session_factory, scope_suffix
        finally:
            async with session_factory() as session:
                await session.execute(
                    delete(SecurityAuditEvent).where(
                        SecurityAuditEvent.actor_user_id.in_(
                            [f"send-user-{scope_suffix}", f"send-peer-{scope_suffix}"]
                        )
                    )
                )
                await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_real_postgres_concurrent_quota_isolates_each_scope_dimension(
    migrated_limiter_sessions,
):
    """Missing locks or a missing scope dimension must violate the 10/20 result."""
    session_factory, scope_suffix = migrated_limiter_sessions
    contexts = [
        _context(f"send-user-{scope_suffix}", "send-org", "send-workspace"),
        _context(f"send-peer-{scope_suffix}", "send-org", "send-workspace"),
        _context(f"send-user-{scope_suffix}", "send-other-org", "send-workspace"),
        _context(f"send-user-{scope_suffix}", "send-org", "send-other-workspace"),
    ]
    decisions = await asyncio.gather(
        *(
            limiter_module.enforce_send_email_rate_limit(context)
            for context in contexts
            for _ in range(20)
        )
    )
    for scope_index, context in enumerate(contexts):
        scope_decisions = decisions[scope_index * 20 : (scope_index + 1) * 20]
        assert sum(decision.allowed for decision in scope_decisions) == 10
        async with session_factory() as session:
            action_counts = dict(
                (
                    await session.execute(
                        select(SecurityAuditEvent.event_action, func.count())
                        .where(
                            SecurityAuditEvent.actor_user_id == context.user_id,
                            SecurityAuditEvent.organization_id
                            == context.organization_id,
                            SecurityAuditEvent.workspace_id == context.workspace_id,
                        )
                        .group_by(SecurityAuditEvent.event_action)
                    )
                ).all()
            )
        assert action_counts == {
            "email_send_rate_limit.allowed": 10,
            "email_send_rate_limit.quota_exhausted": 1,
        }


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_real_postgres_window_expires_on_database_clock(
    migrated_limiter_sessions,
):
    """Wait the real production window; no reduced quota or injected timestamp."""
    session_factory, scope_suffix = migrated_limiter_sessions
    context = _context(f"send-user-{scope_suffix}")
    for _ in range(10):
        assert (await limiter_module.enforce_send_email_rate_limit(context)).allowed
    assert not (await limiter_module.enforce_send_email_rate_limit(context)).allowed
    await asyncio.sleep(61)
    assert (await limiter_module.enforce_send_email_rate_limit(context)).allowed
    async with session_factory() as session:
        actions = (
            (
                await session.execute(
                    select(SecurityAuditEvent.event_action).where(
                        SecurityAuditEvent.actor_user_id == context.user_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert sorted(actions) == [
        "email_send_rate_limit.allowed",
        "email_send_rate_limit.quota_exhausted",
    ]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_cancelled_lock_wait_returns_single_pool_slot(
    migrated_limiter_sessions,
    monkeypatch,
):
    """A cancelled in-flight reservation must release its connection, not quota."""
    session_factory, scope_suffix = migrated_limiter_sessions
    context = _context(f"send-user-{scope_suffix}")
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        connect_args={"server_settings": {"application_name": scope_suffix}},
    )
    monkeypatch.setattr(limiter_module, "AsyncSessionLocal", async_sessionmaker(engine))
    pending_attempt = None
    try:
        async with session_factory() as lock_session:
            scope_hash = limiter_module.rate_limit_scope_hash(
                context.user_id, context.organization_id, context.workspace_id
            )
            await lock_session.execute(
                select(func.pg_advisory_xact_lock(limiter_module._lock_key(scope_hash)))
            )
            pending_attempt = asyncio.create_task(
                limiter_module.enforce_send_email_rate_limit(context)
            )
            async with asyncio.timeout(5):
                while True:
                    # Statistics are transaction-cached; refresh the observation
                    # without releasing the transaction-scoped barrier lock.
                    await lock_session.execute(select(func.pg_stat_clear_snapshot()))
                    waiting_count = (
                        await lock_session.execute(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE application_name = :application_name "
                                "AND wait_event = 'advisory'"
                            ),
                            {"application_name": scope_suffix},
                        )
                    ).scalar_one()
                    if waiting_count:
                        break
                    await asyncio.sleep(0.01)
            pending_attempt.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending_attempt
            assert engine.pool.checkedout() == 0
            await lock_session.rollback()
        assert (await limiter_module.enforce_send_email_rate_limit(context)).allowed
        async with session_factory() as session:
            assert (
                await session.execute(
                    select(func.count())
                    .select_from(SecurityAuditEvent)
                    .where(SecurityAuditEvent.actor_user_id == context.user_id)
                )
            ).scalar_one() == 1
    finally:
        if pending_attempt is not None:
            pending_attempt.cancel()
            await asyncio.gather(pending_attempt, return_exceptions=True)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_signed_send_route_shares_single_pool_slot(
    migrated_limiter_sessions, monkeypatch
):
    """Dropping the request rollback must prevent this signed send from finishing."""
    _, scope_suffix = migrated_limiter_sessions
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = f"send-user-{scope_suffix}"

    async def request_session():
        """Keep the real request session open until the HTTP request exits."""
        async with session_factory() as session:
            yield session

    async def smtp_boundary(*, message_params, smtp_config):
        """Do not send mail; verify only the call at the network boundary."""
        assert message_params.to_address == "recipient@example.com"
        assert smtp_config.smtp_server == "mail.example.invalid"
        assert smtp_config.smtp_username == user_id
        assert engine.pool.checkedout() == 0
        return {"status": "sent", "simulated": False}

    monkeypatch.setitem(app.dependency_overrides, get_db, request_session)
    monkeypatch.setattr(limiter_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(emails_api, "send_email", smtp_boundary)
    monkeypatch.setattr(
        emails_api,
        "validate_smtp_destination",
        lambda smtp_server, smtp_port: (smtp_server, smtp_port),
    )
    token = jwt.encode(
        {
            "ver": 1,
            "iss": "naruon-control-plane",
            "aud": "naruon-api",
            "sub": user_id,
            "role": "member",
            "org": "send-org",
            "groups": [],
            "workspace": "send-workspace",
            "exp": int(time.time()) + 300,
        },
        settings.AUTH_SESSION_HMAC_SECRET.get_secret_value(),
        algorithm="HS256",
    )
    try:
        async with session_factory() as session:
            session.add(
                TenantConfig(
                    user_id=user_id,
                    organization_id="send-org",
                    smtp_port=587,
                    smtp_server="mail.example.invalid",
                    smtp_username=user_id,
                )
            )
            await session.commit()
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/emails/send",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "to": "recipient@example.com",
                    "subject": "Pool regression",
                    "body": "Body",
                },
            )
        assert response.status_code == 200, response.json()
        assert response.json() == {"status": "sent", "simulated": False}
        assert engine.pool.checkedout() == 0
        async with session_factory() as session:
            assert (
                await session.execute(
                    select(func.count())
                    .select_from(SecurityAuditEvent)
                    .where(SecurityAuditEvent.actor_user_id == user_id)
                )
            ).scalar_one() == 1
    finally:
        try:
            async with session_factory() as session:
                await session.execute(
                    delete(TenantConfig).where(TenantConfig.user_id == user_id)
                )
                await session.commit()
        finally:
            await engine.dispose()
