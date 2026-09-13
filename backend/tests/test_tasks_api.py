import base64
import datetime
import hashlib
import hmac
import json
import os
import time
import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from api.auth import get_auth_context
from core.config import settings
from db.models import Email, TenantConfig, TicketTask
from db.session import get_db
from main import app

pytestmark = pytest.mark.usefixtures("dev_auth_dependency_overrides")
TEST_SESSION_HMAC_SECRET = os.environ["AUTH_SESSION_HMAC_SECRET"]


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_session_token(payload: dict[str, object]) -> str:
    header_segment = _base64url_encode(
        json.dumps(
            {"alg": "HS256", "typ": "JWT"}, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(
        TEST_SESSION_HMAC_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def _valid_session_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ver": 1,
        "iss": "naruon-control-plane",
        "aud": "naruon-api",
        "sub": "alice",
        "role": "member",
        "org": "org-acme",
        "groups": [],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return payload


class MockTaskSession:
    def __init__(self) -> None:
        self.emails: dict[int, Email] = {}
        self.tasks: list[TicketTask] = []
        self.tenant_config: TenantConfig | None = TenantConfig(
            user_id="alice",
            smtp_username="alice@example.com",
            imap_username=None,
        )

    async def get(self, model, primary_key):
        if model is Email:
            return self.emails.get(primary_key)
        return None

    async def execute(self, stmt):
        descriptions = getattr(stmt, "column_descriptions", [])

        class MockScalars:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        class MockResult:
            def __init__(self, items):
                self._items = items

            def scalars(self):
                return MockScalars(self._items)

            def all(self):
                return self._items

            def scalar_one_or_none(self):
                if not self._items:
                    return None
                if len(self._items) > 1:
                    raise AssertionError("Mock result expected at most one row")
                return self._items[0]

            def one_or_none(self):
                return self.scalar_one_or_none()

        if descriptions and descriptions[0].get("entity") is TenantConfig:
            return MockResult(
                [] if self.tenant_config is None else [self.tenant_config]
            )

        if descriptions and descriptions[0].get("entity") is Email:
            params = stmt.compile().params
            source_email_id = params.get("message_id_1")
            user_id = params.get("user_id_1")
            organization_id = params.get("organization_id_1")
            minimum_date = next(
                (
                    value
                    for key, value in params.items()
                    if key.startswith("date_")
                    and isinstance(value, datetime.datetime)
                ),
                None,
            )
            return MockResult(
                [
                    email
                    for email in self.emails.values()
                    if (source_email_id is None or email.message_id == source_email_id)
                    and (user_id is None or email.user_id == user_id)
                    and (
                        organization_id is None
                        or email.organization_id == organization_id
                    )
                    and (minimum_date is None or email.date > minimum_date)
                ]
            )

        if descriptions and descriptions[0].get("entity") is TicketTask:
            statement_text = str(stmt).lower()
            try:
                params = stmt.compile().params
            except Exception:
                params = {}
            task_uid = params.get("task_uid_1")
            user_id = params.get("user_id_1")
            organization_id = params.get("organization_id_1")
            source_type = params.get("source_type_1")
            related_email_id = params.get("email_id_1")
            returns_joined_email = len(descriptions) > 1
            scoped_email_join = (
                "email_records.user_id" in statement_text
                and "email_records.organization_id" in statement_text
            )

            def source_message_id(task: TicketTask) -> str | None:
                if task.related_email_id is None:
                    return None
                source_email = self.emails.get(task.related_email_id)
                if source_email is None:
                    return None
                if scoped_email_join and (
                    source_email.user_id != task.user_id
                    or source_email.organization_id != task.organization_id
                ):
                    return None
                return source_email.message_id

            if (
                related_email_id is None
                and "ticket_tasks.email_id in" in statement_text
            ):
                related_email_ids: list[int] = []
                for key, value in params.items():
                    if not key.startswith("email_id"):
                        continue
                    if isinstance(value, int):
                        related_email_ids.append(value)
                    elif isinstance(value, (list, tuple, set)):
                        related_email_ids.extend(
                            candidate
                            for candidate in value
                            if isinstance(candidate, int)
                        )
                if related_email_ids:
                    related_email_id = related_email_ids

            matching_tasks = [
                task
                for task in self.tasks
                if (task_uid is None or task.task_uid == task_uid)
                and (user_id is None or task.user_id == user_id)
                and (
                    organization_id is None or task.organization_id == organization_id
                )
                and (source_type is None or task.source_type == source_type)
                and (
                    related_email_id is None
                    or (
                        isinstance(related_email_id, (list, tuple, set))
                        and task.related_email_id in related_email_id
                    )
                    or (
                        not isinstance(related_email_id, (list, tuple, set))
                        and task.related_email_id == related_email_id
                    )
                )
            ]
            if returns_joined_email:
                return MockResult(
                    [(task, source_message_id(task)) for task in matching_tasks]
                )
            return MockResult(matching_tasks)

        return MockResult(self.tasks)

    def add(self, obj):
        if isinstance(obj, TicketTask):
            if obj.source_type == "reply_sla" and any(
                task.user_id == obj.user_id
                and task.organization_id == obj.organization_id
                and task.source_type == obj.source_type
                and task.related_email_id == obj.related_email_id
                for task in self.tasks
                if task is not obj
            ):
                raise IntegrityError("duplicate reply_sla task", {}, None)
            obj.id = len(self.tasks) + 1
            if not getattr(obj, "task_uid", None):
                obj.task_uid = uuid.uuid4().hex
            now = datetime.datetime.now(datetime.timezone.utc)
            obj.created_at = now
            obj.updated_at = now
            self.tasks.append(obj)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass

    @asynccontextmanager
    async def begin_nested(self):
        yield

    async def flush(self):
        pass


mock_session = MockTaskSession()


@pytest.fixture(autouse=True)
def override_get_db():
    app.dependency_overrides[get_db] = lambda: mock_session
    yield
    app.dependency_overrides.pop(get_db, None)
    mock_session.emails = {}
    mock_session.tasks = []
    mock_session.tenant_config = TenantConfig(
        user_id="alice",
        smtp_username="alice@example.com",
        imap_username=None,
    )


@pytest.fixture
def auth_client():
    with TestClient(
        app,
        headers={"X-User-Id": "alice", "X-Organization-Id": "org-acme"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_mock_task_session_related_email_in_ignores_unrelated_int_params():
    session = MockTaskSession()
    now = datetime.datetime.now(datetime.timezone.utc)
    session.tasks.extend(
        [
            TicketTask(
                id=1,
                task_uid="email-21",
                user_id="alice",
                organization_id="org-acme",
                title="Related email 21",
                status="blocked",
                priority="urgent",
                source_type="reply_sla",
                related_email_id=21,
                related_thread_id="thread-21",
                created_at=now,
                updated_at=now,
            ),
            TicketTask(
                id=999,
                task_uid="email-999",
                user_id="alice",
                organization_id="org-acme",
                title="Unrelated task id",
                status="blocked",
                priority="urgent",
                source_type="reply_sla",
                related_email_id=999,
                related_thread_id="thread-999",
                created_at=now,
                updated_at=now,
            ),
        ]
    )

    class FakeCompiled:
        params = {"email_id_2": [21], "task_id_1": 999}

    class FakeStatement:
        column_descriptions = [{"entity": TicketTask}]

        def compile(self):
            return FakeCompiled()

        def __str__(self):
            return (
                "SELECT * FROM ticket_tasks "
                "WHERE ticket_tasks.email_id IN (__[POSTCOMPILE_email_id_2]) "
                "AND ticket_tasks.task_id = :task_id_1"
            )

    result = await session.execute(FakeStatement())

    assert [task.related_email_id for task in result.scalars().all()] == [21]


def test_create_ticket_tasks_accepts_signed_bearer_session():
    mock_session.emails[14] = make_email()
    app.dependency_overrides.pop(get_auth_context, None)
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())

    try:
        with TestClient(
            app,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = client.post(
                "/api/tasks/from-email",
                json={
                    "source_email_id": "<message-14@example.com>",
                    "items": ["담당자 확인"],
                },
            )
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["tasks"][0]["source_email_id"] == "<message-14@example.com>"
    assert "user_id" not in body["tasks"][0]
    assert "organization_id" not in body["tasks"][0]


def test_reply_sla_escalation_rejects_invalid_policy_payload(auth_client):
    response = auth_client.post(
        "/api/tasks/reply-sla-escalations",
        json={"overdue_hours": 0, "limit": 51, "unexpected": True},
    )

    assert response.status_code == 422
    error_locations = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "overdue_hours") in error_locations
    assert ("body", "limit") in error_locations
    assert ("body", "unexpected") in error_locations
    assert mock_session.tasks == []


def test_reply_sla_escalation_accepts_signed_bearer_session():
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_session.emails[21] = make_email(
        email_id=21,
        message_id="<sent-sla-signed@example.com>",
        thread_id="<thread-sla-signed>",
        sender="alice@example.com",
        recipients="vendor@example.com",
        subject="Vendor reply",
        body="Please reply by Friday.",
        date=now - datetime.timedelta(days=3),
    )
    app.dependency_overrides.pop(get_auth_context, None)
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())

    try:
        with TestClient(
            app,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = client.post(
                "/api/tasks/reply-sla-escalations",
                json={"overdue_hours": 48},
            )
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["tasks"][0]["source_type"] == "reply_sla"
    assert body["tasks"][0]["source_email_id"] == "<sent-sla-signed@example.com>"
    assert "user_id" not in body["tasks"][0]
    assert "organization_id" not in body["tasks"][0]


def test_reply_sla_escalation_creates_source_linked_overdue_task(auth_client):
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_session.emails[21] = make_email(
        email_id=21,
        message_id="<sent-sla@example.com>",
        thread_id="<thread-sla>",
        sender="alice@example.com",
        recipients="vendor@example.com",
        subject="<script>alert('x')</script>",
        body="Please reply by Friday.",
        date=now - datetime.timedelta(days=3),
    )
    mock_session.emails[22] = make_email(
        email_id=22,
        message_id="<sent-recent@example.com>",
        thread_id="thread-recent",
        sender="alice@example.com",
        recipients="vendor@example.com",
        subject="Recent follow-up",
        body="Please reply when you can.",
        date=now - datetime.timedelta(hours=2),
    )
    mock_session.emails[23] = make_email(
        email_id=23,
        message_id="<sent-answered@example.com>",
        thread_id="<thread-answered>",
        sender="alice@example.com",
        recipients="vendor@example.com",
        subject="Answered follow-up",
        body="Please reply when you can.",
        date=now - datetime.timedelta(days=3),
    )
    mock_session.emails[24] = make_email(
        email_id=24,
        message_id="<reply-answered@example.com>",
        thread_id="thread-answered",
        sender="vendor@example.com",
        recipients="alice@example.com",
        subject="Re: Answered follow-up",
        body="Confirmed.",
        date=now - datetime.timedelta(days=2),
    )
    mock_session.emails[25] = make_email(
        email_id=25,
        message_id="<self-note@example.com>",
        thread_id="thread-self",
        sender="alice@example.com",
        recipients="alice@example.com",
        subject="Self note",
        body="Please reply is not external work.",
        date=now - datetime.timedelta(days=3),
    )

    response = auth_client.post(
        "/api/tasks/reply-sla-escalations",
        json={"overdue_hours": 48},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evaluated"] == 2
    assert body["created"] == 1
    assert body["policy"] == {"overdue_hours": 48}
    assert len(body["tasks"]) == 1
    task = body["tasks"][0]
    assert task["title"] == "미답변 팔로업: 제목 정리 필요"
    assert task["status"] == "blocked"
    assert task["priority"] == "urgent"
    assert task["source_type"] == "reply_sla"
    assert task["source_email_id"] == "<sent-sla@example.com>"
    assert task["related_thread_id"] == "thread-sla"
    assert "related_email_id" not in task
    assert "user_id" not in task
    assert "organization_id" not in task
    assert len(mock_session.tasks) == 1
    assert mock_session.tasks[0].related_email_id == 21
    assert "<script>" not in mock_session.tasks[0].title


def test_reply_sla_escalation_is_idempotent_for_existing_task(auth_client):
    now = datetime.datetime.now(datetime.timezone.utc)
    previous_update = now - datetime.timedelta(days=1)
    mock_session.emails[31] = make_email(
        email_id=31,
        message_id="<existing-sla@example.com>",
        thread_id="<thread-existing-sla>",
        sender="alice@example.com",
        recipients="vendor@example.com",
        subject="Existing SLA follow-up",
        body="Please reply by tomorrow.",
        date=now - datetime.timedelta(days=4),
    )
    mock_session.tasks.append(
        TicketTask(
            id=1,
            task_uid="opaque-existing-sla",
            user_id="alice",
            organization_id="org-acme",
            title="예전 SLA 작업",
            status="open",
            priority="normal",
            source_type="reply_sla",
            related_email_id=31,
            related_thread_id="old-thread",
            created_at=previous_update,
            updated_at=previous_update,
        )
    )

    response = auth_client.post(
        "/api/tasks/reply-sla-escalations",
        json={"overdue_hours": 48},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 0
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["id"] == "opaque-existing-sla"
    assert body["tasks"][0]["status"] == "blocked"
    assert body["tasks"][0]["priority"] == "urgent"
    assert body["tasks"][0]["related_thread_id"] == "thread-existing-sla"
    assert len(mock_session.tasks) == 1
    assert mock_session.tasks[0].title == "미답변 팔로업: Existing SLA follow-up"
    assert mock_session.tasks[0].updated_at > previous_update


def test_reply_sla_escalation_conflict_returns_machine_readable_detail(auth_client):
    class ConflictTaskSession(MockTaskSession):
        def __init__(self) -> None:
            super().__init__()
            self.commit_attempts = 0
            self.in_fallback = False

        def add(self, obj):
            if self.in_fallback:
                raise IntegrityError("duplicate reply_sla task", {}, None)
            super().add(obj)

        async def commit(self):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise IntegrityError("batch reply_sla conflict", {}, None)

        async def rollback(self):
            self.in_fallback = True
            self.tasks.clear()

    conflict_session = ConflictTaskSession()
    now = datetime.datetime.now(datetime.timezone.utc)
    conflict_session.emails[41] = make_email(
        email_id=41,
        message_id="<conflict-sla@example.com>",
        thread_id="<thread-conflict-sla>",
        sender="alice@example.com",
        recipients="vendor@example.com",
        subject="Conflict SLA follow-up",
        body="Please reply by tomorrow.",
        date=now - datetime.timedelta(days=4),
    )
    app.dependency_overrides[get_db] = lambda: conflict_session

    response = auth_client.post(
        "/api/tasks/reply-sla-escalations",
        json={"overdue_hours": 48},
    )

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": {
            "error_code": "reply_sla_task_conflict",
            "message": "Overdue reply follow-up task conflict",
        }
    }


def test_reply_sla_escalation_bulk_fetches_nested_conflicts(auth_client):
    class RacingTaskSession(MockTaskSession):
        def __init__(self) -> None:
            super().__init__()
            self.commit_attempts = 0
            self.in_fallback = False
            self.ticket_task_statement_texts: list[str] = []

        async def execute(self, stmt):
            descriptions = getattr(stmt, "column_descriptions", [])
            if descriptions and descriptions[0].get("entity") is TicketTask:
                self.ticket_task_statement_texts.append(str(stmt).lower())
            return await super().execute(stmt)

        def add(self, obj):
            if (
                self.in_fallback
                and isinstance(obj, TicketTask)
                and obj.source_type == "reply_sla"
            ):
                self._insert_raced_task(obj)
                raise IntegrityError("duplicate reply_sla task", {}, None)
            super().add(obj)

        def _insert_raced_task(self, obj: TicketTask) -> None:
            if any(
                task.user_id == obj.user_id
                and task.organization_id == obj.organization_id
                and task.source_type == obj.source_type
                and task.related_email_id == obj.related_email_id
                for task in self.tasks
            ):
                return
            now = datetime.datetime.now(datetime.timezone.utc)
            self.tasks.append(
                TicketTask(
                    id=len(self.tasks) + 1,
                    task_uid=f"raced-reply-sla-{obj.related_email_id}",
                    user_id=obj.user_id,
                    organization_id=obj.organization_id,
                    title="raced overdue reply follow-up",
                    status="open",
                    priority="normal",
                    source_type=obj.source_type,
                    related_email_id=obj.related_email_id,
                    related_thread_id=obj.related_thread_id,
                    created_at=now,
                    updated_at=now,
                )
            )

        async def commit(self):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise IntegrityError("batch reply_sla conflict", {}, None)

        async def rollback(self):
            self.in_fallback = True
            self.tasks.clear()

    racing_session = RacingTaskSession()
    now = datetime.datetime.now(datetime.timezone.utc)
    for email_id in (51, 52):
        racing_session.emails[email_id] = make_email(
            email_id=email_id,
            message_id=f"<raced-sla-{email_id}@example.com>",
            thread_id=f"<thread-raced-sla-{email_id}>",
            sender="alice@example.com",
            recipients="vendor@example.com",
            subject=f"Raced SLA follow-up {email_id}",
            body="Please reply by tomorrow.",
            date=now - datetime.timedelta(days=4),
        )
    app.dependency_overrides[get_db] = lambda: racing_session

    response = auth_client.post(
        "/api/tasks/reply-sla-escalations",
        json={"overdue_hours": 48},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 0
    assert {task["source_email_id"] for task in body["tasks"]} == {
        "<raced-sla-51@example.com>",
        "<raced-sla-52@example.com>",
    }
    assert all(task.status == "blocked" for task in racing_session.tasks)
    assert not any(
        "ticket_tasks.email_id =" in statement
        for statement in racing_session.ticket_task_statement_texts
    )


def test_reply_sla_escalation_fallback_batches_new_task_flushes(auth_client):
    class FlushCountingTaskSession(MockTaskSession):
        def __init__(self) -> None:
            super().__init__()
            self.commit_attempts = 0
            self.flush_attempts = 0

        async def commit(self):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise IntegrityError("batch reply_sla conflict", {}, None)

        async def rollback(self):
            self.tasks = [
                task
                for task in self.tasks
                if task.task_uid == "opaque-existing-batch-sla"
            ]

        async def flush(self):
            self.flush_attempts += 1

    flush_session = FlushCountingTaskSession()
    now = datetime.datetime.now(datetime.timezone.utc)
    for days_old, email_id in ((5, 61), (4, 62), (3, 63)):
        flush_session.emails[email_id] = make_email(
            email_id=email_id,
            message_id=f"<batch-sla-{email_id}@example.com>",
            thread_id=f"<thread-batch-sla-{email_id}>",
            sender="alice@example.com",
            recipients="vendor@example.com",
            subject=f"Batch SLA follow-up {email_id}",
            body="Please reply by tomorrow.",
            date=now - datetime.timedelta(days=days_old),
        )
    flush_session.tasks.append(
        TicketTask(
            id=1,
            task_uid="opaque-existing-batch-sla",
            user_id="alice",
            organization_id="org-acme",
            title="예전 배치 SLA 작업",
            status="open",
            priority="normal",
            source_type="reply_sla",
            related_email_id=62,
            related_thread_id="old-thread",
            created_at=now - datetime.timedelta(days=2),
            updated_at=now - datetime.timedelta(days=2),
        )
    )
    app.dependency_overrides[get_db] = lambda: flush_session

    response = auth_client.post(
        "/api/tasks/reply-sla-escalations",
        json={"overdue_hours": 48},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert [task["source_email_id"] for task in body["tasks"]] == [
        "<batch-sla-61@example.com>",
        "<batch-sla-62@example.com>",
        "<batch-sla-63@example.com>",
    ]
    assert flush_session.commit_attempts == 2
    assert flush_session.flush_attempts == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_reply_sla_escalation_real_postgres_smoke():
    from asyncpg.exceptions import InvalidAuthorizationSpecificationError
    from asyncpg.exceptions import InvalidPasswordError
    from db.models import Base
    from sqlalchemy import delete, select, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
    except (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
        OperationalError,
        OSError,
    ) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")

    Session = async_sessionmaker(engine, expire_on_commit=False)
    user_id = "reply-sla-smoke-user"
    organization_id = "reply-sla-smoke-org"
    now = datetime.datetime.now(datetime.timezone.utc)

    async def cleanup_seed_rows():
        async with Session() as session:
            await session.execute(
                delete(TicketTask).where(TicketTask.user_id == user_id)
            )
            await session.execute(delete(Email).where(Email.user_id == user_id))
            await session.execute(
                delete(TenantConfig).where(TenantConfig.user_id == user_id)
            )
            await session.commit()

    await cleanup_seed_rows()
    async with Session() as session:
        session.add(
            TenantConfig(
                user_id=user_id,
                organization_id=organization_id,
                smtp_username="reply-sla-smoke@example.com",
                imap_username=None,
            )
        )
        session.add(
            Email(
                user_id=user_id,
                organization_id=organization_id,
                workspace_id=f"workspace-{organization_id}",
                message_id="<reply-sla-smoke@example.com>",
                thread_id="<reply-sla-smoke-thread>",
                sender="reply-sla-smoke@example.com",
                recipients="vendor@example.com",
                subject="<img src=x onerror=alert(1)>",
                date=now - datetime.timedelta(days=3),
                body="Please reply by tomorrow.",
            )
        )
        await session.commit()

    async def real_db_override():
        async with Session() as session:
            yield session

    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = real_db_override
    persisted_task: TicketTask | None = None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            headers={
                "X-User-Id": user_id,
                "X-Organization-Id": organization_id,
            },
            base_url="http://test",
        ) as real_client:
            response = await real_client.post(
                "/api/tasks/reply-sla-escalations",
                json={"overdue_hours": 48},
            )
        async with Session() as session:
            task_result = await session.execute(
                select(TicketTask).where(
                    TicketTask.user_id == user_id,
                    TicketTask.organization_id == organization_id,
                    TicketTask.source_type == "reply_sla",
                )
            )
            persisted_task = task_result.scalar_one()
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
        await cleanup_seed_rows()
        await engine.dispose()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["tasks"][0]["source_email_id"] == "<reply-sla-smoke@example.com>"
    assert body["tasks"][0]["related_thread_id"] == "reply-sla-smoke-thread"
    assert body["tasks"][0]["title"] == "미답변 팔로업: 제목 정리 필요"
    assert persisted_task is not None
    assert persisted_task.status == "blocked"
    assert persisted_task.priority == "urgent"
    assert persisted_task.related_thread_id == "reply-sla-smoke-thread"


def test_list_ticket_tasks_does_not_leak_cross_tenant_source_email(auth_client):
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_session.emails[99] = make_email(
        email_id=99,
        user_id="bob",
        organization_id="org-rival",
        thread_id="thread-rival",
    )
    mock_session.tasks.append(
        TicketTask(
            id=1,
            task_uid="opaque-task-id",
            user_id="alice",
            organization_id="org-acme",
            title="교차 테넌트 소스 확인",
            status="open",
            priority="normal",
            source_type="email",
            related_email_id=99,
            related_thread_id="thread-rival",
            created_at=now,
            updated_at=now,
        )
    )

    response = auth_client.get("/api/tasks")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["id"] == "opaque-task-id"
    assert body[0]["source_email_id"] is None
    assert body[0]["related_thread_id"] is None


def test_update_ticket_task_status_uses_opaque_id_and_keeps_source(auth_client):
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_session.emails[14] = make_email()
    mock_session.tasks.append(
        TicketTask(
            id=1,
            task_uid="opaque-task-update-id",
            user_id="alice",
            organization_id="org-acme",
            title="회신 상태 추적",
            status="open",
            priority="normal",
            source_type="email",
            related_email_id=14,
            related_thread_id="thread-123",
            created_at=now,
            updated_at=now,
        )
    )

    response = auth_client.patch(
        "/api/tasks/opaque-task-update-id",
        json={"status": "in_progress", "priority": "high"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "opaque-task-update-id"
    assert body["status"] == "in_progress"
    assert body["priority"] == "high"
    assert body["source_email_id"] == "<message-14@example.com>"
    assert body["related_thread_id"] == "thread-123"
    assert "task_id" not in body
    assert "related_email_id" not in body
    assert mock_session.tasks[0].status == "in_progress"
    assert mock_session.tasks[0].priority == "high"
    assert mock_session.tasks[0].updated_at > now


def test_update_ticket_task_rejects_cross_tenant_task(auth_client):
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_session.tasks.append(
        TicketTask(
            id=1,
            task_uid="opaque-rival-task",
            user_id="bob",
            organization_id="org-rival",
            title="권한 밖 작업",
            status="open",
            priority="normal",
            source_type="email",
            related_email_id=None,
            related_thread_id=None,
            created_at=now,
            updated_at=now,
        )
    )

    response = auth_client.patch(
        "/api/tasks/opaque-rival-task", json={"status": "done"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}
    assert mock_session.tasks[0].status == "open"


def test_update_ticket_task_rejects_empty_payload(auth_client):
    response = auth_client.patch("/api/tasks/missing-fields", json={})

    assert response.status_code == 422
    assert response.json() == {"detail": "At least one ticket field is required"}


def make_email(
    *,
    email_id: int = 14,
    user_id: str = "alice",
    organization_id: str | None = "org-acme",
    thread_id: str | None = "thread-123",
    message_id: str | None = None,
    sender: str = "pm@example.com",
    recipients: str = "alice@example.com",
    subject: str | None = "Task source email",
    body: str = "Please create tracked work items.",
    date: datetime.datetime | None = None,
) -> Email:
    return Email(
        id=email_id,
        user_id=user_id,
        organization_id=organization_id,
        message_id=message_id or f"<message-{email_id}@example.com>",
        thread_id=thread_id,
        sender=sender,
        recipients=recipients,
        subject=subject,
        date=date or datetime.datetime(2026, 5, 19, tzinfo=datetime.timezone.utc),
        body=body,
    )


def test_ticket_task_database_columns_use_two_word_snake_case():
    column_names = {column.name for column in TicketTask.__table__.columns}

    assert column_names == {
        "task_id",
        "task_uid",
        "user_id",
        "organization_id",
        "task_title",
        "status_code",
        "priority_code",
        "source_type",
        "email_id",
        "thread_id",
        "created_at",
        "updated_at",
    }
    assert all("_" in column_name for column_name in column_names)


def test_ticket_task_model_declares_reply_sla_unique_index():
    indexes = {index.name: index for index in TicketTask.__table__.indexes}

    reply_sla_index = indexes["uq_ticket_tasks_reply_sla_email"]

    assert reply_sla_index.unique is True
    expression_text = " ".join(
        str(expression).lower() for expression in reply_sla_index.expressions
    )
    assert "user_id" in expression_text
    assert "coalesce" in expression_text
    assert "organization_id" in expression_text
    assert "source_type" in expression_text
    assert "email_id" in expression_text


def test_create_ticket_tasks_from_email_links_source_email_and_thread(auth_client):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": ["담당자 확인", "일정 공유"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert [type(task["id"]) for task in body["tasks"]] == [str, str]
    assert [len(task["id"]) for task in body["tasks"]] == [32, 32]
    assert [task["title"] for task in body["tasks"]] == ["담당자 확인", "일정 공유"]
    assert {task["status"] for task in body["tasks"]} == {"open"}
    assert {task["priority"] for task in body["tasks"]} == {"normal"}
    assert {task["source_type"] for task in body["tasks"]} == {"email"}
    assert {task["source_email_id"] for task in body["tasks"]} == {
        "<message-14@example.com>"
    }
    assert all("related_email_id" not in task for task in body["tasks"])
    assert {task["related_thread_id"] for task in body["tasks"]} == {"thread-123"}
    assert all("user_id" not in task for task in body["tasks"])
    assert all("organization_id" not in task for task in body["tasks"])


def test_create_ticket_tasks_sanitizes_nul_bytes_from_execution_items(auth_client):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": ["담당자\u0000 확인"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tasks"][0]["title"] == "담당자 확인"
    assert "\x00" not in mock_session.tasks[0].title


def test_create_ticket_tasks_rejects_html_execution_item_titles(auth_client):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": ["<script>alert('XSS by Strix');</script>"],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Execution items must be plain text"}
    assert mock_session.tasks == []


@pytest.mark.parametrize(
    "payload",
    [
        "&lt;img src=x onerror=alert(document.domain)&gt;",
        "<!-- hidden task markup -->",
        "<!DOCTYPE html>",
        "<?xml version='1.0'?>",
        "< /script>alert(1)</script>",
        "<svg/onload=alert(1)@x>",
        "<math/href=javascript:alert(1)@x>",
        "<script src=//attacker.example/xss.js",
        "&lt;script src=//attacker.example/xss.js",
    ],
)
def test_create_ticket_tasks_rejects_encoded_and_malformed_html_titles(
    auth_client, payload
):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": [payload],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Execution items must be plain text"}
    assert mock_session.tasks == []


def test_create_ticket_tasks_allows_plain_comparison_text(auth_client):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": ["Confirm 2 < 3 and 5 > 4"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["tasks"][0]["title"] == "Confirm 2 < 3 and 5 > 4"


def test_create_ticket_tasks_allows_plain_alphabetic_comparison_text(auth_client):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": ["Compare a < b before saving"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["tasks"][0]["title"] == "Compare a < b before saving"


def test_create_ticket_tasks_rejects_email_owned_by_another_member(auth_client):
    mock_session.emails[99] = make_email(
        email_id=99,
        user_id="bob",
        organization_id="org-acme",
        thread_id="thread-bob",
    )

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-99@example.com>",
            "thread_id": "thread-bob",
            "items": ["권한 밖 업무"],
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Source email not found"}
    assert mock_session.tasks == []


def test_create_ticket_tasks_rejects_empty_execution_items(auth_client):
    mock_session.emails[14] = make_email()

    response = auth_client.post(
        "/api/tasks/from-email",
        json={
            "source_email_id": "<message-14@example.com>",
            "thread_id": "thread-123",
            "items": [" "],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "At least one execution item is required"}
    assert mock_session.tasks == []
