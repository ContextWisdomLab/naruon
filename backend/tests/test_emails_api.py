import base64
import hashlib
import hmac
import io
import json
import logging
import os
import time
import zipfile

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr

from api import emails as emails_api
from api.auth import get_auth_context as auth_get_auth_context
from core.config import settings
from db.models import Email, LLMProvider
from main import app
import datetime
from unittest.mock import AsyncMock, patch
from services.embedding import STORAGE_EMBEDDING_DIMENSION
from services.email_service import generate_email_fingerprint

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
        "sub": "testuser",
        "role": "member",
        "org": "org-acme",
        "groups": [],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return payload


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        headers={"X-User-Id": "testuser"},
        base_url="http://test",
    ) as ac:
        yield ac


class MockTenantConfig:
    def __init__(self):
        self.smtp_server = "smtp.example.com"
        self.smtp_port = 587
        self.smtp_username = "testuser"
        self.smtp_password = None
        self.openai_api_key = None


_DEFAULT_TENANT_CONFIG = object()


class MockSession:
    def __init__(
        self,
        items,
        tenant_config=_DEFAULT_TENANT_CONFIG,
        llm_providers=None,
    ):
        self.items = items
        self.llm_providers = list(llm_providers or [])
        self.tenant_config = (
            MockTenantConfig()
            if tenant_config is _DEFAULT_TENANT_CONFIG
            else tenant_config
        )

    async def execute(self, query, params=None):
        class MockResult:
            def __init__(self, rows):
                self.rows = rows

            def scalars(self):
                return self

            def all(self):
                return self.rows

            def scalar_one_or_none(self):
                return self.rows[0] if self.rows else None

            def first(self):
                return self.rows[0] if self.rows else None

        query_text = compiled_query_text(query)
        if "llm_providers" in query_text:
            return MockResult(self.llm_providers)
        if "tenant_configs" in query_text:
            rows = [] if self.tenant_config is None else [self.tenant_config]
            return MockResult(rows)
        return MockResult(self.items)

    async def scalar(self, query):
        query_text = compiled_query_text(query)
        if "count(" in query_text and "email_records" in query_text:
            return len(self.items)
        return self.tenant_config


class LimitAwareMockSession(MockSession):
    def __init__(self, items, tenant_config=_DEFAULT_TENANT_CONFIG):
        super().__init__(items, tenant_config=tenant_config)
        self.last_limit_value = None

    async def execute(self, query, params=None):
        class MockResult:
            def __init__(self, rows):
                self.rows = rows

            def scalars(self):
                return self

            def all(self):
                return self.rows

            def scalar_one_or_none(self):
                return self.rows[0] if self.rows else None

        limit_clause = getattr(query, "_limit_clause", None)
        limit_value = getattr(limit_clause, "value", None)
        if limit_value is not None:
            self.last_limit_value = limit_value

        if "ranked_thread_heads" in str(query):
            # Emulate the SQL window query: newest head row per thread,
            # ordered by date desc, LIMIT applied to heads (not raw rows).
            heads: dict[str, object] = {}
            for item in sorted(self.items, key=lambda email: email.date, reverse=True):
                key = item.thread_id or item.message_id
                heads.setdefault(key, item)
            rows = list(heads.values())
            if limit_value:
                rows = rows[:limit_value]
            return MockResult(rows)

        rows = self.items[:limit_value] if limit_value else self.items
        return MockResult(rows)


class QueryCapturingSession(MockSession):
    def __init__(self, items, tenant_config=_DEFAULT_TENANT_CONFIG):
        super().__init__(items, tenant_config=tenant_config)
        self.queries = []

    async def execute(self, query, params=None):
        self.queries.append(query)
        return await super().execute(query, params)


class ScalarQueryCapturingSession(MockSession):
    def __init__(self, items, tenant_config=_DEFAULT_TENANT_CONFIG):
        super().__init__(items, tenant_config=tenant_config)
        self.queries = []
        self.scalar_queries = []

    async def execute(self, query, params=None):
        self.queries.append(query)
        return await super().execute(query, params)

    async def scalar(self, query):
        self.scalar_queries.append(query)
        return await super().scalar(query)


class ImportRecordingSession(MockSession):
    def __init__(
        self,
        items,
        tenant_config=_DEFAULT_TENANT_CONFIG,
        llm_providers=None,
    ):
        super().__init__(
            items,
            tenant_config=tenant_config,
            llm_providers=llm_providers,
        )
        self.added = []
        self.queries = []
        self.query_params = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, query, params=None):
        self.queries.append(query)
        self.query_params.append(params)
        return await super().execute(query, params)

    def add(self, item):
        self.added.append(item)
        self.items.append(item)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


class _PostgresDialect:
    name = "postgresql"


class _PostgresBind:
    dialect = _PostgresDialect()


class PostgresImportRecordingSession(ImportRecordingSession):
    def get_bind(self):
        return _PostgresBind()


class ScalarQueryCapturingImportSession(PostgresImportRecordingSession):
    def __init__(
        self,
        items,
        tenant_config=_DEFAULT_TENANT_CONFIG,
        llm_providers=None,
    ):
        super().__init__(items, tenant_config=tenant_config, llm_providers=llm_providers)
        self.scalar_queries = []

    async def scalar(self, query):
        self.scalar_queries.append(query)
        return await super().scalar(query)


def compiled_query_text(query) -> str:
    return str(query).lower()


def compiled_query_params(query) -> dict[str, object]:
    return dict(query.compile().params)


def assert_query_is_owner_scoped(query) -> None:
    query_text = compiled_query_text(query)
    query_params = compiled_query_params(query)

    assert "email_records.user_id = :user_id_1" in query_text
    assert "email_records.organization_id = :organization_id_1" in query_text
    assert query_params["user_id_1"] == "testuser"
    assert query_params["organization_id_1"] == "org-acme"


def advisory_query_texts(session: ImportRecordingSession) -> list[str]:
    return [
        compiled_query_text(query)
        for query in session.queries
        if "pg_advisory" in compiled_query_text(query)
    ]


def advisory_query_params(session: ImportRecordingSession) -> list[dict[str, object]]:
    return [
        params
        for query, params in zip(session.queries, session.query_params)
        if "pg_advisory" in compiled_query_text(query) and isinstance(params, dict)
    ]


def _sample_eml_bytes(
    *,
    message_id: str = "<imported@example.com>",
    subject: str = "Quarter plan",
    body: str = "Body text",
) -> bytes:
    return (
        (
            "Message-ID: {message_id}\r\n"
            "Date: Thu, 11 Jun 2026 10:00:00 +0000\r\n"
            "From: Partner <partner@example.com>\r\n"
            "To: User <user@example.com>\r\n"
            "Subject: {subject}\r\n"
            "\r\n"
            "{body}\r\n"
        )
        .format(message_id=message_id, subject=subject, body=body)
        .encode("utf-8")
    )


