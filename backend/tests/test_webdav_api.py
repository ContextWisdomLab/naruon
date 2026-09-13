import base64
import hashlib
import hmac
import json
import time
import uuid
from contextlib import asynccontextmanager

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import get_auth_context, get_current_user
from core.config import settings
from db.models import TicketTask
from db.session import get_db
from main import app
from services.webdav_service import WebDavService, webdav_service

pytestmark = pytest.mark.usefixtures("dev_auth_dependency_overrides")
TEST_SESSION_HMAC_SECRET = "webdav-knowledge-hmac-material-32-bytes"  # noqa: S105


async def _check_postgres_connection_or_skip(engine):
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except (
        ConnectionRefusedError,
        OSError,
        OperationalError,
        asyncpg.CannotConnectNowError,
        asyncpg.InvalidAuthorizationSpecificationError,
        asyncpg.InvalidCatalogNameError,
        asyncpg.InvalidPasswordError,
    ):
        await engine.dispose()
        pytest.skip("PostgreSQL smoke path unavailable")


@asynccontextmanager
async def _override_auth_and_db_client(engine, user_id):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_real_db():
        async with session_factory() as session:
            yield session

    previous_override = app.dependency_overrides.pop(get_auth_context, None)
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    app.dependency_overrides[get_db] = override_real_db

    token = _signed_session_token(
        _valid_session_payload(
            sub=user_id, org="org-acme", workspace="workspace-org-acme"
        )
    )

    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        yield client
    finally:
        await client.aclose()
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret
        if previous_override is not None:
            app.dependency_overrides[get_auth_context] = previous_override
        app.dependency_overrides.pop(get_db, None)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signed_session_token(payload: dict[str, object]) -> str:
    header_segment = _base64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
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
        "groups": ["group-1", "group-2"],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def stub_webdav_service(monkeypatch):
    async def fake_accounts(db, user_id, organization_id=None, workspace_id=None):
        del organization_id, workspace_id
        return (
            [
                {
                    "source_id": "webdav_src_demo_primary",
                    "display_label": "WebDAV source webdav_src_demo_primary",
                    "writeback_enabled": True,
                    "etag": "etag-webdav-demo-primary",
                }
            ]
            if user_id == "alice"
            else []
        )

    async def fake_folders(db, user_id, organization_id=None):
        return (
            [
                {
                    "folder_uid": "webdav_folder_demo_roadmap",
                    "project_name": "Naruon Roadmap 2026",
                    "webdav_path": "/Projects/Naruon_Roadmap_2026",
                    "owner_user_id": "alice",
                    "organization_id": "org-acme",
                },
                {
                    "folder_uid": "webdav_folder_demo_marketing",
                    "project_name": "Marketing Assets",
                    "webdav_path": "/Projects/Marketing_Assets",
                    "owner_user_id": "alice",
                    "organization_id": "org-acme",
                },
            ]
            if user_id == "alice" and organization_id == "org-acme"
            else []
        )

    async def fake_intent(
        db,
        user_id,
        organization_id=None,
        workspace_id=None,
        target_source_id=None,
    ):
        return webdav_service.determine_webdav_writeback_intent_from_accounts(
            await fake_accounts(db, user_id, organization_id, workspace_id),
            target_source_id=target_source_id,
        )

    async def fake_knowledge_intent(
        db,
        user_id,
        organization_id,
        workspace_id,
        source_task_id,
        target_source_id=None,
    ):
        if source_task_id == "task-email":
            return {
                "status": "error",
                "error_code": "validation_error",
                "message": "Task is not self-sent knowledge.",
            }
        if source_task_id != "task-self-knowledge":
            return {
                "status": "error",
                "error_code": "not_found",
                "message": "Self-sent knowledge task was not found.",
            }
        result = await fake_intent(
            db,
            user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            target_source_id=target_source_id,
        )
        if result.get("status") == "error":
            return result
        return {
            **result,
            "intent": "knowledge_materialization",
            "status": "intent_ready",
            "task_id": source_task_id,
            "source_type": "self_sent_knowledge",
            "source_email_id": "<self-note@example.com>",
            "source_thread_id": "thread-self-note",
            "source_id": result["source_id"],
            "target_label": result["target_label"],
            "target_path": f"/Naruon/Notes/{source_task_id}.md",
            "requires_if_match": result["requires_if_match"],
            "if_match": result.get("if_match"),
            "provenance": result["provenance"],
            "provider_write_executed": False,
            "audit_event": "webdav.self_sent_knowledge_intent.created",
        }

    monkeypatch.setattr(webdav_service, "get_connected_accounts_from_db", fake_accounts)
    monkeypatch.setattr(webdav_service, "get_project_folders_from_db", fake_folders)
    monkeypatch.setattr(
        webdav_service,
        "determine_webdav_writeback_intent_from_db",
        fake_intent,
    )
    monkeypatch.setattr(
        webdav_service,
        "determine_knowledge_materialization_intent_from_db",
        fake_knowledge_intent,
    )


