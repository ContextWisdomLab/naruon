import base64
import hashlib
import hmac
import inspect
import json
import os
import sys
import time

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import SecretStr
from api.auth import (
    AuthContext,
    SESSION_AUTH_RATE_LIMIT_MAX_FAILURES,
    _session_auth_failure_buckets,
    _auth_context_from_session_payload,
    build_auth_context,
    ensure_organization_access,
    get_auth_context,
    get_current_user,
    is_admin_role,
    is_tenant_admin_role,
)
from core.config import settings
from db.session import get_db
from main import app

TEST_DEV_AUTH_TOKEN = "test-dev-auth-token-with-32-byte-minimum"  # noqa: S105 - test-only token
WEAK_DEV_AUTH_TOKEN = "weak-token"  # noqa: S105 - test-only token
WRONG_DEV_AUTH_TOKEN = "wrong-dev-auth-token-with-32-byte-min"  # noqa: S105 - test-only token
TEST_SESSION_HMAC_SECRET = os.environ["AUTH_SESSION_HMAC_SECRET"]
WRONG_SESSION_HMAC_SECRET = "wrong-session-hmac-secret-with-32-byte-min"  # noqa: S105 - test-only secret
PUBLIC_FIXTURE_SESSION_HMAC_SECRET = "-".join(
    ("naruon", "session", "hmac", "token", "32", "byte", "minimum")
)
RUNTIME_HEADER_PARAMS = {
    "x_user_id",
    "x_user_role",
    "x_organization_id",
    "x_group_ids",
    "x_dev_auth_token",
}
PUBLIC_API_ROUTES: set[tuple[str, frozenset[str]]] = set()


class _MockResult:
    def __init__(self, obj):
        self.obj = obj

    def scalar_one_or_none(self):
        return self.obj