def _zip_with_eml_bytes(filename: str, eml_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(filename, eml_bytes)
    return buffer.getvalue()


def _mbox_with_eml_bytes(*messages: bytes) -> bytes:
    buffer = io.BytesIO()
    for index, message in enumerate(messages, start=1):
        buffer.write(
            f"From sender-{index}@example.com Thu Jun 11 10:00:00 2026\n".encode(
                "ascii"
            )
        )
        buffer.write(message.replace(b"\r\n", b"\n"))
        buffer.write(b"\n")
    return buffer.getvalue()


@pytest.fixture
def sample_email():
    return Email(
        id=1,
        user_id="testuser",
        message_id="msg123",
        thread_id="thread123",
        sender="test@example.com",
        reply_to="reply@example.com",
        recipients="user@example.com",
        subject="Test Subject",
        date=datetime.datetime.now(datetime.timezone.utc),
        body="This is a test email body.",
    )


@pytest.fixture
def db_session(sample_email):
    # Mock the database session
    return MockSession([sample_email])


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    from db.session import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_emails(client: AsyncClient, db_session):
    response = await client.get("/api/emails?limit=10")
    assert response.status_code == 200
    assert "emails" in response.json()


@pytest.mark.asyncio
async def test_get_emails_returns_ui_safe_display_fields(
    client: AsyncClient, db_session, sample_email: Email
):
    sample_email.subject = "<script>alert('x')</script>Quarter plan"
    sample_email.sender = '"<img/src=x onerror=alert(1)>" <sender@example.com>'
    sample_email.reply_to = '"<script>alert(1)</script>" <reply@example.com>'
    sample_email.body = "<p>Hello</p><script>alert('body')</script>"

    response = await client.get("/api/emails?limit=10")

    assert response.status_code == 200
    item = response.json()["emails"][0]
    assert item["subject"] == "Quarter plan"
    assert item["sender"] == '"" <sender@example.com>'
    assert item["reply_to"] == '"" <reply@example.com>'
    assert item["snippet"] == "Hello"
    assert "<" not in item["subject"]
    assert "<script" not in item["snippet"].lower()


@pytest.mark.asyncio
async def test_get_emails_returns_exact_distinct_threads_beyond_overfetch_window(
    client: AsyncClient, db_session
):
    hot_thread = [
        Email(
            id=index + 1,
            user_id="testuser",
            message_id=f"hot-{index}",
            thread_id="hot-thread",
            sender="hot@example.com",
            recipients="user@example.com",
            subject="Hot thread",
            date=datetime.datetime(
                2026, 4, 27, 12, index, tzinfo=datetime.timezone.utc
            ),
            body=f"Hot body {index}",
        )
        for index in range(6)
    ]
    second_thread = Email(
        id=99,
        user_id="testuser",
        message_id="second-thread-root",
        thread_id="second-thread",
        sender="second@example.com",
        recipients="user@example.com",
        subject="Second thread",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Second body",
    )
    db_session.items = sorted(
        [*hot_thread, second_thread], key=lambda item: item.date, reverse=True
    )

    from db.session import get_db

    app.dependency_overrides[get_db] = lambda: LimitAwareMockSession(db_session.items)

    response = await client.get("/api/emails?limit=2")

    assert response.status_code == 200
    data = response.json()["emails"]
    assert [item["thread_id"] for item in data] == ["hot-thread", "second-thread"]
    assert data[0]["reply_count"] == 6


@pytest.mark.asyncio
async def test_get_emails_excludes_backfill_rows_outside_selected_thread_heads(
    client: AsyncClient, db_session
):
    # The message-backfill query is scoped by thread lookup values on
    # PostgreSQL, but get_emails still defensively drops any returned row
    # whose canonical thread key is not among the selected heads. Emulate a
    # backend that returns a row from a thread outside the winnowed page
    # (here the older thread, which is excluded because limit=1 keeps only the
    # newest head) and assert it never inflates or leaks into the response.
    head_root = Email(
        id=1,
        user_id="testuser",
        message_id="winnow-head-root",
        thread_id="winnow-head-thread",
        sender="head@example.com",
        recipients="user@example.com",
        subject="Head thread root",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Head root body",
    )
    head_reply = Email(
        id=2,
        user_id="testuser",
        message_id="winnow-head-reply",
        thread_id="winnow-head-thread",
        sender="head@example.com",
        recipients="user@example.com",
        subject="Re: Head thread root",
        date=datetime.datetime(2026, 4, 27, 12, 0, tzinfo=datetime.timezone.utc),
        body="Head reply body",
    )
    orphan = Email(
        id=3,
        user_id="testuser",
        message_id="winnow-orphan-root",
        thread_id="winnow-orphan-thread",
        sender="orphan@example.com",
        recipients="user@example.com",
        subject="Orphan thread",
        date=datetime.datetime(2026, 4, 27, 8, 0, tzinfo=datetime.timezone.utc),
        body="Orphan body",
    )
    db_session.items = [head_reply, head_root, orphan]

    from db.session import get_db

    app.dependency_overrides[get_db] = lambda: LimitAwareMockSession(db_session.items)

    response = await client.get("/api/emails?limit=1")

    assert response.status_code == 200
    data = response.json()["emails"]
    # Only the newest thread survives the limit=1 head selection, and the
    # orphan thread returned by the backfill is discarded rather than merged.
    assert [item["thread_id"] for item in data] == ["winnow-head-thread"]
    assert data[0]["reply_count"] == 2


@pytest.mark.asyncio
async def test_get_emails_orders_interleaved_threads_by_latest_message_date(
    client: AsyncClient, db_session
):
    older_alpha = Email(
        id=1,
        user_id="testuser",
        message_id="alpha-root",
        thread_id="alpha-thread",
        sender="alpha@example.com",
        recipients="user@example.com",
        subject="Alpha root",
        date=datetime.datetime(2026, 4, 27, 9, 0, tzinfo=datetime.timezone.utc),
        body="Alpha root body",
    )
    beta = Email(
        id=2,
        user_id="testuser",
        message_id="beta-root",
        thread_id="beta-thread",
        sender="beta@example.com",
        recipients="user@example.com",
        subject="Beta root",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Beta body",
    )
    newer_alpha = Email(
        id=3,
        user_id="testuser",
        message_id="alpha-reply",
        thread_id="alpha-thread",
        sender="alpha@example.com",
        recipients="user@example.com",
        subject="Re: Alpha root",
        date=datetime.datetime(2026, 4, 27, 11, 0, tzinfo=datetime.timezone.utc),
        body="Alpha reply body",
    )
    db_session.items = [newer_alpha, beta, older_alpha]

    response = await client.get("/api/emails?limit=10")

    assert response.status_code == 200
    assert [item["thread_id"] for item in response.json()["emails"]] == [
        "alpha-thread",
        "beta-thread",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1])
async def test_get_emails_rejects_non_positive_limit(client: AsyncClient, limit: int):
    response = await client.get(f"/api/emails?limit={limit}")

    assert response.status_code == 422
    assert "limit" in response.text


@pytest.mark.asyncio
async def test_get_emails_bounds_database_candidate_window(
    client: AsyncClient, db_session
):
    from db.session import get_db

    session = LimitAwareMockSession(db_session.items)
    app.dependency_overrides[get_db] = lambda: session

    response = await client.get("/api/emails?limit=10")

    assert response.status_code == 200
    assert session.last_limit_value is not None
    assert session.last_limit_value >= 10