@pytest.fixture
def auth_client():
    with TestClient(
        app,
        headers={"X-User-Id": "alice", "X-Organization-Id": "org-acme"},
    ) as client:
        yield client


def _request_with_signed_session(method: str, path: str, json_body: dict | None = None):
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    original_overrides = dict(app.dependency_overrides)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            return client.request(
                method,
                path,
                json=json_body,
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def _request_without_signed_session(
    method: str,
    path: str,
    json_body: dict | None = None,
):
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            return client.request(
                method,
                path,
                json=json_body,
                headers={
                    "X-User-Id": "alice",
                    "X-Organization-Id": "org-acme",
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_get_webdav_accounts(auth_client):
    response = auth_client.get("/api/webdav/accounts")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) > 0
    assert body[0]["source_id"] == "webdav_src_demo_primary"
    assert body[0]["display_label"] == "WebDAV source webdav_src_demo_primary"
    assert body[0]["writeback_enabled"] is True
    assert body[0]["etag"] == "etag-webdav-demo-primary"
    assert "account_id" not in body[0]
    assert "server_url" not in body[0]
    assert "username" not in body[0]


def test_get_webdav_accounts_accepts_signed_bearer_session():
    response = _request_with_signed_session("GET", "/api/webdav/accounts")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["source_id"] == "webdav_src_demo_primary"
    assert "account_id" not in body[0]


def test_webdav_routes_reject_public_identity_headers_without_signed_session():
    response = _request_without_signed_session("GET", "/api/webdav/accounts")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_get_project_folders(auth_client):
    response = auth_client.get("/api/webdav/folders")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    assert body[0]["folder_uid"] == "webdav_folder_demo_roadmap"
    assert body[0]["project_name"] == "Naruon Roadmap 2026"
    assert body[0]["owner_user_id"] == "alice"
    assert body[0]["organization_id"] == "org-acme"
    assert body[1]["project_name"] == "Marketing Assets"
    assert "folder_id" not in body[0]


def test_get_webdav_writeback_intent(auth_client):
    response = auth_client.post("/api/webdav/writeback-intent", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "writeback"
    assert body["requires_if_match"] is True
    assert body["source_id"] == "webdav_src_demo_primary"
    assert body["target_label"] == "WebDAV source webdav_src_demo_primary"
    assert body["provenance"] == "server-authoritative"
    assert body["if_match"] == "etag-webdav-demo-primary"
    assert "account_id" not in body
    assert "server_url" not in body


def test_get_webdav_writeback_intent_accepts_signed_bearer_session():
    response = _request_with_signed_session(
        "POST",
        "/api/webdav/writeback-intent",
        {"target_source_id": "webdav_src_demo_primary"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"] == "webdav_src_demo_primary"
    assert body["if_match"] == "etag-webdav-demo-primary"
    assert "account_id" not in body


def test_get_webdav_writeback_intent_with_target_account(auth_client):
    response = auth_client.post(
        "/api/webdav/writeback-intent",
        json={"target_source_id": "webdav_src_demo_primary"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "writeback"
    assert body["source_id"] == "webdav_src_demo_primary"
    assert body["target_label"] == "WebDAV source webdav_src_demo_primary"
    assert body["requires_if_match"] is True
    assert body["if_match"] == "etag-webdav-demo-primary"
    assert body["provenance"] == "server-authoritative"


def test_get_webdav_writeback_intent_with_invalid_target_account(auth_client):
    response = auth_client.post(
        "/api/webdav/writeback-intent",
        json={"target_source_id": "webdav_src_missing"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Requested WebDAV account was not found."


def test_webdav_writeback_rejects_legacy_target_account_id(auth_client):
    response = auth_client.post(
        "/api/webdav/writeback-intent",
        json={"target_account_id": 1},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
    assert response.json()["detail"][0]["loc"] == ["body", "target_account_id"]


def test_get_self_sent_knowledge_webdav_intent(auth_client):
    response = auth_client.post(
        "/api/webdav/knowledge-materialization-intent",
        json={
            "target_source_id": "webdav_src_demo_primary",
            "source_task_id": "task-self-knowledge",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "knowledge_materialization"
    assert body["status"] == "intent_ready"
    assert body["task_id"] == "task-self-knowledge"
    assert body["source_type"] == "self_sent_knowledge"
    assert body["source_email_id"] == "<self-note@example.com>"
    assert body["source_thread_id"] == "thread-self-note"
    assert body["target_path"] == "/Naruon/Notes/task-self-knowledge.md"
    assert body["provider_write_executed"] is False
    assert body["audit_event"] == "webdav.self_sent_knowledge_intent.created"
    assert "related_email_id" not in body
    assert "user_id" not in body
    assert "organization_id" not in body
    assert "account_id" not in body


def test_self_sent_knowledge_webdav_intent_requires_source_task(auth_client):
    response = auth_client.post(
        "/api/webdav/knowledge-materialization-intent",
        json={},
    )
    assert response.status_code == 422


def test_self_sent_knowledge_webdav_intent_returns_not_found_for_other_owner_task(
    auth_client,
):
    response = auth_client.post(
        "/api/webdav/knowledge-materialization-intent",
        json={"source_task_id": "task-other-owner"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Self-sent knowledge task was not found."


def test_self_sent_knowledge_webdav_intent_rejects_non_self_sent_task(auth_client):
    response = auth_client.post(
        "/api/webdav/knowledge-materialization-intent",
        json={"source_task_id": "task-email"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Task is not self-sent knowledge."


def test_self_sent_knowledge_webdav_intent_requires_connected_webdav_account():
    with TestClient(
        app,
        headers={"X-User-Id": "bob", "X-Organization-Id": "org-acme"},
    ) as client:
        response = client.post(
            "/api/webdav/knowledge-materialization-intent",
            json={"source_task_id": "task-self-knowledge"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "No connected WebDAV accounts found."


def test_get_self_sent_knowledge_webdav_intent_accepts_signed_bearer_session():
    response = _request_with_signed_session(
        "POST",
        "/api/webdav/knowledge-materialization-intent",
        {
            "target_source_id": "webdav_src_demo_primary",
            "source_task_id": "task-self-knowledge",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["task_id"] == "task-self-knowledge"
    assert "account_id" not in response.json()


@pytest.mark.asyncio
async def test_knowledge_materialization_rejects_non_self_sent_task(monkeypatch):
    monkeypatch.setattr(
        webdav_service,
        "determine_knowledge_materialization_intent_from_db",
        WebDavService.determine_knowledge_materialization_intent_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )
    task = TicketTask(
        user_id="alice",
        organization_id="org-acme",
        title="Ordinary task",
        source_type="email",
    )
    task.task_uid = "task-email"
    task.related_thread_id = "thread-email"

    class Result:
        def one_or_none(self):
            return (task, "<email@example.com>")

    class Session:
        async def execute(self, stmt):
            return Result()

    monkeypatch.setattr(
        webdav_service,
        "get_connected_accounts_from_db",
        lambda session, user_id, organization_id=None, workspace_id=None: [],
    )

    result = await webdav_service.determine_knowledge_materialization_intent_from_db(
        Session(),
        "alice",
        "org-acme",
        "workspace-org-acme",
        "task-email",
    )

    assert result == {
        "status": "error",
        "error_code": "validation_error",
        "message": "Task is not self-sent knowledge.",
    }


@pytest.mark.asyncio
async def test_knowledge_materialization_requires_source_email_provenance(monkeypatch):
    monkeypatch.setattr(
        webdav_service,
        "determine_knowledge_materialization_intent_from_db",
        WebDavService.determine_knowledge_materialization_intent_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )
    task = TicketTask(
        user_id="alice",
        organization_id="org-acme",
        title="Self sent task without email",
        source_type="self_sent_knowledge",
    )
    task.task_uid = "task-self-no-email"
    task.related_thread_id = "thread-self-note"

    class Result:
        def one_or_none(self):
            return (task, None)

    class Session:
        async def execute(self, stmt):
            return Result()

    result = await webdav_service.determine_knowledge_materialization_intent_from_db(
        Session(),
        "alice",
        "org-acme",
        "workspace-org-acme",
        "task-self-no-email",
    )

    assert result == {
        "status": "error",
        "error_code": "missing_provenance",
        "message": "Self-sent knowledge task missing source email provenance.",
    }


def test_get_webdav_writeback_intent_no_accounts():
    with TestClient(
        app,
        headers={"X-User-Id": "bob", "X-Organization-Id": "org-acme"},
    ) as client:
        response = client.post("/api/webdav/writeback-intent", json={})
        assert response.status_code == 422
        assert response.json()["detail"] == "No connected WebDAV accounts found."


def test_webdav_writeback_intent_skips_disabled_accounts():
    svc = WebDavService()
    result = svc.determine_webdav_writeback_intent_from_accounts(
        [
            {
                "source_id": "webdav_src_disabled",
                "server_url": "https://webdav.naruon.net",
                "username": "demo_user",
                "writeback_enabled": False,
            }
        ],
        target_source_id="webdav_src_disabled",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "no_webdav_account"


def test_webdav_writeback_intent_fails_closed_without_eligibility():
    svc = WebDavService()
    result = svc.determine_webdav_writeback_intent_from_accounts(
        [
            {
                "source_id": "webdav_src_missing_eligibility",
                "server_url": "https://webdav.naruon.net",
                "username": "demo_user",
            }
        ],
        target_source_id="webdav_src_missing_eligibility",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "no_webdav_account"


@pytest.mark.asyncio
async def test_knowledge_materialization_execute_provider_dispatches_runner(
    monkeypatch,
    auth_client,
):
    dispatched_commands: list[dict[str, object]] = []

    async def fake_dispatch_command(
        organization_id,
        workspace_id,
        command,
        *,
        timeout_seconds=30,
    ):
        assert organization_id == "org-acme"
        assert workspace_id == "workspace-org-acme"
        dispatched_commands.append(command)
        return {
            "request_id": "runner_req_webdav_1",
            "status": "success",
            "provider_write_executed": True,
            "provider_status": 204,
            "etag": "etag-after-write",
        }

    monkeypatch.setattr(
        "api.webdav.runner_manager.dispatch_command", fake_dispatch_command
    )
    response = auth_client.post(
        "/api/webdav/knowledge-materialization-intent",
        json={
            "source_task_id": "task-self-knowledge",
            "target_source_id": "webdav_src_demo_primary",
            "execute_provider": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["provider_write_executed"] is True
    assert body["provider_status"] == 204
    assert body["runner_request_id"] == "runner_req_webdav_1"
    assert body["retry_item_uid"] is None
    assert body["if_match"] == "etag-webdav-demo-primary"

    assert len(dispatched_commands) == 1
    command = dispatched_commands[0]
    assert command["action"] == "write_webdav"
    assert command["account"] == "webdav_src_demo_primary"
    assert command["source_id"] == "webdav_src_demo_primary"
    assert command["target_path"] == "/Naruon/Notes/task-self-knowledge.md"
    assert command["if_match"] == "etag-webdav-demo-primary"
    assert command["content_type"] == "text/markdown; charset=utf-8"
    assert "task-self-knowledge" in command["content"]
    assert "server_url" not in command


@pytest.mark.asyncio
async def test_knowledge_materialization_execute_provider_returns_retry_item(
    monkeypatch,
    auth_client,
):
    async def fake_dispatch_command(
        organization_id,
        workspace_id,
        command,
        *,
        timeout_seconds=30,
    ):
        assert organization_id == "org-acme"
        assert workspace_id == "workspace-org-acme"
        assert command["action"] == "write_webdav"
        return {
            "status": "error",
            "error_code": "runner_response_timeout",
            "provider_write_executed": False,
            "retry_item_uid": "provider_retry_webdav_1",
        }

    monkeypatch.setattr(
        "api.webdav.runner_manager.dispatch_command", fake_dispatch_command
    )

    response = auth_client.post(
        "/api/webdav/knowledge-materialization-intent",
        json={
            "source_task_id": "task-self-knowledge",
            "target_source_id": "webdav_src_demo_primary",
            "execute_provider": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["provider_write_executed"] is False
    assert body["error_code"] == "runner_response_timeout"
    assert body["retry_item_uid"] == "provider_retry_webdav_1"


@pytest.mark.asyncio
async def test_webdav_writeback_intent_real_postgres_smoke(monkeypatch):
    source_uid = f"webdav_src_{uuid.uuid4().hex[:24]}"
    user_id = f"webdav-smoke-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(
        webdav_service,
        "get_connected_accounts_from_db",
        WebDavService.get_connected_accounts_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )
    monkeypatch.setattr(
        webdav_service,
        "determine_webdav_writeback_intent_from_db",
        WebDavService.determine_webdav_writeback_intent_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )

    engine = create_async_engine(settings.DATABASE_URL)
    await _check_postgres_connection_or_skip(engine)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS webdav_accounts (
                        account_id INTEGER PRIMARY KEY,
                        source_uid VARCHAR UNIQUE NOT NULL,
                        organization_id VARCHAR,
                        workspace_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        server_url VARCHAR NOT NULL,
                        username VARCHAR NOT NULL,
                        credentials_encrypted VARCHAR NOT NULL,
                        writeback_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        etag_value VARCHAR,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE webdav_accounts "
                    "ADD COLUMN IF NOT EXISTS source_uid VARCHAR"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE webdav_accounts "
                    "ADD COLUMN IF NOT EXISTS organization_id VARCHAR"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE webdav_accounts "
                    "ADD COLUMN IF NOT EXISTS workspace_id VARCHAR"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE webdav_accounts "
                    "ADD COLUMN IF NOT EXISTS writeback_enabled "
                    "BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE webdav_accounts "
                    "ADD COLUMN IF NOT EXISTS etag_value VARCHAR"
                )
            )
            await conn.execute(
                text(
                    """
                    DELETE FROM webdav_accounts
                    WHERE source_uid = :source_uid
                    """
                ),
                {"source_uid": source_uid},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO webdav_accounts (
                        account_id,
                        source_uid,
                        organization_id,
                        workspace_id,
                        user_id,
                        server_url,
                        username,
                        credentials_encrypted,
                        writeback_enabled,
                        etag_value,
                        created_at
                    )
                    VALUES (
                        :account_id,
                        :source_uid,
                        :organization_id,
                        :workspace_id,
                        :user_id,
                        :server_url,
                        :username,
                        :credentials_encrypted,
                        :writeback_enabled,
                        :etag_value,
                        now()
                    )
                    """
                ),
                {
                    "account_id": 10_000 + (uuid.uuid4().int % 1_000_000),
                    "source_uid": source_uid,
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "user_id": user_id,
                    "server_url": "https://real-webdav.naruon.net",
                    "username": user_id,
                    "credentials_encrypted": "test-only-placeholder",
                    "writeback_enabled": True,
                    "etag_value": "etag-webdav-smoke",
                },
            )
    except Exception:
        await engine.dispose()
        raise

    async with _override_auth_and_db_client(engine, user_id) as client:
        try:
            response = await client.post(
                "/api/webdav/writeback-intent",
                json={"target_source_id": source_uid},
            )
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM webdav_accounts WHERE source_uid = :source_uid"),
                    {"source_uid": source_uid},
                )
            await engine.dispose()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"] == source_uid
    assert body["target_label"] == f"WebDAV source {source_uid}"
    assert body["provenance"] == "server-authoritative"
    assert body["if_match"] == "etag-webdav-smoke"
    assert "account_id" not in body
    assert "server_url" not in body


@pytest.mark.asyncio
async def test_webdav_folders_real_postgres_uses_opaque_folder_uid(monkeypatch):
    folder_uid = f"webdav_folder_{uuid.uuid4().hex[:24]}"
    rival_folder_uid = f"webdav_folder_{uuid.uuid4().hex[:24]}"
    folder_id = 10_000 + (uuid.uuid4().int % 1_000_000)
    rival_folder_id = 10_000 + (uuid.uuid4().int % 1_000_000)
    user_id = f"webdav-folder-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        WebDavService.get_project_folders_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )

    engine = create_async_engine(settings.DATABASE_URL)
    await _check_postgres_connection_or_skip(engine)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS project_folders (
                        folder_id INTEGER PRIMARY KEY,
                        folder_uid VARCHAR UNIQUE NOT NULL,
                        user_id VARCHAR NOT NULL,
                        organization_id VARCHAR,
                        project_name VARCHAR NOT NULL,
                        webdav_path VARCHAR NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE project_folders "
                    "ADD COLUMN IF NOT EXISTS folder_uid VARCHAR"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE project_folders "
                    "ADD COLUMN IF NOT EXISTS organization_id VARCHAR"
                )
            )
            await conn.execute(
                text(
                    "DELETE FROM project_folders "
                    "WHERE folder_uid IN (:folder_uid, :rival_folder_uid) "
                    "OR folder_id IN (:folder_id, :rival_folder_id)"
                ),
                {
                    "folder_uid": folder_uid,
                    "rival_folder_uid": rival_folder_uid,
                    "folder_id": folder_id,
                    "rival_folder_id": rival_folder_id,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO project_folders (
                        folder_id,
                        folder_uid,
                        user_id,
                        organization_id,
                        project_name,
                        webdav_path,
                        created_at
                    )
                    VALUES (
                        :folder_id,
                        :folder_uid,
                        :user_id,
                        :organization_id,
                        :project_name,
                        :webdav_path,
                        now()
                    )
                    """
                ),
                {
                    "folder_id": folder_id,
                    "folder_uid": folder_uid,
                    "user_id": user_id,
                    "organization_id": "org-acme",
                    "project_name": "Source-backed Folder",
                    "webdav_path": "/Projects/Source_Backed_Folder",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO project_folders (
                        folder_id,
                        folder_uid,
                        user_id,
                        organization_id,
                        project_name,
                        webdav_path,
                        created_at
                    )
                    VALUES (
                        :folder_id,
                        :folder_uid,
                        :user_id,
                        :organization_id,
                        :project_name,
                        :webdav_path,
                        now()
                    )
                    """
                ),
                {
                    "folder_id": rival_folder_id,
                    "folder_uid": rival_folder_uid,
                    "user_id": user_id,
                    "organization_id": "org-rival",
                    "project_name": "Rival Folder",
                    "webdav_path": "/Projects/Rival_Folder",
                },
            )
    except Exception:
        await engine.dispose()
        raise

    async with _override_auth_and_db_client(engine, user_id) as client:
        try:
            response = await client.get("/api/webdav/folders")
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "DELETE FROM project_folders "
                        "WHERE folder_uid IN (:folder_uid, :rival_folder_uid) "
                        "OR folder_id IN (:folder_id, :rival_folder_id)"
                    ),
                    {
                        "folder_uid": folder_uid,
                        "rival_folder_uid": rival_folder_uid,
                        "folder_id": folder_id,
                        "rival_folder_id": rival_folder_id,
                    },
                )
            await engine.dispose()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == [
        {
            "folder_uid": folder_uid,
            "project_name": "Source-backed Folder",
            "webdav_path": "/Projects/Source_Backed_Folder",
            "owner_user_id": user_id,
            "organization_id": "org-acme",
        }
    ]
    assert "folder_id" not in body[0]


@pytest.mark.asyncio
async def test_knowledge_materialization_intent_real_postgres_endpoint_smoke(
    monkeypatch,
):
    smoke_id = 10_000 + (uuid.uuid4().int % 1_000_000)
    schema_name = f"webdav_knowledge_{uuid.uuid4().hex}"
    user_id = f"knowledge-smoke-{smoke_id}"
    task_uid = f"task{uuid.uuid4().hex[:28]}"
    message_id = f"<self-knowledge-{smoke_id}@example.com>"
    thread_id = f"thread-knowledge-{smoke_id}"
    source_uid = f"webdav_src_{uuid.uuid4().hex[:24]}"
    monkeypatch.setattr(
        webdav_service,
        "get_connected_accounts_from_db",
        WebDavService.get_connected_accounts_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )
    monkeypatch.setattr(
        webdav_service,
        "determine_webdav_writeback_intent_from_db",
        WebDavService.determine_webdav_writeback_intent_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )
    monkeypatch.setattr(
        webdav_service,
        "determine_knowledge_materialization_intent_from_db",
        WebDavService.determine_knowledge_materialization_intent_from_db.__get__(
            webdav_service,
            WebDavService,
        ),
    )

    admin_engine = create_async_engine(settings.DATABASE_URL)
    await _check_postgres_connection_or_skip(admin_engine)
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema_name}"))
    except Exception:
        await admin_engine.dispose()
        raise

    engine = create_async_engine(
        settings.DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE email_records (
                        id INTEGER PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        organization_id VARCHAR NOT NULL,
                        workspace_id VARCHAR NOT NULL,
                        message_id VARCHAR NOT NULL,
                        thread_id VARCHAR
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TABLE ticket_tasks (
                        task_id INTEGER PRIMARY KEY,
                        task_uid VARCHAR(32) UNIQUE NOT NULL,
                        user_id VARCHAR NOT NULL,
                        organization_id VARCHAR,
                        task_title VARCHAR NOT NULL,
                        status_code VARCHAR NOT NULL,
                        priority_code VARCHAR NOT NULL,
                        source_type VARCHAR NOT NULL,
                        email_id INTEGER,
                        thread_id VARCHAR,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TABLE webdav_accounts (
                        account_id INTEGER PRIMARY KEY,
                        source_uid VARCHAR UNIQUE NOT NULL,
                        organization_id VARCHAR,
                        workspace_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        server_url VARCHAR NOT NULL,
                        username VARCHAR NOT NULL,
                        credentials_encrypted VARCHAR NOT NULL,
                        writeback_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        etag_value VARCHAR,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO email_records (
                        id,
                        user_id,
                            organization_id,
                            workspace_id,
                            message_id,
                        thread_id
                    )
                    VALUES (
                        :email_id,
                        :user_id,
                            :organization_id,
                            :workspace_id,
                            :message_id,
                        :thread_id
                    )
                    """
                ),
                {
                    "email_id": smoke_id,
                    "user_id": user_id,
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "message_id": message_id,
                    "thread_id": thread_id,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO ticket_tasks (
                        task_id,
                        task_uid,
                        user_id,
                        organization_id,
                        task_title,
                        status_code,
                        priority_code,
                        source_type,
                        email_id,
                        thread_id
                    )
                    VALUES (
                        :task_id,
                        :task_uid,
                        :user_id,
                        :organization_id,
                        :task_title,
                        'open',
                        'normal',
                        'self_sent_knowledge',
                        :email_id,
                        :thread_id
                    )
                    """
                ),
                {
                    "task_id": smoke_id,
                    "task_uid": task_uid,
                    "user_id": user_id,
                    "organization_id": "org-acme",
                    "task_title": "Memo: source-backed smoke",
                    "email_id": smoke_id,
                    "thread_id": thread_id,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO webdav_accounts (
                        account_id,
                        source_uid,
                        organization_id,
                        workspace_id,
                        user_id,
                        server_url,
                        username,
                        credentials_encrypted,
                        writeback_enabled,
                        etag_value,
                        created_at
                    )
                    VALUES (
                        :account_id,
                        :source_uid,
                        :organization_id,
                        :workspace_id,
                        :user_id,
                        :server_url,
                        :username,
                        :credentials_encrypted,
                        :writeback_enabled,
                        :etag_value,
                        now()
                    )
                    """
                ),
                {
                    "account_id": smoke_id + 1,
                    "source_uid": source_uid,
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "user_id": user_id,
                    "server_url": "https://real-webdav.naruon.net",
                    "username": user_id,
                    "credentials_encrypted": "test-only-placeholder",
                    "writeback_enabled": True,
                    "etag_value": "etag-webdav-knowledge-smoke",
                },
            )
    except Exception:
        await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await admin_engine.dispose()
        raise

    async with _override_auth_and_db_client(engine, user_id) as client:
        try:
            response = await client.post(
                "/api/webdav/knowledge-materialization-intent",
                json={
                    "target_source_id": source_uid,
                    "source_task_id": task_uid,
                },
            )
        finally:
            await engine.dispose()
            async with admin_engine.begin() as conn:
                await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            await admin_engine.dispose()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "knowledge_materialization"
    assert body["status"] == "intent_ready"
    assert body["task_id"] == task_uid
    assert body["source_type"] == "self_sent_knowledge"
    assert body["source_email_id"] == message_id
    assert body["source_thread_id"] == thread_id
    assert body["source_id"] == source_uid
    assert body["target_label"] == f"WebDAV source {source_uid}"
    assert body["target_path"] == f"/Naruon/Notes/{task_uid}.md"
    assert body["requires_if_match"] is True
    assert body["if_match"] == "etag-webdav-knowledge-smoke"
    assert body["provider_write_executed"] is False
    assert "server_url" not in body
