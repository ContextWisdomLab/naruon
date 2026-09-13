import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
import uuid

import asyncpg
from fastapi.testclient import TestClient
import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import AuthContext, get_auth_context, get_current_user
from api.security import _webdav_scope_statement
from core.config import settings
from cryptography.fernet import Fernet
from db.models import (
    get_fernet,
    CalendarWritebackSource,
    ConnectorSignalEvent,
    SecurityAuditEvent,
    WebdavAccount,
)
from db.session import get_db
from main import app

pytestmark = pytest.mark.usefixtures("dev_auth_dependency_overrides")
TEST_SESSION_HMAC_SECRET = "security-governance-hmac-material-32-bytes"  # noqa: S105


class MockResult:
    def __init__(self, obj):
        self.obj = obj

    def scalars(self):
        return self

    def all(self):
        return self.obj if isinstance(self.obj, list) else []


class MockAsyncSession:
    def __init__(
        self,
        webdav_accounts: list[WebdavAccount] | None = None,
        calendar_sources: list[CalendarWritebackSource] | None = None,
        audit_events: list[SecurityAuditEvent] | None = None,
        connector_events: list[ConnectorSignalEvent] | None = None,
    ):
        self.results = [
            webdav_accounts or [],
            calendar_sources or [],
            audit_events or [],
            connector_events or [],
        ]
        self.execute_calls = 0
        self.added: list[object] = []
        self.committed = False

    async def execute(self, query):
        result = self.results[self.execute_calls]
        self.execute_calls += 1
        return MockResult(_scope_rows_for_query(query, result))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _scope_rows_for_query(query, rows):
    compiled = query.compile()
    null_columns = _null_predicate_columns(str(compiled))
    return [
        row
        for row in rows
        if _row_matches_query_params(row, compiled.params, null_columns)
    ]


def _null_predicate_columns(compiled_query: str) -> set[str]:
    query_text = " ".join(compiled_query.lower().split())
    return {
        column_name
        for column_name in (
            "actor_user_id",
            "organization_id",
            "source_protocol",
            "user_id",
            "workspace_id",
        )
        if f".{column_name} is null" in query_text
        or f" {column_name} is null" in query_text
    }


def _column_name_from_param(param_name: str) -> str | None:
    column_name, separator, suffix = param_name.rpartition("_")
    if separator == "_" and suffix.isdigit():
        return column_name
    return None


def _row_matches_query_params(row, params, null_columns: set[str]) -> bool:
    for column_name in null_columns:
        if hasattr(row, column_name) and getattr(row, column_name) is not None:
            return False

    for param_name, value in params.items():
        column_name = _column_name_from_param(param_name)
        if column_name is None or not hasattr(row, column_name):
            if isinstance(value, int):
                continue
            return False
        row_value = getattr(row, column_name)
        if isinstance(value, list):
            if row_value not in value:
                return False
            continue
        if isinstance(value, int):
            continue
        if not isinstance(value, str):
            continue
        if row_value != value:
            return False
    return True


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
        "sub": "admin",
        "role": "member",
        "org": "org-acme",
        "groups": ["group-security"],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return payload


def _now() -> datetime:
    return datetime(2026, 5, 28, 4, 0, tzinfo=timezone.utc)


def _webdav_account(
    source_uid: str,
    user_id: str,
    organization_id: str | None = "org-acme",
    workspace_id: str = "workspace-org-acme",
) -> WebdavAccount:
    return WebdavAccount(
        source_uid=source_uid,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        server_url="https://files.acme.example/dav",
        username="files@example.com",
        credentials_encrypted="credential secret",
        writeback_enabled=True,
        created_at=_now(),
    )


def _calendar_source(
    source_uid: str,
    user_id: str,
    organization_id: str | None = "org-acme",
) -> CalendarWritebackSource:
    return CalendarWritebackSource(
        source_uid=source_uid,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id="workspace-org-acme",
        account_ref="caldav-account-ref",
        provider_name="Customer CalDAV",
        source_protocol="caldav",
        source_host="calendar.acme.example",
        writeback_enabled=True,
        etag_value="etag-caldav-primary",
        created_at=_now(),
    )


def _connector_event(
    event_uid: str,
    organization_id: str = "org-acme",
    workspace_id: str = "workspace-org-acme",
) -> ConnectorSignalEvent:
    return ConnectorSignalEvent(
        event_uid=event_uid,
        organization_id=organization_id,
        workspace_id=workspace_id,
        signal_key="connector_heartbeat",
        state_code="heartbeat",
        detail_text="outbound connector heartbeat",
        observed_at=_now(),
    )