@pytest.mark.asyncio
async def test_get_emails_normalizes_legacy_bracketed_thread_ids(
    client: AsyncClient, db_session
):
    root = Email(
        id=1,
        user_id="testuser",
        message_id="<root@example.com>",
        thread_id="<root@example.com>",
        sender="root@example.com",
        recipients="user@example.com",
        subject="Legacy root",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Root body",
    )
    reply = Email(
        id=2,
        user_id="testuser",
        message_id="<reply@example.com>",
        thread_id="root@example.com",
        sender="reply@example.com",
        recipients="user@example.com",
        subject="Re: Legacy root",
        date=datetime.datetime(2026, 4, 27, 11, 0, tzinfo=datetime.timezone.utc),
        body="Reply body",
    )
    db_session.items = [reply, root]

    response = await client.get("/api/emails?limit=10")

    assert response.status_code == 200
    data = response.json()["emails"]
    assert len(data) == 1
    assert data[0]["thread_id"] == "root@example.com"
    assert data[0]["reply_count"] == 2


@pytest.mark.asyncio
async def test_get_emails_marks_self_sent_and_pending_reply_threads(
    client: AsyncClient, db_session
):
    class MailTenantConfig:
        smtp_username = "Me <testuser@example.com>"
        imap_username = None

    sent_waiting = Email(
        id=10,
        user_id="testuser",
        message_id="waiting-msg",
        thread_id="waiting-thread",
        sender="Test User <testuser@example.com>",
        recipients="target@example.com",
        subject="Can you confirm?",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Please reply when you can.",
    )
    self_note = Email(
        id=11,
        user_id="testuser",
        message_id="note-msg",
        thread_id="note-thread",
        sender="testuser@example.com",
        recipients="testuser@example.com",
        subject="Note to self",
        date=datetime.datetime(2026, 4, 27, 11, 0, tzinfo=datetime.timezone.utc),
        body="Summarize this as knowledge.",
    )
    db_session.tenant_config = MailTenantConfig()
    db_session.items = [self_note, sent_waiting]

    response = await client.get("/api/emails?limit=10")

    assert response.status_code == 200
    by_thread = {item["thread_id"]: item for item in response.json()["emails"]}
    assert by_thread["waiting-thread"]["requires_reply"] is True
    assert by_thread["waiting-thread"]["is_self_sent"] is False
    assert by_thread["note-thread"]["is_self_sent"] is True
    assert by_thread["note-thread"]["requires_reply"] is False


@pytest.mark.asyncio
async def test_get_emails_sent_folder_returns_user_sent_threads_only(
    client: AsyncClient, db_session
):
    class MailTenantConfig:
        smtp_username = "Me <testuser@example.com>"
        imap_username = None

    external_inbox = Email(
        id=20,
        user_id="testuser",
        message_id="external-msg",
        thread_id="external-thread",
        sender="partner@example.com",
        recipients="testuser@example.com",
        subject="Incoming only",
        date=datetime.datetime(2026, 4, 27, 9, 0, tzinfo=datetime.timezone.utc),
        body="FYI only.",
    )
    sent_waiting = Email(
        id=21,
        user_id="testuser",
        message_id="sent-waiting-msg",
        thread_id="sent-waiting-thread",
        sender="Test User <testuser@example.com>",
        recipients="partner@example.com",
        subject="Can you confirm?",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Can you confirm this plan?",
    )
    self_note = Email(
        id=22,
        user_id="testuser",
        message_id="sent-note-msg",
        thread_id="sent-note-thread",
        sender="testuser@example.com",
        recipients="testuser@example.com",
        subject="Note to self",
        date=datetime.datetime(2026, 4, 27, 11, 0, tzinfo=datetime.timezone.utc),
        body="Turn this into knowledge.",
    )
    db_session.tenant_config = MailTenantConfig()
    db_session.items = [self_note, sent_waiting, external_inbox]

    response = await client.get("/api/emails?folder=sent&limit=10")

    assert response.status_code == 200
    by_thread = {item["thread_id"]: item for item in response.json()["emails"]}
    assert set(by_thread) == {"sent-waiting-thread", "sent-note-thread"}
    assert by_thread["sent-waiting-thread"]["requires_reply"] is True
    assert by_thread["sent-note-thread"]["is_self_sent"] is True
    assert by_thread["sent-note-thread"]["requires_reply"] is False


@pytest.mark.asyncio
async def test_get_emails_rejects_unknown_folder(client: AsyncClient):
    response = await client.get("/api/emails?folder=archive")

    assert response.status_code == 422
    assert "folder" in response.text