class _EmptyRunnerConfigSession:
    async def execute(self, query):
        return _MockResult(None)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_session_token(
    payload: dict[str, object],
    secret: str = TEST_SESSION_HMAC_SECRET,
    header: dict[str, object] | None = None,
) -> str:
    header_bytes = json.dumps(
        {"alg": "HS256", "typ": "JWT"} if header is None else header,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    header_segment = _base64url_encode(header_bytes)
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload_segment = _base64url_encode(payload_bytes)
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(
        secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{header_segment}.{payload_segment}.{_base64url_encode(signature)}"


def _legacy_signed_session_token(
    payload: dict[str, object], secret: str = TEST_SESSION_HMAC_SECRET
) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload_segment = _base64url_encode(payload_bytes)
    signature = hmac.new(
        secret.encode("utf-8"), payload_segment.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload_segment}.{_base64url_encode(signature)}"


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
def restore_auth_flags():
    previous_debug = settings.DEBUG
    previous_runtime_environment = getattr(settings, "RUNTIME_ENVIRONMENT", None)
    previous_session_hmac_secret = getattr(settings, "AUTH_SESSION_HMAC_SECRET", None)
    previous_oidc_signing_keys = sys.modules["api.auth"]._cached_oidc_signing_keys
    _session_auth_failure_buckets.clear()
    yield
    settings.DEBUG = previous_debug
    if previous_runtime_environment is not None:
        setattr(settings, "RUNTIME_ENVIRONMENT", previous_runtime_environment)
    if hasattr(settings, "AUTH_SESSION_HMAC_SECRET"):
        settings.AUTH_SESSION_HMAC_SECRET = previous_session_hmac_secret
    sys.modules["api.auth"]._cached_oidc_signing_keys = previous_oidc_signing_keys
    _session_auth_failure_buckets.clear()


def _set_runtime_environment(value: str) -> None:
    if hasattr(settings, "RUNTIME_ENVIRONMENT"):
        setattr(settings, "RUNTIME_ENVIRONMENT", value)


def _enable_local_dev_headers() -> None:
    _set_runtime_environment("local")


def _get_runner_config_without_dependency_overrides(headers: dict[str, str]):
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            return client.get("/api/runtime-config", headers=headers)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def _request_without_dependency_overrides(
    method: str, path: str, headers: dict[str, str] | None = None
):
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            return client.request(method, path, headers=headers)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def _assert_runner_config_rejects_identity_headers(headers: dict[str, str]) -> None:
    response = _get_runner_config_without_dependency_overrides(headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_private_api_routes_have_default_signed_session_dependency():
    missing_default_auth: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        route_methods = frozenset(route.methods or set())
        if (route.path, route_methods) in PUBLIC_API_ROUTES:
            continue
        route_level_dependencies = {
            dependency.dependency for dependency in route.dependencies
        }
        if get_auth_context not in route_level_dependencies:
            missing_default_auth.append(
                f"{','.join(sorted(route_methods))} {route.path}"
            )

    assert missing_default_auth == []


def test_explicit_public_routes_do_not_require_signed_session():
    for method, path in (("GET", "/"),):
        response = _request_without_dependency_overrides(method, path)
        assert response.status_code == 200, f"{method} {path}: {response.text}"


def test_metrics_route_is_not_registered_by_default():
    response = _request_without_dependency_overrides("GET", "/metrics")

    assert response.status_code == 404


@pytest.mark.parametrize("path", ("/api/emails", "/api/runtime-config"))
def test_private_api_route_rejects_missing_signed_session_by_default(path: str):
    response = _request_without_dependency_overrides("GET", path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_runtime_auth_dependencies_do_not_declare_dev_header_api_surface():
    auth_context_params = set(inspect.signature(get_auth_context).parameters)
    current_user_params = set(inspect.signature(get_current_user).parameters)

    assert RUNTIME_HEADER_PARAMS.isdisjoint(auth_context_params)
    assert RUNTIME_HEADER_PARAMS.isdisjoint(current_user_params)


def test_build_auth_context_accepts_signed_bearer_session():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())

    context = build_auth_context(authorization=f"Bearer {token}")

    assert context == AuthContext(
        user_id="alice",
        role="member",
        organization_id="org-acme",
        group_ids=("group-1", "group-2"),
        workspace_id="workspace-org-acme",
        session_verifier="hmac",
    )
    assert context.session_verifier == "hmac"


def test_build_auth_context_rejects_missing_auth():
    with pytest.raises(HTTPException) as exc:
        build_auth_context(authorization=None)

    assert exc.value.status_code == 401


def test_build_auth_context_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc:
        build_auth_context(authorization="Bearer invalid.jwt.token")

    assert exc.value.status_code == 401


def test_build_auth_context_accepts_independently_signed_workspace_membership():
    # Workspace ids are opaque membership identifiers signed by the verified
    # session authority; they are not names derived from organization ids.
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(org="org-acme", workspace="workspace-project-blue")
    )

    context = build_auth_context(authorization=f"Bearer {token}")
    assert context.organization_id == "org-acme"
    assert context.workspace_id == "workspace-project-blue"


@pytest.mark.asyncio
async def test_get_auth_context_rejects_missing_auth():
    # It should raise HTTP 401 when auth is absent instead of defaulting.
    with pytest.raises(HTTPException) as exc:
        await get_auth_context()
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_auth_context_accepts_signed_bearer_session():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())

    context = await get_auth_context(authorization=f"Bearer {token}")

    assert context == AuthContext(
        user_id="alice",
        role="member",
        organization_id="org-acme",
        group_ids=("group-1", "group-2"),
        workspace_id="workspace-org-acme",
    )
    assert context.session_verifier == "hmac"


@pytest.mark.asyncio
async def test_signed_bearer_session_uses_server_hmac_verifier():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(_session_verifier="oidc"))

    context = await get_auth_context(authorization=f"Bearer {token}")

    assert context.session_verifier == "hmac"


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_tampered_payload():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(role="member"))
    header_segment, _payload_segment, signature_segment = token.split(".")
    tampered_payload_segment = _base64url_encode(
        json.dumps(
            _valid_session_payload(role="system_admin"),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )

    with pytest.raises(HTTPException) as exc:
        authorization = (
            f"Bearer {header_segment}.{tampered_payload_segment}.{signature_segment}"
        )
        await get_auth_context(authorization=authorization)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_tampered_header():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())
    _header_segment, payload_segment, signature_segment = token.split(".")
    tampered_header_segment = _base64url_encode(
        json.dumps(
            {"alg": "HS256", "kid": "attacker", "typ": "JWT"},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )

    with pytest.raises(HTTPException) as exc:
        authorization = (
            f"Bearer {tampered_header_segment}.{payload_segment}.{signature_segment}"
        )
        await get_auth_context(authorization=authorization)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_legacy_two_segment_token():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _legacy_signed_session_token(_valid_session_payload())

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_missing_algorithm():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(), header={"typ": "JWT"})

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_none_algorithm():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(), header={"alg": "none", "typ": "JWT"}
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_rs256_algorithm():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(), header={"alg": "RS256", "typ": "JWT"}
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_decodes_with_fixed_hmac_algorithm_allowlist(
    monkeypatch,
):
    import jwt

    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())
    decode_algorithms: list[list[str]] = []
    decode_options: list[dict[str, object]] = []

    def mock_jwt_decode(*args, **kwargs):
        decode_algorithms.append(list(kwargs["algorithms"]))
        decode_options.append(dict(kwargs["options"]))
        return _valid_session_payload()

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)

    context = await get_auth_context(authorization=f"Bearer {token}")

    assert context.user_id == "alice"
    assert decode_algorithms == [["HS256"]]
    assert decode_options == [
        {"require": ("exp", "iss", "aud"), "verify_signature": True}
    ]