def _audit_event(
    event_uid: str,
    actor_user_id: str = "admin",
    organization_id: str | None = "org-acme",
    workspace_id: str = "workspace-org-acme",
) -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_uid=event_uid,
        actor_user_id=actor_user_id,
        actor_role="tenant_admin",
        organization_id=organization_id,
        workspace_id=workspace_id,
        event_action="update",
        resource_type="llm_provider",
        resource_uid="llm_provider:provider_primary",
        evidence_source="api.llm_providers",
        detail_text="Updated provider configuration",
        observed_at=_now(),
    )


def test_mock_query_scope_maps_params_to_specific_columns():
    query = _webdav_scope_statement(
        AuthContext(
            user_id="member",
            role="member",
            organization_id="org-acme",
            group_ids=(),
            workspace_id="workspace-org-acme",
        )
    )
    rows = [
        _webdav_account("webdav_src_owned", "member", "org-acme"),
        _webdav_account("webdav_src_cross_column", "org-acme", "member"),
    ]

    scoped_rows = _scope_rows_for_query(query, rows)

    assert [row.source_uid for row in scoped_rows] == ["webdav_src_owned"]


def test_mock_query_scope_enforces_null_organization_predicate():
    query = _webdav_scope_statement(
        AuthContext(
            user_id="solo",
            role="member",
            organization_id=None,
            group_ids=(),
            workspace_id="workspace-personal",
        )
    )
    rows = [
        _webdav_account(
            "webdav_src_personal",
            "solo",
            None,
            workspace_id="workspace-personal",
        ),
        _webdav_account(
            "webdav_src_org_leak",
            "solo",
            "org-acme",
            workspace_id="workspace-personal",
        ),
    ]

    scoped_rows = _scope_rows_for_query(query, rows)

    assert [row.source_uid for row in scoped_rows] == ["webdav_src_personal"]


def test_mock_query_scope_enforces_webdav_workspace_predicate():
    query = _webdav_scope_statement(
        AuthContext(
            user_id="member",
            role="member",
            organization_id="org-acme",
            group_ids=(),
            workspace_id="workspace-active",
        )
    )
    rows = [
        _webdav_account(
            "webdav_src_active",
            "member",
            "org-acme",
            workspace_id="workspace-active",
        ),
        _webdav_account(
            "webdav_src_other_workspace",
            "member",
            "org-acme",
            workspace_id="workspace-other",
        ),
    ]

    scoped_rows = _scope_rows_for_query(query, rows)

    assert [row.source_uid for row in scoped_rows] == ["webdav_src_active"]


@pytest.fixture
def mock_db():
    return MockAsyncSession(
        webdav_accounts=[
            _webdav_account("webdav_src_org_primary", "owner"),
            _webdav_account("webdav_src_other_org", "owner", "org-rival"),
        ],
        calendar_sources=[
            _calendar_source("caldav_src_primary", "owner"),
            _calendar_source("caldav_src_other_org", "owner", "org-rival"),
        ],
        audit_events=[
            _audit_event("audit_evt_provider_update"),
            _audit_event("audit_evt_other_org", organization_id="org-rival"),
        ],
        connector_events=[
            _connector_event("connector_evt_heartbeat"),
            _connector_event("connector_evt_other_org", "org-rival"),
        ],
    )