@pytest.mark.asyncio
async def test_unique_email_thread_intent_detects_message_id_and_fingerprint_duplicates(
    client: AsyncClient, db_session
):
    duplicate_date = datetime.datetime(2026, 5, 27, 9, 30, tzinfo=datetime.timezone.utc)
    fingerprint = generate_email_fingerprint(
        {
            "sender": "partner@example.com",
            "subject": "Q2 출시 계획",
            "date": duplicate_date.isoformat(),
            "body": "Forwarded launch plan body",
        }
    )
    db_session.items = [
        Email(
            id=41,
            user_id="testuser",
            organization_id="org-acme",
            message_id="<q2-root@example.com>",
            thread_id="thread-q2-root",
            fingerprint=fingerprint,
            sender="partner@example.com",
            recipients="user@example.com",
            subject="Q2 출시 계획",
            date=duplicate_date,
            body="Forwarded launch plan body",
        )
    ]

    response = await client.post(
        "/api/emails/unique-thread-intent",
        json={
            "candidates": [
                {
                    "candidate_key": "zip-q2-root",
                    "message_id": "q2-root@example.com",
                    "sender": "partner@example.com",
                    "recipients": "user@example.com",
                    "subject": "Q2 출시 계획",
                    "date": duplicate_date.isoformat(),
                    "body": "Forwarded launch plan body",
                },
                {
                    "candidate_key": "forwarded-copy",
                    "sender": "partner@example.com",
                    "recipients": "user@example.com",
                    "subject": "Q2 출시 계획",
                    "date": duplicate_date.isoformat(),
                    "body": "Forwarded launch plan body",
                },
            ]
        },
        headers={"X-Organization-Id": "org-acme"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "intent_ready"
    assert data["candidates_checked"] == 2
    assert data["duplicates_found"] == 2
    assert data["provider_write_executed"] is False
    assert data["audit_event"] == "email.unique_thread_intent.created"
    by_key = {item["candidate_key"]: item for item in data["thread_updates"]}
    assert by_key["zip-q2-root"]["match_reason"] == "message_id"
    assert by_key["zip-q2-root"]["canonical_thread_id"] == "thread-q2-root"
    assert by_key["forwarded-copy"]["match_reason"] == "fingerprint"
    assert by_key["forwarded-copy"]["canonical_thread_id"] == "thread-q2-root"


@pytest.mark.asyncio
async def test_unique_email_thread_intent_rejects_empty_candidates(
    client: AsyncClient,
):
    response = await client.post(
        "/api/emails/unique-thread-intent", json={"candidates": []}
    )

    assert response.status_code == 422
    assert "candidates" in response.text


@pytest.mark.asyncio
async def test_unique_email_thread_intent_applies_auth_dependency(
    client: AsyncClient,
):
    from api.auth import AuthContext
    from api.emails import get_auth_context as emails_get_auth_context

    calls = []

    async def auth_override():
        calls.append("hit")
        return AuthContext(
            user_id="authorized-user",
            role="member",
            organization_id="authorized-org",
            group_ids=(),
            workspace_id="workspace-authorized-org",
        )

    app.dependency_overrides[emails_get_auth_context] = auth_override

    response = await client.post(
        "/api/emails/unique-thread-intent",
        json={
            "candidates": [
                {
                    "candidate_key": "new-import",
                    "message_id": "new@example.com",
                    "subject": "New import",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert calls == ["hit"]


def test_unique_email_thread_intent_accepts_signed_bearer_session(db_session):
    duplicate_date = datetime.datetime(2026, 5, 27, 9, 30, tzinfo=datetime.timezone.utc)
    db_session.items = [
        Email(
            id=51,
            user_id="testuser",
            organization_id="org-acme",
            message_id="<signed-root@example.com>",
            thread_id="signed-thread",
            sender="partner@example.com",
            recipients="user@example.com",
            subject="Signed import",
            date=duplicate_date,
            body="Signed duplicate body",
        )
    ]
    token = _signed_session_token(_valid_session_payload())
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    previous_auth_override = app.dependency_overrides.pop(auth_get_auth_context, None)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    try:
        response = TestClient(app).post(
            "/api/emails/unique-thread-intent",
            json={
                "candidates": [
                    {
                        "candidate_key": "signed-import",
                        "message_id": "signed-root@example.com",
                        "subject": "Signed import",
                    }
                ]
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret
        if previous_auth_override is not None:
            app.dependency_overrides[auth_get_auth_context] = previous_auth_override

    assert response.status_code == 200
    data = response.json()
    assert data["thread_updates"][0]["canonical_thread_id"] == "signed-thread"


@pytest.mark.asyncio
async def test_import_email_files_persists_signed_scoped_eml_upload(
    client: AsyncClient,
):
    from db.session import get_db

    session = ImportRecordingSession([])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        with patch(
            "services.email_import_service.generate_embeddings",
            new_callable=AsyncMock,
        ) as mock_generate_embeddings:
            response = await client.post(
                "/api/emails/import-files",
                files=[
                    (
                        "files",
                        (
                            "customer-source.eml",
                            _sample_eml_bytes(
                                message_id="<imported@example.com>",
                                subject="<script>bad()</script>Quarter plan",
                                body="<p>Body text</p>",
                            ),
                            "message/rfc822",
                        ),
                    )
                ],
                headers={"X-Organization-Id": "org-acme"},
            )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["imported_count"] == 1
    assert data["skipped_count"] == 0
    assert data["failed_count"] == 0
    assert data["provider_write_executed"] is False
    assert data["provenance"] == "server-authoritative"
    assert data["items"] == [
        {
            "filename": "customer-source.eml",
            "status": "imported",
            "reason_code": None,
            "attachment_count": 0,
        }
    ]
    assert "imported@example.com" not in json.dumps(data)

    assert session.commit_count == 1
    assert session.rollback_count == 0
    mock_generate_embeddings.assert_not_awaited()
    assert len(session.added) == 1
    added_email = session.added[0]
    assert added_email.user_id == "testuser"
    assert added_email.organization_id == "org-acme"
    assert added_email.message_id == "imported@example.com"
    assert added_email.subject == "Quarter plan"
    assert added_email.body == "Body text"
    assert added_email.fingerprint
    assert len(added_email.embedding) == STORAGE_EMBEDDING_DIMENSION


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "upload_filename",
    [
        "%00message.eml",
        "%0amessage.eml",
        "secret.eml%00.zip",
        "payload.exe",
    ],
)
async def test_import_email_files_rejects_invalid_canonical_filename(
    client: AsyncClient,
    upload_filename: str,
):
    response = await client.post(
        "/api/emails/import-files",
        files=[
            ("files", (upload_filename, b"not accepted", "application/octet-stream"))
        ],
        headers={"X-Organization-Id": "org-acme"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_file_type"}


@pytest.mark.asyncio
async def test_import_email_files_skips_duplicate_message_id(client: AsyncClient):
    from db.session import get_db

    existing_email = Email(
        id=80,
        user_id="testuser",
        organization_id="org-acme",
        message_id="<duplicate@example.com>",
        thread_id="duplicate-thread",
        sender="partner@example.com",
        recipients="user@example.com",
        subject="Duplicate",
        date=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        body="Existing body",
        embedding=[0.0] * 1536,
    )
    session = ImportRecordingSession([existing_email])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "duplicate.eml",
                        _sample_eml_bytes(
                            message_id="<duplicate@example.com>",
                            subject="Duplicate",
                            body="Existing body",
                        ),
                        "message/rfc822",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    data = response.json()
    assert data["imported_count"] == 0
    assert data["skipped_count"] == 1
    assert data["failed_count"] == 0
    assert data["items"][0]["status"] == "skipped_duplicate"
    assert data["items"][0]["reason_code"] == "duplicate_email"
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_import_email_files_extracts_eml_from_zip(client: AsyncClient):
    from db.session import get_db

    session = ImportRecordingSession([])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "email-archive.zip",
                        _zip_with_eml_bytes(
                            "nested/source.eml",
                            _sample_eml_bytes(message_id="<zip-source@example.com>"),
                        ),
                        "application/zip",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    data = response.json()
    assert data["imported_count"] == 1
    assert data["items"][0]["filename"] == "email-archive.zip:source.eml"
    assert session.added[0].message_id == "zip-source@example.com"


@pytest.mark.asyncio
async def test_import_email_files_extracts_eml_from_mbox(client: AsyncClient):
    from db.session import get_db

    session = ImportRecordingSession([])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "mailbox-export.mbox",
                        _mbox_with_eml_bytes(
                            _sample_eml_bytes(
                                message_id="<mbox-source@example.com>",
                                subject="MBOX source",
                            )
                        ),
                        "application/mbox",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    data = response.json()
    assert data["imported_count"] == 1
    assert data["failed_count"] == 0
    assert data["items"][0]["filename"] == "mailbox-export.mbox:message_000001.eml"
    assert session.added[0].message_id == "mbox-source@example.com"
    assert session.added[0].subject == "MBOX source"


@pytest.mark.asyncio
async def test_import_email_files_uses_active_provider_embedding_model(
    client: AsyncClient,
):
    from db.session import get_db

    provider = LLMProvider(
        id=31,
        organization_id="org-acme",
        name="Local Gemma4",
        provider_type="ollama",
        base_url="http://ollama:11434/v1",
        model_identifier="gemma4:e2b-it-qat",
        embedding_model="embeddinggemma",
        is_active=True,
    )
    session = ImportRecordingSession([], llm_providers=[provider])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        with patch(
            "services.email_import_service.generate_embeddings",
            new_callable=AsyncMock,
        ) as mock_generate_embeddings:
            mock_generate_embeddings.return_value = [[0.25] * 768]
            response = await client.post(
                "/api/emails/import-files",
                files=[
                    (
                        "files",
                        (
                            "provider-source.eml",
                            _sample_eml_bytes(
                                message_id="<provider-source@example.com>",
                                body="Provider embedding body",
                            ),
                            "message/rfc822",
                        ),
                    )
                ],
                headers={"X-Organization-Id": "org-acme"},
            )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    mock_generate_embeddings.assert_awaited_once_with(
        ["Provider embedding body"],
        "local-provider",
        base_url="http://ollama:11434/v1",
        model="embeddinggemma",
    )
    added_email = session.added[0]
    assert len(added_email.embedding) == STORAGE_EMBEDDING_DIMENSION
    assert added_email.embedding[:768] == [0.25] * 768
    assert added_email.embedding[768:] == [0.0] * 768


def test_import_email_files_accepts_signed_bearer_session(db_session):
    from db.session import get_db

    session = ImportRecordingSession([])
    token = _signed_session_token(_valid_session_payload())
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    previous_auth_override = app.dependency_overrides.pop(auth_get_auth_context, None)
    previous_db_override = app.dependency_overrides.get(get_db)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = TestClient(app).post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "signed-source.eml",
                        _sample_eml_bytes(message_id="<signed-import@example.com>"),
                        "message/rfc822",
                    ),
                )
            ],
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret
        if previous_auth_override is not None:
            app.dependency_overrides[auth_get_auth_context] = previous_auth_override
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    data = response.json()
    assert data["imported_count"] == 1
    assert session.added[0].user_id == "testuser"
    assert session.added[0].organization_id == "org-acme"


@pytest.mark.asyncio
async def test_import_email_files_duplicate_query_is_owner_scoped(
    client: AsyncClient,
):
    from db.session import get_db

    session = ImportRecordingSession([])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "scoped-source.eml",
                        _sample_eml_bytes(message_id="<scoped-import@example.com>"),
                        "message/rfc822",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    assert session.queries
    email_queries = [
        query
        for query in session.queries
        if "from email_records" in compiled_query_text(query)
    ]
    assert email_queries
    assert_query_is_owner_scoped(email_queries[0])


@pytest.mark.asyncio
async def test_import_email_files_serializes_quota_with_postgres_owner_lock(
    client: AsyncClient,
):
    from db.session import get_db

    session = PostgresImportRecordingSession([])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "locked-source.eml",
                        _sample_eml_bytes(message_id="<locked@example.com>"),
                        "message/rfc822",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 200
    advisory_queries = advisory_query_texts(session)
    assert "pg_advisory_lock" in advisory_queries[0]
    assert "pg_advisory_unlock" in advisory_queries[-1]
    assert "hashtext(:namespace_key)" in advisory_queries[0]
    assert ":owner_key" in advisory_queries[0]
    assert advisory_query_params(session) == [
        {
            "namespace_key": "naruon-email-import-quota",
            "owner_key": "testuser\x00org-acme",
        },
        {
            "namespace_key": "naruon-email-import-quota",
            "owner_key": "testuser\x00org-acme",
        },
    ]


@pytest.mark.asyncio
async def test_import_email_files_rejects_when_owner_quota_is_exhausted(
    client: AsyncClient, monkeypatch
):
    from db.session import get_db

    monkeypatch.setattr("services.email_import_service.MAX_IMPORT_EMAILS_PER_OWNER", 1)
    existing_email = Email(
        id=90,
        user_id="testuser",
        organization_id="org-acme",
        message_id="<existing@example.com>",
        thread_id="existing-thread",
        sender="partner@example.com",
        recipients="user@example.com",
        subject="Existing",
        date=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        body="Existing body",
        embedding=[0.0] * 1536,
    )
    session = PostgresImportRecordingSession([existing_email])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "quota-source.eml",
                        _sample_eml_bytes(message_id="<quota@example.com>"),
                        "message/rfc822",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 429
    assert response.json()["detail"] == "email_import_quota_exceeded"
    assert session.added == []
    assert session.commit_count == 0
    advisory_queries = advisory_query_texts(session)
    assert "pg_advisory_lock" in advisory_queries[0]
    assert "pg_advisory_unlock" in advisory_queries[-1]
    assert advisory_query_params(session) == [
        {
            "namespace_key": "naruon-email-import-quota",
            "owner_key": "testuser\x00org-acme",
        },
        {
            "namespace_key": "naruon-email-import-quota",
            "owner_key": "testuser\x00org-acme",
        },
    ]


@pytest.mark.asyncio
async def test_import_email_files_rejects_oversized_archive_before_partial_commit(
    client: AsyncClient, monkeypatch
):
    from db.session import get_db

    monkeypatch.setattr("services.email_import_service.MAX_IMPORT_EMAILS_PER_OWNER", 1)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "first.eml",
            _sample_eml_bytes(message_id="<quota-first@example.com>"),
        )
        bundle.writestr(
            "second.eml",
            _sample_eml_bytes(message_id="<quota-second@example.com>"),
        )
    session = ImportRecordingSession([])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "quota-archive.zip",
                        archive.getvalue(),
                        "application/zip",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == 429
    assert response.json()["detail"] == "email_import_quota_exceeded"
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_owner_import_quota_count_is_not_scoped_to_a_single_workspace(
    client: AsyncClient, monkeypatch
):
    # MAX_IMPORT_EMAILS_PER_OWNER and the advisory quota lock are both scoped
    # to (user_id, organization_id) only -- an owner-wide allowance, not a
    # per-workspace one. If the count query underneath it additionally filters
    # by workspace_id, an owner importing through N distinct workspaces gets
    # N times the intended allowance instead of one shared 1000-email cap.
    from db.session import get_db

    existing_email = Email(
        id=91,
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-other",
        message_id="<existing-other-workspace@example.com>",
        thread_id="existing-thread-other",
        sender="partner@example.com",
        recipients="user@example.com",
        subject="Existing in another workspace",
        date=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        body="Existing body",
        embedding=[0.0] * 1536,
    )
    session = ScalarQueryCapturingImportSession([existing_email])
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        await client.post(
            "/api/emails/import-files",
            files=[
                (
                    "files",
                    (
                        "quota-cross-workspace.eml",
                        _sample_eml_bytes(message_id="<quota-cross-workspace@example.com>"),
                        "message/rfc822",
                    ),
                )
            ],
            headers={"X-Organization-Id": "org-acme"},
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    quota_queries = [
        query
        for query in session.scalar_queries
        if "count(" in compiled_query_text(query) and "email_records" in compiled_query_text(query)
    ]
    assert quota_queries
    assert_query_is_owner_scoped(quota_queries[-1])
    assert "workspace_id" not in compiled_query_text(quota_queries[-1])


@pytest.mark.asyncio
async def test_unique_email_thread_intent_query_is_scoped_to_current_user(
    client: AsyncClient, sample_email: Email
):
    from db.session import get_db

    session = QueryCapturingSession([sample_email])
    app.dependency_overrides[get_db] = lambda: session

    response = await client.post(
        "/api/emails/unique-thread-intent",
        json={
            "candidates": [
                {
                    "candidate_key": "scoped-import",
                    "message_id": "msg123",
                    "subject": "Scoped import",
                }
            ]
        },
        headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
    )

    assert response.status_code == 200
    assert_query_is_owner_scoped(session.queries[-1])


async def _setup_postgres_smoke_session():
    from core.config import settings
    from asyncpg.exceptions import InvalidAuthorizationSpecificationError
    from asyncpg.exceptions import InvalidPasswordError
    from db.models import Base
    from sqlalchemy import text
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
        import pytest

        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")

    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session


async def _seed_reply_tracking_smoke_data(Session, user_id, organization_id, now):
    from db.models import Email, TenantConfig
    from sqlalchemy import delete

    async def cleanup_seed_rows():
        async with Session() as session:
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
                smtp_username="Smoke User <reply-smoke@example.com>",
                imap_username=None,
            )
        )
        session.add_all(
            [
                Email(
                    user_id=user_id,
                    organization_id=organization_id,
                    workspace_id=f"workspace-{organization_id}",
                    message_id="waiting-smoke-msg",
                    thread_id="<waiting-smoke-thread>",
                    sender="reply-smoke@example.com",
                    recipients="target@example.com",
                    subject="Can you confirm?",
                    date=now - datetime.timedelta(days=3),
                    body="Please reply when you can.",
                ),
                Email(
                    user_id=user_id,
                    organization_id=organization_id,
                    workspace_id=f"workspace-{organization_id}",
                    message_id="note-smoke-msg",
                    thread_id="note-smoke-thread",
                    sender="reply-smoke@example.com",
                    recipients="reply-smoke@example.com",
                    subject="Note to self",
                    date=now - datetime.timedelta(days=2),
                    body="Organize this as knowledge.",
                ),
                Email(
                    user_id=user_id,
                    organization_id=organization_id,
                    workspace_id=f"workspace-{organization_id}",
                    message_id="answered-smoke-msg",
                    thread_id="<answered-smoke-thread>",
                    sender="reply-smoke@example.com",
                    recipients="target@example.com",
                    subject="Answered",
                    date=now - datetime.timedelta(days=1, hours=1),
                    body="Please reply when you can.",
                ),
                Email(
                    user_id=user_id,
                    organization_id=organization_id,
                    workspace_id=f"workspace-{organization_id}",
                    message_id="answer-smoke-msg",
                    thread_id="answered-smoke-thread",
                    sender="target@example.com",
                    recipients="reply-smoke@example.com",
                    subject="Re: Answered",
                    date=now - datetime.timedelta(days=1),
                    body="Confirmed.",
                ),
            ]
        )
        await session.commit()

    return cleanup_seed_rows


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_get_emails_reply_tracking_real_postgres_smoke():
    from db.session import get_db

    engine, Session = await _setup_postgres_smoke_session()

    user_id = "reply-smoke-user"
    organization_id = "reply-smoke-org"
    now = datetime.datetime.now(datetime.timezone.utc)

    cleanup_seed_rows = await _seed_reply_tracking_smoke_data(
        Session, user_id, organization_id, now
    )

    async def real_db_override():
        async with Session() as session:
            yield session

    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = real_db_override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            headers={
                "X-User-Id": user_id,
                "X-Organization-Id": organization_id,
            },
            base_url="http://test",
        ) as real_client:
            inbox_response = await real_client.get("/api/emails?limit=10")
            pending_response = await real_client.get("/api/emails/pending-replies")
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
        await cleanup_seed_rows()
        await engine.dispose()

    assert inbox_response.status_code == 200
    by_thread = {item["thread_id"]: item for item in inbox_response.json()["emails"]}
    assert by_thread["waiting-smoke-thread"]["requires_reply"] is True
    assert by_thread["note-smoke-thread"]["is_self_sent"] is True
    assert by_thread["answered-smoke-thread"]["requires_reply"] is False

    assert pending_response.status_code == 200
    pending_threads = {item["thread_id"] for item in pending_response.json()["emails"]}
    assert pending_threads == {"waiting-smoke-thread"}


@pytest.mark.asyncio
async def test_get_email_by_id(client: AsyncClient, db_session, sample_email: Email):
    response = await client.get(f"/api/emails/{sample_email.id}")
    assert response.status_code == 200
    assert response.json()["id"] == sample_email.id
    assert response.json()["reply_to"] == "reply@example.com"


@pytest.mark.asyncio
async def test_get_email_by_id_returns_ui_safe_display_fields(
    client: AsyncClient, db_session, sample_email: Email
):
    sample_email.subject = "<script>alert('x')</script>Quarter plan"
    sample_email.sender = '"<img/src=x onerror=alert(1)>" <sender@example.com>'
    sample_email.recipients = '"<script>alert(1)</script>" <user@example.com>'
    sample_email.body = "<p>Hello</p><script>alert('body')</script>"

    response = await client.get(f"/api/emails/{sample_email.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["subject"] == "Quarter plan"
    assert data["sender"] == '"" <sender@example.com>'
    assert data["recipients"] == '"" <user@example.com>'
    assert data["body"] == "Hello"
    assert "<script" not in data["body"].lower()


@pytest.mark.asyncio
async def test_get_email_thread(client: AsyncClient, db_session, sample_email: Email):
    response = await client.get(f"/api/emails/thread/{sample_email.thread_id}")
    assert response.status_code == 200
    data = response.json()
    assert "thread" in data
    assert len(data["thread"]) == 1
    assert data["thread"][0]["id"] == sample_email.id


@pytest.mark.asyncio
async def test_get_email_thread_returns_ui_safe_display_fields(
    client: AsyncClient, db_session, sample_email: Email
):
    sample_email.subject = "<img/src=x onerror=alert(1)>Thread"
    sample_email.body = "<svg/onload=alert(1)>Thread body"

    response = await client.get(f"/api/emails/thread/{sample_email.thread_id}")

    assert response.status_code == 200
    item = response.json()["thread"][0]
    assert item["subject"] == "Thread"
    assert item["body"] == "Thread body"
    assert "<" not in item["subject"]
    assert "<" not in item["body"]


@pytest.mark.asyncio
async def test_get_email_thread_returns_chronological_order(
    client: AsyncClient, db_session
):
    newer = Email(
        id=2,
        user_id="testuser",
        message_id="newer-msg",
        thread_id="thread123",
        sender="newer@example.com",
        recipients="user@example.com",
        subject="Re: Test Subject",
        date=datetime.datetime(2026, 4, 27, 11, 0, tzinfo=datetime.timezone.utc),
        body="Newer body",
    )
    older = Email(
        id=1,
        user_id="testuser",
        message_id="older-msg",
        thread_id="thread123",
        sender="older@example.com",
        recipients="user@example.com",
        subject="Test Subject",
        date=datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc),
        body="Older body",
    )
    db_session.items = sorted([newer, older], key=lambda item: item.date)

    response = await client.get("/api/emails/thread/thread123")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["thread"]] == [1, 2]


@pytest.mark.asyncio
async def test_get_email_thread_accepts_url_encoded_reserved_characters(
    client: AsyncClient, db_session, sample_email: Email
):
    sample_email.thread_id = "root/part@example.com"
    sample_email.message_id = "<root/part@example.com>"

    response = await client.get("/api/emails/thread/root%2Fpart%40example.com")

    assert response.status_code == 200
    assert response.json()["thread"][0]["thread_id"] == "root/part@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/emails?limit=10", "/api/emails/1", "/api/emails/thread/thread123"],
)
async def test_get_email_routes_apply_auth_dependency(client: AsyncClient, path: str):
    from api.auth import AuthContext
    from api.emails import get_auth_context as emails_get_auth_context

    calls = []

    async def auth_override():
        calls.append("hit")
        return AuthContext(
            user_id="authorized-user",
            role="member",
            organization_id="authorized-org",
            group_ids=(),
            workspace_id="workspace-authorized-org",
        )

    app.dependency_overrides[emails_get_auth_context] = auth_override

    response = await client.get(path)

    assert response.status_code == 200
    assert calls == ["hit"]