def test_auth_session_route_returns_server_verified_claims():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())

    response = _request_without_dependency_overrides(
        "GET",
        "/api/auth/session",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "alice",
        "organization_id": "org-acme",
        "workspace_id": "workspace-org-acme",
    }


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_unknown_critical_header():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(),
        header={
            "alg": "HS256",
            "typ": "JWT",
            "crit": ["x-custom-policy"],
            "x-custom-policy": "require-mfa",
        },
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_wrong_secret():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(), WRONG_SESSION_HMAC_SECRET)

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_non_ascii_token_segment():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization="Bearer 💥.payload.signature")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_non_ascii_claim_values():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(sub="álïcé"))

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_non_finite_expiration():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(exp=float("nan")))

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_expired_token():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(exp=int(time.time()) - 1))

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_excessive_expiration():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(exp=int(time.time()) + (13 * 60 * 60))
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_future_issued_at():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(
            iat=int(time.time()) + 120,
            exp=int(time.time()) + 300,
        )
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_issued_at_after_expiration():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(
            iat=int(time.time()) + 240,
            exp=int(time.time()) + 120,
        )
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rate_limits_repeated_invalid_token(monkeypatch):
    from api import auth as auth_module

    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    decode_attempts = 0

    def reject_header(token: str):
        nonlocal decode_attempts
        decode_attempts += 1
        raise auth_module.jwt.PyJWTError("invalid")

    monkeypatch.setattr(auth_module.jwt, "get_unverified_header", reject_header)

    for _attempt in range(SESSION_AUTH_RATE_LIMIT_MAX_FAILURES):
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization="Bearer invalid.jwt.token")
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization="Bearer invalid.jwt.token")

    assert exc.value.status_code == 401
    assert decode_attempts == SESSION_AUTH_RATE_LIMIT_MAX_FAILURES


@pytest.mark.asyncio
async def test_signed_bearer_session_failure_buckets_are_bounded(monkeypatch):
    from api import auth as auth_module

    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    monkeypatch.setattr(auth_module, "SESSION_AUTH_RATE_LIMIT_MAX_BUCKETS", 3)

    for index in range(5):
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer invalid.jwt.token{index}")
        assert exc.value.status_code == 401

    assert len(_session_auth_failure_buckets) == 3


@pytest.mark.asyncio
async def test_signed_bearer_session_requires_strong_configured_secret():
    token = _signed_session_token(_valid_session_payload())

    settings.AUTH_SESSION_HMAC_SECRET = None
    with pytest.raises(HTTPException) as missing_secret_exc:
        await get_auth_context(authorization=f"Bearer {token}")

    settings.AUTH_SESSION_HMAC_SECRET = SecretStr("weak-secret")
    with pytest.raises(HTTPException) as weak_secret_exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert missing_secret_exc.value.status_code == 401
    assert weak_secret_exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_repeated_configured_secret():
    repeated_secret = "A" * 32
    token = _signed_session_token(_valid_session_payload(), repeated_secret)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(repeated_secret)

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_public_fixture_secret():
    token = _signed_session_token(
        _valid_session_payload(), PUBLIC_FIXTURE_SESSION_HMAC_SECRET
    )
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(PUBLIC_FIXTURE_SESSION_HMAC_SECRET)

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_bearer_session_rejects_invalid_role_claim():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(role="platform_owner"))

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_subject_does_not_imply_system_admin_role():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(sub="admin", role="member"))

    context = await get_auth_context(authorization=f"Bearer {token}")

    assert context.user_id == "admin"
    assert context.role == "member"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "admin_role",
    ("system_admin", "platform_admin", "tenant_admin", "organization_admin"),
)
async def test_hmac_session_rejects_admin_role_claim(admin_role: str):
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(role=admin_role, org="org-acme")
    )

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role_claim", (["system_admin"], 123, True, None))
async def test_hmac_session_rejects_non_string_role_claim(role_claim: object):
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload(role=role_claim))

    with pytest.raises(HTTPException) as exc:
        await get_auth_context(authorization=f"Bearer {token}")

    assert exc.value.status_code == 401


