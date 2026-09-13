from types import SimpleNamespace

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from db.session import get_db
from main import app

pytestmark = pytest.mark.usefixtures("dev_auth_dependency_overrides")


# Mock async DB session
class MockResult:
    def __init__(self, obj):
        self.obj = obj

    def scalar_one_or_none(self):
        return self.obj


class MockAsyncSession:
    def __init__(self):
        self.objects = {}

    def _query_key(self, query):
        params = dict(query.compile().params)
        return params.get("user_id_1"), params.get("organization_id_1")

    async def execute(self, query):
        return MockResult(self.objects.get(self._query_key(query)))

    def add(self, obj):
        self.objects[(obj.user_id, obj.organization_id)] = obj

    async def commit(self):
        pass


@pytest.fixture
def mock_db():
    return MockAsyncSession()


@pytest.fixture
def client(mock_db):
    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={"X-User-Id": "testuser"}) as c:
        yield c
    app.dependency_overrides.clear()


def test_tenant_config_endpoint(client, mock_db, monkeypatch):
    host_resolve_calls = []
    destination_resolve_calls = []
    imap_destination_calls = []
    pop3_destination_calls = []

    def fake_validate_smtp_host(smtp_server, *, resolve_host=True):
        host_resolve_calls.append(resolve_host)
        return smtp_server

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        destination_resolve_calls.append(resolve_host)
        return smtp_server, smtp_port

    def fake_validate_imap_destination(imap_server, imap_port, *, resolve_host=True):
        imap_destination_calls.append((imap_server, imap_port, resolve_host))
        return imap_server, imap_port

    def fake_validate_pop3_destination(pop3_server, pop3_port, *, resolve_host=True):
        pop3_destination_calls.append((pop3_server, pop3_port, resolve_host))
        return pop3_server, pop3_port

    monkeypatch.setattr("api.tenant_config.validate_smtp_host", fake_validate_smtp_host)
    monkeypatch.setattr(
        "api.tenant_config.validate_smtp_destination",
        fake_validate_smtp_destination,
    )
    monkeypatch.setattr(
        "api.tenant_config.validate_imap_destination",
        fake_validate_imap_destination,
    )
    monkeypatch.setattr(
        "api.tenant_config.validate_pop3_destination",
        fake_validate_pop3_destination,
    )
    monkeypatch.setattr("api.tenant_config.validate_pop3_port", lambda port: port)

    post_payload = {
        "user_id": "test_user",
        "openai_api_key": "sk-123",
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "sender@example.com",
        "smtp_password": "smtp-secret",
        "imap_server": "imap.example.com",
        "imap_port": 993,
        "imap_username": "imap-user",
        "imap_password": "imap-secret",
        "pop3_server": "pop3.example.com",
        "pop3_port": 995,
        "pop3_username": "pop3-user",
        "pop3_password": "pop3-secret",
        "oauth_client_secret": "secret-456",
    }
    response = client.post(
        "/api/config", json=post_payload, headers={"X-User-Id": "test_user"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert host_resolve_calls == [True]
    assert destination_resolve_calls == [True]
    assert imap_destination_calls == [("imap.example.com", 993, True)]
    assert pop3_destination_calls == [("pop3.example.com", 995, True)]

    assert ("test_user", None) in mock_db.objects

    get_response = client.get(
        "/api/config",
        headers={"X-User-Id": "test_user"},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["user_id"] == "test_user"
    assert data["openai_api_key"] == "********"
    assert data["oauth_client_secret"] == "********"
    assert data["smtp_password"] == "********"
    assert data["imap_password"] == "********"
    assert data["pop3_password"] == "********"
    assert data["smtp_server"] == "smtp.example.com"
    assert data["smtp_port"] == 587
    assert data["smtp_username"] == "sender@example.com"
    assert data["imap_server"] == "imap.example.com"
    assert data["imap_port"] == 993
    assert data["imap_username"] == "imap-user"
    assert data["pop3_server"] == "pop3.example.com"
    assert data["pop3_port"] == 995
    assert data["pop3_username"] == "pop3-user"
    assert data["google_client_secret"] is None


def test_noema_orchestrator_gateway_config_returns_presence_without_the_token(
    client, mock_db
):
    post_payload = {
        "user_id": "test_user",
        "noema_orchestrator_base_url": "https://orchestrator.internal/v1",
        "noema_orchestrator_token": "orch-token-123",
    }
    response = client.post(
        "/api/config", json=post_payload, headers={"X-User-Id": "test_user"}
    )
    assert response.status_code == 200

    get_response = client.get(
        "/api/config",
        headers={"X-User-Id": "test_user"},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["noema_orchestrator_base_url"] == "https://orchestrator.internal/v1"
    assert data["has_noema_orchestrator_token"] is True
    assert "noema_orchestrator_token" not in data
    assert "orch-token-123" not in get_response.text


def test_validate_mail_config_update_revalidates_existing_mail_hosts(monkeypatch):
    from api.tenant_config import validate_mail_config_update

    calls = []

    def record_smtp_host(host, *, resolve_host=True):
        calls.append(("smtp_host", host, resolve_host))
        return host

    def record_smtp_port(port):
        calls.append(("smtp_port", port))
        return port

    def record_smtp_destination(host, port, *, resolve_host=True):
        calls.append(("smtp_destination", host, port, resolve_host))
        return host, port

    def record_imap_destination(host, port, *, resolve_host=True):
        calls.append(("imap_destination", host, port, resolve_host))
        return host, port

    def record_pop3_destination(host, port, *, resolve_host=True):
        calls.append(("pop3_destination", host, port, resolve_host))
        return host, port

    monkeypatch.setattr("api.tenant_config.validate_smtp_host", record_smtp_host)
    monkeypatch.setattr("api.tenant_config.validate_smtp_port", record_smtp_port)
    monkeypatch.setattr(
        "api.tenant_config.validate_smtp_destination",
        record_smtp_destination,
    )
    monkeypatch.setattr(
        "api.tenant_config.validate_imap_destination",
        record_imap_destination,
    )
    monkeypatch.setattr(
        "api.tenant_config.validate_pop3_destination",
        record_pop3_destination,
    )

    validate_mail_config_update(
        {},
        SimpleNamespace(
            smtp_server="smtp.example.com",
            smtp_port=587,
            imap_server="imap.example.com",
            imap_port=None,
            pop3_server="pop3.example.com",
            pop3_port=None,
        ),
    )

    assert calls == [
        ("smtp_host", "smtp.example.com", True),
        ("smtp_port", 587),
        ("smtp_destination", "smtp.example.com", 587, True),
        ("imap_destination", "imap.example.com", 993, True),
        ("pop3_destination", "pop3.example.com", 995, True),
    ]


def test_validate_mail_config_update_rejects_unsafe_partial_override(caplog):
    from api.tenant_config import validate_mail_config_update

    with caplog.at_level("WARNING", logger="api.tenant_config"):
        with pytest.raises(HTTPException) as exc_info:
            validate_mail_config_update({"imap_server": "127.0.0.1"}, None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid IMAP configuration"
    assert "IMAP configuration validation failed" in caplog.text
    assert "127.0.0.1" not in caplog.text


def test_legacy_tenant_config_endpoint_keeps_organization_scope(
    client, mock_db, monkeypatch
):
    monkeypatch.setattr(
        "api.tenant_config.validate_smtp_host",
        lambda host, *, resolve_host=True: host,
    )
    monkeypatch.setattr(
        "api.tenant_config.validate_smtp_destination",
        lambda host, port, *, resolve_host=True: (host, port),
    )

    acme_response = client.post(
        "/api/config",
        json={
            "user_id": "shared_user",
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
        },
        headers={"X-User-Id": "shared_user", "X-Organization-Id": "org-acme"},
    )
    rival_response = client.post(
        "/api/config",
        json={
            "user_id": "shared_user",
            "smtp_server": "smtp.other.com",
            "smtp_port": 587,
        },
        headers={"X-User-Id": "shared_user", "X-Organization-Id": "org-rival"},
    )

    acme_get = client.get(
        "/api/config",
        headers={"X-User-Id": "shared_user", "X-Organization-Id": "org-acme"},
    )
    rival_get = client.get(
        "/api/config",
        headers={"X-User-Id": "shared_user", "X-Organization-Id": "org-rival"},
    )

    assert acme_response.status_code == 200
    assert rival_response.status_code == 200
    assert acme_get.json()["smtp_server"] == "smtp.example.com"
    assert rival_get.json()["smtp_server"] == "smtp.other.com"
    assert ("shared_user", "org-acme") in mock_db.objects
    assert ("shared_user", "org-rival") in mock_db.objects


def test_tenant_config_rejects_private_smtp_host(client):
    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "smtp_server": "127.0.0.1",
            "smtp_port": 587,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid SMTP configuration" in response.json()["detail"]


def test_tenant_config_rejects_metadata_smtp_host(client):
    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "smtp_server": "169.254.169.254",
            "smtp_port": 587,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid SMTP configuration" in response.json()["detail"]


def test_tenant_config_rejects_unsafe_smtp_port(client, monkeypatch):
    def fake_getaddrinfo(host, port=None, *args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", port or 587))]

    monkeypatch.setattr("services.email_client.socket.getaddrinfo", fake_getaddrinfo)

    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "smtp_server": "smtp.example.com",
            "smtp_port": 22,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid SMTP configuration" in response.json()["detail"]


def test_tenant_config_rejects_private_pop3_host(client):
    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "pop3_server": "127.0.0.1",
            "pop3_port": 995,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid POP3 configuration" in response.json()["detail"]


def test_tenant_config_rejects_private_imap_host(client):
    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "imap_server": "127.0.0.1",
            "imap_port": 993,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid IMAP configuration" in response.json()["detail"]


def test_tenant_config_rejects_unallowlisted_imap_host(client, monkeypatch):
    monkeypatch.setattr(
        "services.email_client.settings.ALLOWED_IMAP_HOSTS",
        "mail.example.com",
    )

    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "imap_server": "imap.example.com",
            "imap_port": 993,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid IMAP configuration" in response.json()["detail"]


def test_tenant_config_rejects_unallowlisted_pop3_host(client, monkeypatch):
    monkeypatch.setattr(
        "services.email_client.settings.ALLOWED_POP3_HOSTS",
        "mail.example.com",
    )

    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "pop3_server": "pop3.example.com",
            "pop3_port": 995,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid POP3 configuration" in response.json()["detail"]


def test_tenant_config_rejects_unsafe_imap_port(client, monkeypatch):
    def fake_validate_imap_destination(host, port, *, resolve_host=True):
        from services.email_client import validate_imap_port

        validate_imap_port(port)
        return host, port

    monkeypatch.setattr(
        "api.tenant_config.validate_imap_destination",
        fake_validate_imap_destination,
    )

    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "imap_server": "imap.example.com",
            "imap_port": 22,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid IMAP configuration" in response.json()["detail"]


def test_tenant_config_rejects_unsafe_pop3_port(client, monkeypatch):
    def fake_validate_pop3_destination(host, port, *, resolve_host=True):
        from services.email_client import validate_pop3_port

        validate_pop3_port(port)
        return host, port

    monkeypatch.setattr(
        "api.tenant_config.validate_pop3_destination",
        fake_validate_pop3_destination,
    )

    response = client.post(
        "/api/config",
        json={
            "user_id": "test_user",
            "pop3_server": "pop3.example.com",
            "pop3_port": 22,
        },
        headers={"X-User-Id": "test_user"},
    )

    assert response.status_code == 400
    assert "Invalid POP3 configuration" in response.json()["detail"]


@pytest.mark.parametrize(
    "permitted_role",
    (
        "system_admin",
        "platform_admin",
        "tenant_admin",
        "organization_admin",
        "group_admin",
        "member",
    ),
)
def test_tenant_config_get_returns_own_config_for_permitted_role(
    client, permitted_role
):
    # GET /api/config enforces RBAC through ensure_mailbox_config_self_access and
    # always returns the authenticated session user's own config (no user_id parameter).
    response = client.get(
        "/api/config",
        headers={
            "X-User-Id": "session-user",
            "X-User-Role": permitted_role,
            "X-Organization-Id": "org-acme",
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == "session-user"


@pytest.mark.parametrize(
    "admin_role", ("system_admin", "platform_admin", "tenant_admin")
)
def test_tenant_config_post_rejects_cross_user_admin_access(client, admin_role):
    response = client.post(
        "/api/config",
        json={"user_id": "member-user"},
        headers={
            "X-User-Id": "admin",
            "X-User-Role": admin_role,
            "X-Organization-Id": "org-acme",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Mailbox settings are personal and can only be managed by the authenticated user"
    }


@pytest.mark.parametrize("role", ("group_admin", "member"))
def test_global_config_requires_admin(client, role):
    response = client.get(
        "/api/config/global",
        headers={
            "X-User-Id": "member-user",
            "X-User-Role": role,
            "X-Organization-Id": "org-acme",
            "X-Workspace-Id": "ws-1",
        },
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough privileges"}


@pytest.mark.parametrize(
    "admin_role",
    ("system_admin", "platform_admin", "tenant_admin", "organization_admin"),
)
def test_global_config_allows_admin(client, admin_role):
    response = client.get(
        "/api/config/global",
        headers={
            "X-User-Id": "admin-user",
            "X-User-Role": admin_role,
            "X-Organization-Id": "org-acme",
            "X-Workspace-Id": "ws-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest_asyncio.fixture(scope="function")
async def smoke_db_engine():
    from asyncpg.exceptions import (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
    )
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import create_async_engine

    from core.config import settings
    from db.models import Base

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    except (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
        OperationalError,
        OSError,
    ) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
def smoke_sessionmaker(smoke_db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(smoke_db_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def clean_smoke_user_db(smoke_sessionmaker):
    from sqlalchemy import text

    user_id = "pop3-smoke-user"

    async def cleanup():
        async with smoke_sessionmaker() as session:
            await session.execute(
                text("DELETE FROM tenant_configs WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            await session.commit()

    await cleanup()
    yield user_id
    await cleanup()


@pytest.fixture(scope="function")
def smoke_db_override(smoke_sessionmaker):
    async def real_db_override():
        async with smoke_sessionmaker() as session:
            yield session

    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = real_db_override
    yield
    if previous_db_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_db_override


@pytest.fixture(scope="function")
def smoke_encryption_key():
    from core.config import settings

    old_encryption_key = settings.ENCRYPTION_KEY
    settings.ENCRYPTION_KEY = SecretStr(Fernet.generate_key().decode("ascii"))
    yield
    settings.ENCRYPTION_KEY = old_encryption_key


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_create_read_pop3_postgres_smoke(
    monkeypatch,
    smoke_sessionmaker,
    clean_smoke_user_db,
    smoke_db_override,
    smoke_encryption_key,
):
    from sqlalchemy import text

    def fake_validate_pop3_destination(host, port, *, resolve_host=True):
        return host, port

    monkeypatch.setattr(
        "api.tenant_config.validate_pop3_destination",
        fake_validate_pop3_destination,
    )

    user_id = clean_smoke_user_db
    pop3_password = "pop3-smoke-secret"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        headers={"X-User-Id": user_id},
        base_url="http://test",
    ) as real_client:
        post_response = await real_client.post(
            "/api/config",
            json={
                "user_id": user_id,
                "pop3_server": "pop3.example.com",
                "pop3_port": 995,
                "pop3_username": "pop3-user",
                "pop3_password": pop3_password,
            },
        )
        get_response = await real_client.get(
            "/api/config",
        )

    async with smoke_sessionmaker() as session:
        raw_pop3_password = (
            await session.execute(
                text(
                    "SELECT pop3_password FROM tenant_configs WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            )
        ).scalar_one()

    assert post_response.status_code == 200
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["pop3_server"] == "pop3.example.com"
    assert data["pop3_port"] == 995
    assert data["pop3_username"] == "pop3-user"
    assert data["pop3_password"] == "********"
    assert raw_pop3_password != pop3_password