@pytest.mark.asyncio
async def test_get_emails_query_is_scoped_to_current_user(
    client: AsyncClient, sample_email: Email
):
    from db.session import get_db

    session = QueryCapturingSession([sample_email])
    app.dependency_overrides[get_db] = lambda: session

    response = await client.get(
        "/api/emails?limit=10",
        headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
    )

    assert response.status_code == 200
    assert_query_is_owner_scoped(session.queries[-1])


@pytest.mark.asyncio
async def test_get_email_by_id_query_is_scoped_to_current_user(
    client: AsyncClient, sample_email: Email
):
    from db.session import get_db

    session = QueryCapturingSession([sample_email])
    app.dependency_overrides[get_db] = lambda: session

    response = await client.get(
        f"/api/emails/{sample_email.id}",
        headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
    )

    assert response.status_code == 200
    assert_query_is_owner_scoped(session.queries[-1])


@pytest.mark.asyncio
async def test_get_email_thread_query_is_scoped_to_current_user(
    client: AsyncClient, sample_email: Email
):
    from db.session import get_db

    session = QueryCapturingSession([sample_email])
    app.dependency_overrides[get_db] = lambda: session

    response = await client.get(
        f"/api/emails/thread/{sample_email.thread_id}",
        headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
    )

    assert response.status_code == 200
    assert_query_is_owner_scoped(session.queries[-1])