@pytest.fixture
def admin_client(mock_db):
    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(
            app,
            headers={
                "X-User-Id": "admin",
                "X-User-Role": "tenant_admin",
                "X-Organization-Id": "org-acme",
            },
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_access_surface_returns_org_scoped_sources_and_policy_decisions(admin_client):
    response = admin_client.get("/api/security/access-surface")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["viewer"]["role"] == "tenant_admin"
    assert data["scope_kind"] == "organization"
    source_types = {source["source_type"] for source in data["sources"]}
    assert source_types == {"webdav_repository", "caldav_source"}
    assert "webdav_src_other_org" not in response.text
    assert "caldav_src_other_org" not in response.text
    assert data["connector_events"][0]["state_code"] == "heartbeat"
    assert "connector_evt_other_org" not in response.text
    assert len(data["durable_audit_events"]) == 1
    assert "audit_evt_other_org" not in response.text
    assert data["durable_audit_events"][0]["scope_kind"] == "organization"
    reasons = {decision["reason"] for decision in data["policy_decisions"]}
    assert "organization_denied" in reasons
    assert "data_region_denied" in reasons
    assert "allowed" in reasons


def test_access_surface_redacts_sequential_ids_and_credentials(admin_client):
    response = admin_client.get("/api/security/access-surface")

    assert response.status_code == 200, response.text
    serialized = response.text
    for forbidden in (
        "source_id",
        "event_uid",
        "decision_uid",
        "review_uid",
        "provider_write_executed",
        "workspace-org-acme",
        "org-acme",
        "group-security",
        "webdav_src_org_primary",
        "caldav_src_primary",
        "connector_evt_heartbeat",
        "audit_evt_provider_update",
        "llm_provider:provider_primary",
        "account_id",
        "credentials_encrypted",
        "credential secret",
        "username",
        "files@example.com",
        "api_key",
        "sk-",
        "audit_id",
    ):
        assert forbidden not in serialized


def test_permission_change_intent_records_provider_denial_without_external_write(
    admin_client,
    mock_db,
):
    response = admin_client.post(
        "/api/security/permission-change-intent",
        json={"decision": "deny_external_write", "resource_type": "provider_secret"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "decision": "deny_external_write",
        "resource_type": "provider_secret",
        "allowed": False,
        "reason": "organization_denied",
        "evidence_label": "policy_engine_evidence",
        "audit_event": "security.permission_change_intent",
        "provider_write_executed": False,
        "denial_result": "provider_denied_by_policy",
        "observed_at": body["observed_at"],
    }
    assert body["observed_at"].endswith("Z")
    assert mock_db.committed is True
    assert len(mock_db.added) == 1
    audit_event = mock_db.added[0]
    assert isinstance(audit_event, SecurityAuditEvent)
    assert audit_event.event_action == "permission_change_intent"
    assert audit_event.resource_type == "provider_secret"
    assert audit_event.actor_user_id == "admin"
    assert audit_event.actor_role == "tenant_admin"
    assert audit_event.organization_id == "org-acme"
    assert audit_event.workspace_id == "workspace-org-acme"
    assert audit_event.evidence_source == "api.security.permission_change_intent"
    assert audit_event.detail_text == (
        "permission_intent=deny_external_write; "
        "resource_type=provider_secret; "
        "policy_reason=organization_denied; "
        "provider_write_executed=false"
    )
    assert "sk-" not in response.text
    assert "credential" not in response.text
    assert "org-outside-scope" not in response.text


@pytest.mark.parametrize(
    ("request_body", "expected_allowed", "expected_reason", "expected_denial_result"),
    [
        (
            {"decision": "allow_writeback", "resource_type": "webdav_repository"},
            True,
            "allowed",
            "approval_required_before_external_write",
        ),
        (
            {"decision": "deny_workspace_write", "resource_type": "webdav_repository"},
            False,
            "workspace_denied",
            "provider_denied_by_policy",
        ),
        (
            {"decision": "deny_region_export", "resource_type": "data_export"},
            False,
            "data_region_denied",
            "provider_denied_by_policy",
        ),
        (
            {"decision": "deny_missing_consent", "resource_type": "caldav_source"},
            False,
            "consent_denied",
            "provider_denied_by_policy",
        ),
    ],
)
def test_permission_change_intent_records_policy_variants_without_provider_write(
    admin_client,
    mock_db,
    request_body,
    expected_allowed,
    expected_reason,
    expected_denial_result,
):
    response = admin_client.post(
        "/api/security/permission-change-intent",
        json=request_body,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == request_body["decision"]
    assert body["resource_type"] == request_body["resource_type"]
    assert body["allowed"] is expected_allowed
    assert body["reason"] == expected_reason
    assert body["provider_write_executed"] is False
    assert body["denial_result"] == expected_denial_result
    assert mock_db.committed is True
    assert len(mock_db.added) == 1
    audit_event = mock_db.added[0]
    assert isinstance(audit_event, SecurityAuditEvent)
    assert audit_event.event_action == "permission_change_intent"
    assert audit_event.resource_type == request_body["resource_type"]
    assert audit_event.detail_text == (
        f"permission_intent={request_body['decision']}; "
        f"resource_type={request_body['resource_type']}; "
        f"policy_reason={expected_reason}; "
        "provider_write_executed=false"
    )
    assert "workspace-outside-scope" not in response.text
    assert settings.SECONDARY_DATA_REGION not in response.text
    assert "provider.write" not in response.text


def test_permission_change_intent_requires_admin_role(mock_db):
    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(
            app,
            headers={
                "X-User-Id": "member",
                "X-User-Role": "member",
                "X-Organization-Id": "org-acme",
            },
        ) as client:
            response = client.post(
                "/api/security/permission-change-intent",
                json={
                    "decision": "allow_writeback",
                    "resource_type": "webdav_repository",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 403
    assert "Admin role is required" in response.text
    assert mock_db.added == []
    assert mock_db.committed is False


def test_permission_change_intent_rejects_extra_client_controlled_fields(
    admin_client,
):
    response = admin_client.post(
        "/api/security/permission-change-intent",
        json={
            "decision": "deny_external_write",
            "resource_type": "provider_secret",
            "x-user-id": "attacker",
        },
    )

    assert response.status_code == 422
    assert "extra_forbidden" in response.text


def test_member_surface_only_returns_owned_sources(mock_db):
    async def override_get_db():
        yield MockAsyncSession(
            webdav_accounts=[
                _webdav_account("webdav_src_owned", "member"),
                _webdav_account("webdav_src_admin", "admin"),
            ],
            calendar_sources=[
                _calendar_source("caldav_src_owned", "member"),
                _calendar_source("caldav_src_admin", "admin"),
            ],
            audit_events=[
                _audit_event("audit_evt_member", actor_user_id="member"),
                _audit_event("audit_evt_admin", actor_user_id="admin"),
            ],
            connector_events=[],
        )

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(
            app,
            headers={
                "X-User-Id": "member",
                "X-User-Role": "member",
                "X-Organization-Id": "org-acme",
            },
        ) as client:
            response = client.get("/api/security/access-surface")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["sources"]) == 2
    assert len(body["durable_audit_events"]) == 1
    assert "webdav_src_owned" not in response.text
    assert "caldav_src_owned" not in response.text
    assert "webdav_src_admin" not in response.text
    assert "caldav_src_admin" not in response.text
    assert "audit_evt_member" not in response.text
    assert "audit_evt_admin" not in response.text


def test_access_surface_rejects_public_identity_headers_without_signed_session(mock_db):
    async def override_get_db():
        yield mock_db

    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/security/access-surface",
                headers={
                    "X-User-Id": "admin",
                    "X-User-Role": "tenant_admin",
                    "X-Organization-Id": "org-acme",
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_access_surface_rejects_hmac_bearer_session_without_authoritative_workspace(
    mock_db,
):
    async def override_get_db():
        yield mock_db

    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    original_overrides = dict(app.dependency_overrides)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    # This route's own check (_require_authoritative_workspace_scope) is
    # keyed on session_verifier=="hmac" alone, not on the workspace claim's
    # value, so an otherwise-valid, org-consistent workspace claim isolates
    # that behavior from the org/workspace-derivation check in
    # _auth_context_from_session_payload.
    token = _signed_session_token(_valid_session_payload())
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/security/access-surface",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

    assert response.status_code == 403, response.text
    assert response.json() == {
        "detail": "Authoritative workspace membership is required for security access surface"
    }


@pytest.mark.asyncio
async def test_access_surface_real_postgres_smoke_uses_scoped_sources(
    monkeypatch,
):
    # EncryptedString needs a key for seeding (encrypt) and the API read
    # (decrypt); monkeypatch restores it on any exit incl. skip.
    monkeypatch.setattr(
        settings,
        "ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    user_id = f"security_smoke_user_{uuid.uuid4().hex[:12]}"
    source_uid = f"webdav_src_security_{uuid.uuid4().hex[:18]}"
    caldav_uid = f"caldav_src_security_{uuid.uuid4().hex[:18]}"
    event_uid = f"connector_evt_security_{uuid.uuid4().hex[:18]}"
    audit_uid = f"audit_evt_security_{uuid.uuid4().hex[:18]}"
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO webdav_accounts (
                        source_uid,
                        user_id,
                        organization_id,
                        workspace_id,
                        server_url,
                        username,
                        credentials_encrypted,
                        writeback_enabled,
                        created_at
                    )
                    VALUES (
                        :source_uid,
                        :user_id,
                        :organization_id,
                        :workspace_id,
                        :server_url,
                        :username,
                        :credentials_encrypted,
                        :writeback_enabled,
                        now()
                    )
                    """
                ),
                {
                    "source_uid": source_uid,
                    "user_id": user_id,
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "server_url": "https://security-files.example/dav",
                    "username": "security-smoke@example.com",
                    "credentials_encrypted": get_fernet()
                    .encrypt(b"security-smoke-webdav-secret")
                    .decode("ascii"),
                    "writeback_enabled": True,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO calendar_writeback_sources (
                        source_uid,
                        user_id,
                        organization_id,
                        workspace_id,
                        account_ref,
                        provider_name,
                        source_protocol,
                        source_host,
                        writeback_enabled,
                        etag_value,
                        created_at
                    )
                    VALUES (
                        :source_uid,
                        :user_id,
                        :organization_id,
                        :workspace_id,
                        :account_ref,
                        :provider_name,
                        :source_protocol,
                        :source_host,
                        :writeback_enabled,
                        :etag_value,
                        now()
                    )
                    """
                ),
                {
                    "source_uid": caldav_uid,
                    "user_id": user_id,
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "account_ref": "security-smoke-account",
                    "provider_name": "Security Smoke CalDAV",
                    "source_protocol": "caldav",
                    "source_host": "security-caldav.example",
                    "writeback_enabled": True,
                    "etag_value": "etag-security-smoke",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO connector_signal_events (
                        event_uid,
                        organization_id,
                        workspace_id,
                        signal_key,
                        state_code,
                        detail_text,
                        observed_at
                    )
                    VALUES (
                        :event_uid,
                        :organization_id,
                        :workspace_id,
                        :signal_key,
                        :state_code,
                        :detail_text,
                        now()
                    )
                    """
                ),
                {
                    "event_uid": event_uid,
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "signal_key": "connector_heartbeat",
                    "state_code": "heartbeat",
                    "detail_text": "security smoke connector heartbeat",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO security_audit_events (
                        event_uid,
                        actor_user_id,
                        actor_role,
                        organization_id,
                        workspace_id,
                        event_action,
                        resource_type,
                        resource_uid,
                        evidence_source,
                        detail_text,
                        observed_at
                    )
                    VALUES (
                        :event_uid,
                        :actor_user_id,
                        :actor_role,
                        :organization_id,
                        :workspace_id,
                        :event_action,
                        :resource_type,
                        :resource_uid,
                        :evidence_source,
                        :detail_text,
                        now()
                    )
                    """
                ),
                {
                    "event_uid": audit_uid,
                    "actor_user_id": user_id,
                    "actor_role": "tenant_admin",
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-org-acme",
                    "event_action": "update",
                    "resource_type": "llm_provider",
                    "resource_uid": "llm_provider:security_smoke",
                    "evidence_source": "api.llm_providers",
                    "detail_text": "Updated provider configuration",
                },
            )
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
    except Exception:
        await engine.dispose()
        raise

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_real_db():
        async with session_factory() as session:
            yield session

    original_overrides = dict(app.dependency_overrides)

    # The access surface rejects hmac-verified bearer sessions outright
    # (_require_authoritative_workspace_scope), so this smoke test
    # authenticates through an authoritative-verifier AuthContext (the
    # dataclass default, "override") while keeping the real database
    # session and the real endpoint logic under test.
    def override_auth_context() -> AuthContext:
        return AuthContext(
            user_id=user_id,
            role="member",
            organization_id="org-acme",
            group_ids=(),
            workspace_id="workspace-org-acme",
        )

    app.dependency_overrides[get_db] = override_real_db
    app.dependency_overrides[get_auth_context] = override_auth_context
    app.dependency_overrides.pop(get_current_user, None)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/security/access-surface")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM webdav_accounts WHERE source_uid = :source_uid"),
                {"source_uid": source_uid},
            )
            await conn.execute(
                text(
                    "DELETE FROM calendar_writeback_sources "
                    "WHERE source_uid = :source_uid"
                ),
                {"source_uid": caldav_uid},
            )
            await conn.execute(
                text(
                    "DELETE FROM connector_signal_events "
                    "WHERE event_uid = :event_uid"
                ),
                {"event_uid": event_uid},
            )
            await conn.execute(
                text(
                    "DELETE FROM security_audit_events "
                    "WHERE event_uid = :event_uid"
                ),
                {"event_uid": audit_uid},
            )
        await engine.dispose()

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["sources"]) == 2
    assert len(body["connector_events"]) == 1
    assert len(body["durable_audit_events"]) == 1
    assert source_uid not in response.text
    assert caldav_uid not in response.text
    assert event_uid not in response.text
    assert audit_uid not in response.text
    assert "account_id" not in response.text
    assert "security-smoke@example.com" not in response.text