def test_http_route_accepts_signed_bearer_and_ignores_forged_identity_headers():
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(_valid_session_payload())

    async def override_get_db():
        yield _EmptyRunnerConfigSession()

    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/runtime-config",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-User-Id": "attacker",
                    "X-User-Role": "system_admin",
                    "X-Organization-Id": "org-victim",
                    "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

    assert response.status_code == 200
    assert response.json()["product_name"] == "Naruon"


def test_auth_dependency_overrides_are_opt_in_by_default():
    assert get_auth_context not in app.dependency_overrides
    assert get_current_user not in app.dependency_overrides


@pytest.mark.asyncio
async def test_debug_mode_does_not_trust_unsigned_identity_headers():
    settings.DEBUG = True

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
        }
    )


def test_dev_header_trust_requires_configured_token():
    _set_runtime_environment("local")

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
        }
    )


def test_dev_header_trust_rejects_wrong_token():
    _enable_local_dev_headers()

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
            "X-Dev-Auth-Token": WRONG_DEV_AUTH_TOKEN,
        }
    )


def test_dev_auth_token_does_not_work_when_header_trust_is_disabled():
    _set_runtime_environment("local")

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
            "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
        }
    )


def test_dev_header_trust_is_rejected_in_production_environment():
    _set_runtime_environment("production")

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
            "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
        }
    )


def test_dev_header_trust_requires_strong_token():
    _set_runtime_environment("local")

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
            "X-Dev-Auth-Token": WEAK_DEV_AUTH_TOKEN,
        }
    )


@pytest.mark.asyncio
async def test_runtime_auth_rejects_dev_headers_even_when_local_flags_enabled():
    _enable_local_dev_headers()

    with pytest.raises(HTTPException) as exc:
        await get_auth_context()

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication required"


def test_http_route_rejects_dev_token_and_forged_role_even_when_flags_enabled():
    _enable_local_dev_headers()

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
            "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
        }
    )


def test_http_route_rejects_public_identity_headers_without_dev_token():
    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "attacker",
            "X-User-Role": "system_admin",
            "X-Organization-Id": "org-victim",
        }
    )


def test_runtime_auth_rejects_scoped_enterprise_role_headers():
    _enable_local_dev_headers()

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "alice",
            "X-User-Role": "group_admin",
            "X-Organization-Id": "org-acme",
            "X-Group-Ids": "group-1,group-2",
            "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
        }
    )


def test_runtime_auth_rejects_system_admin_role_headers():
    _enable_local_dev_headers()

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "root",
            "X-User-Role": "system_admin",
            "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
        }
    )


def test_admin_user_id_is_rejected_without_verified_identity_provider():
    _enable_local_dev_headers()

    _assert_runner_config_rejects_identity_headers(
        {
            "X-User-Id": "admin",
            "X-Dev-Auth-Token": TEST_DEV_AUTH_TOKEN,
        }
    )


def test_ensure_organization_access_rejects_cross_scope_resource():
    context = AuthContext(
        user_id="alice",
        role="member",
        organization_id="org-acme",
        group_ids=("group-1",),
        workspace_id="workspace-org-acme",
    )

    with pytest.raises(HTTPException) as exc:
        ensure_organization_access(context, "org-other")

    assert exc.value.status_code == 403
    assert exc.value.detail == "Resource belongs to a different organization"