@patch("api.emails.send_email", return_value={"status": "simulated", "simulated": True})
def test_send_email_endpoint(mock_send_email, monkeypatch):
    from main import app
    from fastapi.testclient import TestClient

    validate_calls = []

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        validate_calls.append(resolve_host)
        return smtp_server, smtp_port

    monkeypatch.setattr(
        "api.emails.validate_smtp_destination", fake_validate_smtp_destination
    )

    client = TestClient(app, headers={"X-User-Id": "testuser"})

    response = client.post(
        "/api/emails/send",
        json={
            "to": "test@example.com",
            "subject": "Re: Test",
            "body": "This is a reply.",
            "in_reply_to": "<parent@example.com>",
            "references": "<root@example.com> <parent@example.com>",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "simulated", "simulated": True}
    assert validate_calls == [True]
    from services.email_client import EmailMessageParams, SmtpConfig

    expected_params = EmailMessageParams(
        to_address="test@example.com",
        subject="Re: Test",
        body="This is a reply.",
        in_reply_to="<parent@example.com>",
        references="<root@example.com> <parent@example.com>",
    )
    expected_config = SmtpConfig(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="testuser",
        smtp_password=None,
    )
    mock_send_email.assert_called_once_with(
        message_params=expected_params,
        smtp_config=expected_config,
    )


@pytest.mark.parametrize(
    ("header_field", "header_value"),
    [
        ("subject", "Quarter plan\rBcc: attacker@example.com"),
        ("subject", "Quarter plan\nBcc: attacker@example.com"),
        ("in_reply_to", "<parent@example.com>\rBcc: attacker@example.com"),
        ("in_reply_to", "<parent@example.com>\nBcc: attacker@example.com"),
        ("references", "<root@example.com>\rBcc: attacker@example.com"),
        ("references", "<root@example.com>\nBcc: attacker@example.com"),
        ("to", "victim@example.com\rBcc: attacker@example.com"),
        ("to", "victim@example.com\nBcc: attacker@example.com"),
    ],
)
@patch("api.emails.send_email", return_value={"status": "simulated", "simulated": True})
def test_send_email_endpoint_rejects_header_injection(
    mock_send_email, header_field, header_value
):
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app, headers={"X-User-Id": "testuser"})
    payload = {
        "to": "test@example.com",
        "subject": "Quarter plan",
        "body": "This is a reply.",
    }
    payload[header_field] = header_value

    response = client.post("/api/emails/send", json=payload)

    assert response.status_code == 422
    mock_send_email.assert_not_called()