def test_oidc_jwks_client_fetches_from_validated_pinned_address(monkeypatch):
    from api import auth as auth_module
    from core.url_validation import ValidatedHTTPSURLHost

    calls: list[dict[str, object]] = []

    class FakeResponse:
        status = 200

        def read(self, size: int) -> bytes:
            return b'{"keys":[]}'

    class FakeConnection:
        def __init__(
            self,
            address: str,
            *,
            port: int,
            server_hostname: str,
            timeout: float,
            context: object,
        ):
            calls.append(
                {
                    "address": address,
                    "port": port,
                    "server_hostname": server_hostname,
                    "timeout": timeout,
                    "closed": False,
                }
            )

        def request(self, method: str, target: str, headers: dict[str, str]) -> None:
            calls[-1]["method"] = method
            calls[-1]["target"] = target
            calls[-1]["host"] = headers["Host"]

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            calls[-1]["closed"] = True

    monkeypatch.setattr(auth_module, "_PinnedHTTPSConnection", FakeConnection)
    client = auth_module._PinnedOIDCJWKSClient(
        ValidatedHTTPSURLHost(
            normalized_url="https://login.example.test:8443/realms/naruon/jwks?rev=1",
            hostname="login.example.test",
            port=8443,
            addresses=("93.184.216.34",),
        )
    )

    assert client.fetch_data() == {"keys": []}
    assert calls == [
        {
            "address": "93.184.216.34",
            "port": 8443,
            "server_hostname": "login.example.test",
            "timeout": auth_module.OIDC_JWKS_TIMEOUT_SECONDS,
            "closed": True,
            "method": "GET",
            "target": "/realms/naruon/jwks?rev=1",
            "host": "login.example.test:8443",
        }
    ]


@pytest.mark.asyncio
async def test_signed_bearer_session_with_oidc(monkeypatch):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    decode_algorithms: list[list[str]] = []
    decode_options: list[dict[str, object]] = []

    def mock_jwt_decode(*args, **kwargs):
        decode_algorithms.append(list(kwargs["algorithms"]))
        decode_options.append(dict(kwargs["options"]))
        return {
            "iss": "https://login.example.test/realms/naruon",
            "aud": "naruon-api",
            "sub": "alice",
            "role": "member",
            "org": "org-acme",
            "groups": ["group-1", "group-2"],
            "workspace": "workspace-org-acme",
            "exp": int(time.time()) + 300,
            "_session_verifier": "hmac",
        }

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)

    try:
        token = _signed_session_token(
            _valid_session_payload(),
            header={"alg": "RS256", "typ": "JWT", "kid": "test-key"},
        )
        context = await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert context.user_id == "alice"
    assert context.role == "member"
    assert context.organization_id == "org-acme"
    assert context.session_verifier == "oidc"
    assert decode_algorithms == [["RS256"]]
    assert decode_options == [
        {"require": ("exp", "iss", "aud"), "verify_signature": True}
    ]


@pytest.mark.asyncio
async def test_oidc_session_accepts_tuple_audience(monkeypatch):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    def mock_jwt_decode(*args, **kwargs):
        return {
            "iss": "https://login.example.test/realms/naruon",
            "aud": ("naruon-api", "naruon-admin"),
            "sub": "alice",
            "role": "member",
            "org": "org-acme",
            "groups": ["group-1", "group-2"],
            "workspace": "workspace-org-acme",
            "exp": int(time.time()) + 300,
        }

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)

    try:
        token = _signed_session_token(
            _valid_session_payload(),
            header={"alg": "RS256", "typ": "JWT", "kid": "test-key"},
        )
        context = await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert context.session_verifier == "oidc"
    assert context.user_id == "alice"


@pytest.mark.asyncio
async def test_oidc_session_rejects_missing_client_id_after_decode(monkeypatch):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = None
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    def mock_jwt_decode(*args, **kwargs):
        return {
            "iss": "https://login.example.test/realms/naruon",
            "sub": "alice",
            "role": "member",
            "org": "org-acme",
            "groups": ["group-1", "group-2"],
            "workspace": "workspace-org-acme",
            "exp": int(time.time()) + 300,
        }

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)
    token = _signed_session_token(
        _valid_session_payload(),
        header={"alg": "RS256", "typ": "JWT", "kid": "test-key"},
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401


def test_oidc_session_metadata_rejects_missing_issuer_configuration():
    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    settings.OIDC_ISSUER_URL = None
    settings.OIDC_CLIENT_ID = "naruon-api"

    try:
        with pytest.raises(HTTPException) as exc:
            _auth_context_from_session_payload(
                {
                    "iss": "https://login.example.test/realms/naruon",
                    "aud": ["naruon-api"],
                    "sub": "alice",
                    "role": "member",
                    "org": "org-acme",
                    "groups": [],
                    "workspace": "workspace-org-acme",
                    "exp": int(time.time()) + 300,
                },
                "oidc",
            )
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id

    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ("HS256", "none"))