@patch("api.emails.send_email", return_value={"status": "sent", "simulated": False})
def test_send_email_endpoint_rate_limits_per_user(mock_send_email, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        return smtp_server, smtp_port

    monkeypatch.setattr(
        "api.emails.validate_smtp_destination", fake_validate_smtp_destination
    )
    monkeypatch.setattr(emails_api, "_SEND_EMAIL_RATE_LIMIT_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(emails_api.time, "monotonic", lambda: 100.0)
    emails_api._email_send_attempts_by_scope.clear()

    try:
        client = TestClient(app, headers={"X-User-Id": "testuser"})
        payload = {
            "to": "test@example.com",
            "subject": "Re: Test",
            "body": "This is a reply.",
        }

        assert client.post("/api/emails/send", json=payload).status_code == 200
        response = client.post("/api/emails/send", json=payload)
    finally:
        emails_api._email_send_attempts_by_scope.clear()

    assert response.status_code == 429
    assert response.json() == {"detail": "Email send rate limit exceeded"}
    mock_send_email.assert_called_once()


@patch("api.emails.send_email", return_value={"status": "simulated", "simulated": True})
def test_send_email_endpoint_ignores_user_id_query_and_uses_authenticated_user_config(
    mock_send_email, monkeypatch, sample_email
):
    from main import app
    from fastapi.testclient import TestClient
    from db.session import get_db

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        return smtp_server, smtp_port

    monkeypatch.setattr(
        "api.emails.validate_smtp_destination", fake_validate_smtp_destination
    )
    session = ScalarQueryCapturingSession([sample_email])

    async def tenant_db():
        yield session

    app.dependency_overrides[get_db] = tenant_db
    try:
        client = TestClient(app, headers={"X-User-Id": "testuser"})
        response = client.post(
            "/api/emails/send?user_id=victim-user",
            json={
                "to": "test@example.com",
                "subject": "Re: Test",
                "body": "This is a reply.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    tenant_query = next(
        query
        for query in session.queries
        if "tenant_configs" in compiled_query_text(query)
    )
    assert compiled_query_params(tenant_query)["user_id_1"] == "testuser"
    mock_send_email.assert_called_once()


def test_send_email_endpoint_preserves_configuration_error(sample_email):
    from main import app
    from fastapi.testclient import TestClient
    from db.session import get_db

    async def missing_smtp_db():
        yield MockSession([sample_email], tenant_config=None)

    app.dependency_overrides[get_db] = missing_smtp_db
    try:
        client = TestClient(app, headers={"X-User-Id": "testuser"})
        response = client.post(
            "/api/emails/send",
            json={
                "to": "test@example.com",
                "subject": "Re: Test",
                "body": "This is a reply.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "SMTP is not configured"}


@patch("api.emails.send_email", return_value={"status": "sent", "simulated": False})
def test_send_email_endpoint_rejects_unsafe_persisted_smtp_host(
    mock_send_email, caplog
):
    from main import app
    from fastapi.testclient import TestClient
    from db.session import get_db

    class UnsafeTenantConfig(MockTenantConfig):
        def __init__(self):
            super().__init__()
            self.smtp_server = "127.0.0.1"
            self.smtp_port = 587

    async def unsafe_smtp_db():
        yield MockSession([], tenant_config=UnsafeTenantConfig())

    caplog.set_level(logging.WARNING, logger="api.emails")
    app.dependency_overrides[get_db] = unsafe_smtp_db
    try:
        client = TestClient(app, headers={"X-User-Id": "testuser"})
        response = client.post(
            "/api/emails/send",
            json={
                "to": "test@example.com",
                "subject": "Test",
                "body": "Body",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Invalid email configuration" in response.json()["detail"]
    assert "Email send rejected invalid SMTP configuration" in caplog.text
    assert "127.0.0.1" not in caplog.text
    mock_send_email.assert_not_called()


@patch("api.emails.send_email", return_value={"status": "failed", "simulated": False})
def test_send_email_endpoint_rejects_failed_send_status(mock_send_email, monkeypatch):
    from main import app
    from fastapi.testclient import TestClient

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        assert resolve_host is True
        return smtp_server, smtp_port

    monkeypatch.setattr(
        "api.emails.validate_smtp_destination", fake_validate_smtp_destination
    )

    client = TestClient(app, headers={"X-User-Id": "testuser"})

    response = client.post(
        "/api/emails/send",
        json={
            "to": "test@example.com",
            "subject": "Re: Test",
            "body": "This is a reply.",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to send email"}
    mock_send_email.assert_called_once()


@pytest.mark.asyncio
async def test_get_pending_replies(client: AsyncClient, db_session):
    from main import app
    from db.session import get_db

    # Create MockTenantConfig with smtp_username set to match one email
    class SentTenantConfig:
        smtp_username = "testuser@example.com"
        imap_username = None

    db_session.tenant_config = SentTenantConfig()

    sent_email = Email(
        id=3,
        user_id="testuser",
        message_id="msg3",
        thread_id="thread3",
        sender='"<img/src=x onerror=alert(1)>" <testuser@example.com>',
        recipients="target@example.com",
        subject="<script>alert('x')</script>Did you get this?",
        date=datetime.datetime(2026, 4, 28, 10, 0, tzinfo=datetime.timezone.utc),
        body="<p>Please reply when you can.</p><script>alert('body')</script>",
    )
    answered_sent_email = Email(
        id=4,
        user_id="testuser",
        message_id="msg4",
        thread_id="thread4",
        sender="testuser@example.com",
        recipients="target@example.com",
        subject="Answered thread",
        date=datetime.datetime(2026, 4, 28, 9, 0, tzinfo=datetime.timezone.utc),
        body="Please reply when you can.",
    )
    external_reply = Email(
        id=5,
        user_id="testuser",
        message_id="msg5",
        thread_id="thread4",
        sender="target@example.com",
        recipients="testuser@example.com",
        subject="Re: Answered thread",
        date=datetime.datetime(2026, 4, 28, 11, 0, tzinfo=datetime.timezone.utc),
        body="Confirmed.",
    )

    db_session.items = [sent_email, answered_sent_email, external_reply]

    app.dependency_overrides[get_db] = lambda: db_session

    response = await client.get("/api/emails/pending-replies")
    assert response.status_code == 200
    data = response.json()
    assert len(data["emails"]) == 1
    assert data["emails"][0]["sender"] == '"" <testuser@example.com>'
    assert data["emails"][0]["subject"] == "Did you get this?"
    assert data["emails"][0]["snippet"] == "Please reply when you can."
    assert data["emails"][0]["thread_id"] == "thread3"
    assert data["emails"][0]["requires_reply"] is True


def test_email_owner_filters():
    from api.auth import AuthContext

    # Test with organization_id
    ctx1 = AuthContext(
        user_id="user-123",
        role="member",
        organization_id="org-456",
        group_ids=(),
        workspace_id="ws-789",
    )
    filters1 = Email.owner_filters(
        ctx1.user_id, ctx1.organization_id, ctx1.workspace_id
    )

    assert len(filters1) == 3
    assert (
        str(filters1[0].compile(compile_kwargs={"literal_binds": True}))
        == "email_records.user_id = 'user-123'"
    )
    assert (
        str(filters1[1].compile(compile_kwargs={"literal_binds": True}))
        == "email_records.organization_id = 'org-456'"
    )
    assert (
        str(filters1[2].compile(compile_kwargs={"literal_binds": True}))
        == "email_records.workspace_id = 'ws-789'"
    )

    # Test with None organization_id
    ctx2 = AuthContext(
        user_id="user-123",
        role="member",
        organization_id=None,
        group_ids=(),
        workspace_id="ws-789",
    )
    filters2 = Email.owner_filters(
        ctx2.user_id, ctx2.organization_id, ctx2.workspace_id
    )

    assert len(filters2) == 3
    assert (
        str(filters2[0].compile(compile_kwargs={"literal_binds": True}))
        == "email_records.user_id = 'user-123'"
    )
    assert (
        str(filters2[1].compile(compile_kwargs={"literal_binds": True}))
        == "email_records.organization_id IS NULL"
    )


def test_find_matches_for_candidates_perf_optim_handles_missing_lookups():
    """
    Test to guarantee 100% coverage on the bolt performance optimization in
    _find_matches_for_candidates where candidate_lookups might theoretically miss keys.
    """
    from api.emails import _find_matches_for_candidates
    from services.email_dedupe_service import EmailDedupeCandidate
    import datetime

    candidate = EmailDedupeCandidate(
        candidate_key="missing_key_candidate",
        message_id="<missing@example.com>",
        date=datetime.datetime.now(),
        sender="test@test.com",
        recipients="test2@test.com",
        subject="Subject",
        body="Body",
    )

    candidates = [candidate]
    by_message_id = {}
    by_fingerprint = {}
    candidate_lookups = {}
    candidate_fingerprints = {}

    updates = _find_matches_for_candidates(
        candidates,
        by_message_id,
        by_fingerprint,
        candidate_lookups,
        candidate_fingerprints,
    )

    assert updates == []