async def test_oidc_rejects_non_rs256_algorithm_before_decode(
    monkeypatch, algorithm: str
):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    decode_called = False

    def mock_jwt_decode(*args, **kwargs):
        nonlocal decode_called
        decode_called = True
        return {}

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)
    token = _signed_session_token(
        _valid_session_payload(),
        header={"alg": algorithm, "typ": "JWT", "kid": "test-key"},
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401
    assert decode_called is False


@pytest.mark.asyncio
async def test_oidc_rejects_key_id_that_does_not_match_verified_key(monkeypatch):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "trusted-key"
        key = "trusted_public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    def mock_jwt_decode(token, key, **kwargs):
        assert key == "trusted_public_key"
        return {
            "iss": "https://login.example.test/realms/naruon",
            "aud": "naruon-api",
            "sub": "alice",
            "role": "member",
            "org": "org-acme",
            "groups": [],
            "workspace": "workspace-org-acme",
            "exp": int(time.time()) + 300,
        }

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)
    token = _signed_session_token(
        _valid_session_payload(),
        header={"alg": "RS256", "typ": "JWT", "kid": "attacker-key"},
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_oidc_rejects_unknown_critical_header_before_decode(monkeypatch):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    decode_called = False

    def mock_jwt_decode(*args, **kwargs):
        nonlocal decode_called
        decode_called = True
        return {}

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)
    token = _signed_session_token(
        _valid_session_payload(),
        header={
            "alg": "RS256",
            "typ": "JWT",
            "kid": "test-key",
            "crit": ["x-custom-policy"],
            "x-custom-policy": "require-mfa",
        },
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401
    assert decode_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "admin_role",
    ("system_admin", "platform_admin", "tenant_admin", "organization_admin"),
)
async def test_oidc_session_rejects_admin_role_claim(monkeypatch, admin_role: str):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    def mock_jwt_decode(*args, **kwargs):
        return {
            "iss": "https://login.example.test/realms/naruon",
            "aud": "naruon-api",
            "sub": "operator",
            "role": admin_role,
            "org": None,
            "groups": [],
            "workspace": "workspace-root",
            "exp": int(time.time()) + 300,
        }

    monkeypatch.setattr(jwt, "decode", mock_jwt_decode)
    token = _signed_session_token(
        _valid_session_payload(),
        header={"alg": "RS256", "typ": "JWT", "kid": "test-key"},
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_oidc_validation_failure_does_not_fallback_to_signed_session(monkeypatch):
    import jwt

    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)

    class MockKey:
        key_id = "test-key"
        key = "public_key"

    monkeypatch.setattr("api.auth.jwks_client", object())
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", (MockKey(),))

    def reject_jwt_decode(*args, **kwargs):
        raise RuntimeError("oidc rejected")

    monkeypatch.setattr(jwt, "decode", reject_jwt_decode)
    token = _signed_session_token(
        _valid_session_payload(),
        header={"alg": "RS256", "typ": "JWT", "kid": "test-key"},
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_oidc_request_path_requires_preloaded_jwks(monkeypatch):
    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    monkeypatch.setattr("api.auth._cached_oidc_signing_keys", ())

    class NetworkFetchingJWKSClient:
        def get_signing_key_from_jwt(self, token):
            raise AssertionError("request path must not fetch JWKS")

    monkeypatch.setattr("api.auth.jwks_client", NetworkFetchingJWKSClient())
    token = _signed_session_token(
        _valid_session_payload(),
        header={"alg": "RS256", "typ": "JWT", "kid": "test-key"},
    )

    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth_context(authorization=f"Bearer {token}")
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret

    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "role, expected",
    [
        ("tenant_admin", True),
        ("organization_admin", True),
        ("system_admin", False),
        ("platform_admin", False),
        ("group_admin", False),
        ("member", False),
        ("invalid_role", False),
        ("", False),
    ],
)
def test_is_tenant_admin_role(role: str, expected: bool):
    assert is_tenant_admin_role(role) is expected


@pytest.mark.parametrize(
    "role, expected",
    [
        ("system_admin", True),
        ("platform_admin", True),
        ("tenant_admin", True),
        ("organization_admin", True),
        ("group_admin", False),
        ("member", False),
        ("invalid_role", False),
        ("", False),
    ],
)
def test_is_admin_role(role: str, expected: bool):
    assert is_admin_role(role) is expected
