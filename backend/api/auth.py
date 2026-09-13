from http.client import HTTPSConnection
import hashlib
import json
import logging
import math
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException

from core.config import settings, validate_auth_session_hmac_secret_value
from core.url_validation import (
    ValidatedHTTPSURLHost,
    parse_allowed_hosts,
    validate_https_url_host_details,
)

logger = logging.getLogger(__name__)
OIDC_JWKS_TIMEOUT_SECONDS = 5
OIDC_JWKS_MAX_RESPONSE_BYTES = 1024 * 1024


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(
        self,
        address: str,
        *,
        port: int,
        server_hostname: str,
        timeout: float,
        context: ssl.SSLContext,
    ):
        super().__init__(address, port=port, timeout=timeout, context=context)
        self._server_hostname = server_hostname

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self.host, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=self._server_hostname,
        )


class _PinnedOIDCJWKSClient(PyJWKClient):
    def __init__(self, validated_url: ValidatedHTTPSURLHost):
        super().__init__(
            validated_url.normalized_url,
            cache_keys=True,
            timeout=OIDC_JWKS_TIMEOUT_SECONDS,
        )
        self._validated_url = validated_url
        self._ssl_context = ssl.create_default_context()

    def fetch_data(self) -> Any:
        parsed = urlsplit(self.uri)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        host_header = self._validated_url.hostname
        if self._validated_url.port != 443:
            host_header = f"{host_header}:{self._validated_url.port}"

        last_error: Exception | None = None
        for address in self._validated_url.addresses:
            try:
                connection = _PinnedHTTPSConnection(
                    address,
                    port=self._validated_url.port,
                    server_hostname=self._validated_url.hostname,
                    timeout=self.timeout,
                    context=self._ssl_context,
                )
                try:
                    connection.request(
                        "GET",
                        target,
                        headers={
                            **self.headers,
                            "Host": host_header,
                        },
                    )
                    response = connection.getresponse()
                    response_body = response.read(OIDC_JWKS_MAX_RESPONSE_BYTES + 1)
                    if len(response_body) > OIDC_JWKS_MAX_RESPONSE_BYTES:
                        raise ValueError("OIDC JWKS response is too large")
                    if response.status >= 400:
                        raise ValueError(
                            f"OIDC JWKS endpoint returned {response.status}"
                        )
                    jwk_set = json.loads(response_body.decode("utf-8"))
                finally:
                    connection.close()
                if self.jwk_set_cache is not None:
                    self.jwk_set_cache.put(jwk_set)
                return jwk_set
            except Exception as exc:
                last_error = exc
        raise jwt.PyJWKClientConnectionError(
            f'Fail to fetch data from the url, err: "{last_error}"'
        ) from last_error


def _build_oidc_jwks_client() -> PyJWKClient | None:
    if not settings.OIDC_JWKS_URL:
        return None
    validated_url = validate_https_url_host_details(
        "OIDC_JWKS_URL",
        settings.OIDC_JWKS_URL,
        parse_allowed_hosts(settings.ALLOWED_OIDC_HOSTS),
        "ALLOWED_OIDC_HOSTS",
    )
    return _PinnedOIDCJWKSClient(validated_url)


jwks_client = _build_oidc_jwks_client()
_cached_oidc_signing_keys: tuple[Any, ...] = ()

RoleName = Literal[
    "system_admin",
    "tenant_admin",
    "platform_admin",
    "organization_admin",
    "group_admin",
    "member",
]
SessionVerifier = Literal["hmac", "oidc", "override", "server"]
ALLOWED_ROLES: set[str] = {
    "system_admin",
    "tenant_admin",
    "platform_admin",
    "organization_admin",
    "group_admin",
    "member",
}
SYSTEM_ADMIN_ROLES = frozenset({"system_admin", "platform_admin"})
TENANT_ADMIN_ROLES = frozenset({"tenant_admin", "organization_admin"})
ADMIN_ROLES = SYSTEM_ADMIN_ROLES | TENANT_ADMIN_ROLES
SESSION_ISSUER = "naruon-control-plane"
SESSION_AUDIENCE = "naruon-api"
JWT_DECODE_REQUIRED_CLAIMS = ("exp", "iss", "aud")
MIN_SESSION_SECRET_BYTES = 32
MAX_SIGNED_SESSION_EXPIRATION_SECONDS = 12 * 60 * 60
MAX_SIGNED_SESSION_CLOCK_SKEW_SECONDS = 60
SESSION_AUTH_RATE_LIMIT_WINDOW_SECONDS = 60
SESSION_AUTH_RATE_LIMIT_MAX_FAILURES = 10
SESSION_AUTH_RATE_LIMIT_MAX_BUCKETS = 4096
_session_auth_failure_buckets: dict[str, tuple[int, float]] = {}


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: RoleName
    organization_id: str | None
    group_ids: tuple[str, ...]
    workspace_id: str
    session_verifier: SessionVerifier = field(default="override", compare=False)


def ensure_organization_access(auth_context: AuthContext, organization_id: str) -> None:
    if auth_context.organization_id != organization_id:
        raise HTTPException(
            status_code=403, detail="Resource belongs to a different organization"
        )


def is_system_admin_role(role: str) -> bool:
    return role in SYSTEM_ADMIN_ROLES


def is_tenant_admin_role(role: str) -> bool:
    return role in TENANT_ADMIN_ROLES


def is_admin_role(role: str) -> bool:
    return role in ADMIN_ROLES


async def get_auth_context(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AuthContext:
    return build_auth_context(authorization=authorization)


def build_auth_context(authorization: str | None = None) -> AuthContext:
    """
    Build runtime identity from verified signed session material.

    Client-supplied identity metadata is not authentication material. Only a
    bearer token signed by the configured control-plane HMAC secret can supply
    identity, role, organization, group, and workspace claims in the runtime
    dependency path. Endpoint tests that need fixture identities must continue to
    use explicit FastAPI dependency overrides.
    """
    payload, session_verifier = _verify_signed_session_payload(authorization)
    return _auth_context_from_session_payload(payload, session_verifier)


def _authentication_error() -> HTTPException:
    return HTTPException(status_code=401, detail="Authentication required")


def preload_oidc_jwks() -> None:
    """Populate OIDC signing keys outside the request authentication path."""
    global _cached_oidc_signing_keys
    if jwks_client is None:
        _cached_oidc_signing_keys = ()
        return
    try:
        jwk_set = jwks_client.get_jwk_set(refresh=True)
        _cached_oidc_signing_keys = tuple(jwk_set.keys)
    except Exception:
        _cached_oidc_signing_keys = ()
        logger.exception("OIDC JWKS preload failed; requests will fail closed.")


def _oidc_unverified_header(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise _authentication_error() from None
    _reject_unsupported_critical_headers(header)
    if header.get("alg") != "RS256":
        raise _authentication_error()
    key_id = header.get("kid")
    if not isinstance(key_id, str) or not key_id.strip():
        raise _authentication_error()
    return header


def _decode_cached_oidc_session_payload(token: str) -> dict[str, Any]:
    if not _cached_oidc_signing_keys:
        raise _authentication_error()
    header = _oidc_unverified_header(token)
    key_id = header["kid"].strip()

    for signing_key in _cached_oidc_signing_keys:
        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.OIDC_CLIENT_ID,
                issuer=settings.OIDC_ISSUER_URL,
                options={
                    "require": JWT_DECODE_REQUIRED_CLAIMS,
                    "verify_signature": True,
                },
            )
        except jwt.PyJWTError:
            continue
        if getattr(signing_key, "key_id", None) != key_id:
            raise _authentication_error()
        if not isinstance(payload, dict):
            raise _authentication_error()
        return payload
    raise _authentication_error()


def _reject_unsupported_critical_headers(header: dict[str, Any]) -> None:
    if "crit" in header:
        raise _authentication_error()


def _session_secret_bytes() -> bytes:
    configured = settings.AUTH_SESSION_HMAC_SECRET
    if configured is None:
        raise _authentication_error()
    secret_value = configured.get_secret_value()
    if not secret_value:
        raise _authentication_error()
    secret = secret_value.encode("utf-8")
    if len(secret) < MIN_SESSION_SECRET_BYTES:
        raise _authentication_error()
    try:
        validate_auth_session_hmac_secret_value(secret_value)
    except ValueError:
        raise _authentication_error() from None
    return secret


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _authentication_error()
    scheme, separator, token = authorization.strip().partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise _authentication_error()
    return token.strip()


def _session_auth_failure_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _prune_session_auth_failure_buckets(now: float) -> None:
    expired_keys = [
        key
        for key, (_failure_count, reset_at) in _session_auth_failure_buckets.items()
        if reset_at <= now
    ]
    for key in expired_keys:
        _session_auth_failure_buckets.pop(key, None)


def _ensure_session_auth_failure_bucket_capacity(key: str) -> None:
    if (
        key in _session_auth_failure_buckets
        or len(_session_auth_failure_buckets) < SESSION_AUTH_RATE_LIMIT_MAX_BUCKETS
    ):
        return
    _session_auth_failure_buckets.pop(next(iter(_session_auth_failure_buckets)), None)


def _reject_if_session_auth_rate_limited(token: str) -> None:
    now = time.monotonic()
    _prune_session_auth_failure_buckets(now)
    key = _session_auth_failure_key(token)
    failure_count, _reset_at = _session_auth_failure_buckets.get(
        key,
        (0, now + SESSION_AUTH_RATE_LIMIT_WINDOW_SECONDS),
    )
    if failure_count >= SESSION_AUTH_RATE_LIMIT_MAX_FAILURES:
        raise _authentication_error()


def _record_session_auth_failure(token: str) -> None:
    now = time.monotonic()
    _prune_session_auth_failure_buckets(now)
    key = _session_auth_failure_key(token)
    _ensure_session_auth_failure_bucket_capacity(key)
    failure_count, reset_at = _session_auth_failure_buckets.get(
        key,
        (0, now + SESSION_AUTH_RATE_LIMIT_WINDOW_SECONDS),
    )
    if reset_at <= now:
        failure_count = 0
        reset_at = now + SESSION_AUTH_RATE_LIMIT_WINDOW_SECONDS
    _session_auth_failure_buckets[key] = (failure_count + 1, reset_at)


def _clear_session_auth_failures(token: str) -> None:
    _session_auth_failure_buckets.pop(_session_auth_failure_key(token), None)


def _verify_signed_session_payload(
    authorization: str | None,
) -> tuple[dict[str, Any], SessionVerifier]:
    token = _extract_bearer_token(authorization)
    _reject_if_session_auth_rate_limited(token)

    try:
        payload, session_verifier = _verify_signed_session_token(token)
    except HTTPException:
        _record_session_auth_failure(token)
        raise
    _clear_session_auth_failures(token)
    return payload, session_verifier


def _verify_signed_session_token(token: str) -> tuple[dict[str, Any], SessionVerifier]:
    # OIDC RS256 verification is authoritative when configured.
    if settings.OIDC_ISSUER_URL:
        if jwks_client is None:
            raise _authentication_error()
        try:
            payload = _decode_cached_oidc_session_payload(token)
            _reject_signed_session_admin_payload(payload)
            return payload, "oidc"
        except Exception:
            raise _authentication_error() from None

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise _authentication_error() from None
    if header.get("alg") != "HS256":
        raise _authentication_error()
    _reject_unsupported_critical_headers(header)

    try:
        payload = jwt.decode(
            token,
            _session_secret_bytes(),
            algorithms=["HS256"],
            audience=SESSION_AUDIENCE,
            issuer=SESSION_ISSUER,
            options={
                "require": JWT_DECODE_REQUIRED_CLAIMS,
                "verify_signature": True,
            },
        )
    except jwt.PyJWTError:
        raise _authentication_error()
    if not isinstance(payload, dict):
        raise _authentication_error()
    _reject_signed_session_admin_payload(payload)
    return payload, "hmac"


def _reject_signed_session_admin_payload(payload: dict[str, Any]) -> None:
    role_claim = payload.get("role")
    if not isinstance(role_claim, str):
        raise _authentication_error()
    # Admin roles require explicit server-side assignment, not externally
    # supplied HMAC or enterprise OIDC session claims.
    if role_claim in ADMIN_ROLES:
        raise _authentication_error()


def _required_string_claim(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip() or not value.isascii():
        raise _authentication_error()
    return value.strip()


def _optional_string_claim(payload: dict[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or not value.isascii():
        raise _authentication_error()
    return value.strip()


def _tuple_string_claim(payload: dict[str, Any], name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _authentication_error()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or not item.isascii():
            raise _authentication_error()
        normalized.append(item.strip())
    return tuple(normalized)


def _session_audience_claim(payload: dict[str, Any]) -> tuple[str, ...]:
    value = payload.get("aud")
    if isinstance(value, str):
        if not value.strip() or not value.isascii():
            raise _authentication_error()
        return (value.strip(),)
    if isinstance(value, list | tuple):
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or not item.isascii():
                raise _authentication_error()
            normalized.append(item.strip())
        return tuple(normalized)
    raise _authentication_error()


def _validate_session_metadata(
    payload: dict[str, Any], session_verifier: SessionVerifier
) -> None:
    if session_verifier == "oidc":
        if not settings.OIDC_ISSUER_URL or not settings.OIDC_CLIENT_ID:
            raise _authentication_error()
        if payload.get("iss") != settings.OIDC_ISSUER_URL:
            raise _authentication_error()
        if settings.OIDC_CLIENT_ID not in _session_audience_claim(payload):
            raise _authentication_error()
    else:
        if payload.get("ver") != 1:
            raise _authentication_error()
        if payload.get("iss") != SESSION_ISSUER:
            raise _authentication_error()
        if payload.get("aud") != SESSION_AUDIENCE:
            raise _authentication_error()
    expires_at = payload.get("exp")
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
        raise _authentication_error()
    if not math.isfinite(expires_at):
        raise _authentication_error()
    now = time.time()
    if expires_at <= now:
        raise _authentication_error()
    if expires_at > now + MAX_SIGNED_SESSION_EXPIRATION_SECONDS:
        raise _authentication_error()
    issued_at = payload.get("iat")
    if issued_at is not None:
        if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
            raise _authentication_error()
        if not math.isfinite(issued_at):
            raise _authentication_error()
        if issued_at > now + MAX_SIGNED_SESSION_CLOCK_SKEW_SECONDS:
            raise _authentication_error()
        if expires_at <= issued_at:
            raise _authentication_error()
        if expires_at - issued_at > MAX_SIGNED_SESSION_EXPIRATION_SECONDS:
            raise _authentication_error()


def _auth_context_from_session_payload(
    payload: dict[str, Any], session_verifier: SessionVerifier
) -> AuthContext:
    _validate_session_metadata(payload, session_verifier)
    role_value = _required_string_claim(payload, "role")
    if role_value not in ALLOWED_ROLES:
        raise _authentication_error()
    role = cast(RoleName, role_value)
    if role in TENANT_ADMIN_ROLES and session_verifier not in ("server", "override"):
        raise _authentication_error()
    organization_id = _optional_string_claim(payload, "org")
    if organization_id is None:
        raise _authentication_error()
    # Workspace membership is the independently signed claim produced by the
    # verified session authority. Workspace identifiers are opaque and are not
    # derived from organization display/identity values.
    workspace_id = _required_string_claim(payload, "workspace")
    return AuthContext(
        user_id=_required_string_claim(payload, "sub"),
        role=role,
        organization_id=organization_id,
        group_ids=_tuple_string_claim(payload, "groups"),
        workspace_id=workspace_id,
        session_verifier=cast(SessionVerifier, session_verifier),
    )


async def get_current_user(
    auth_context: AuthContext = Depends(get_auth_context),
) -> str:
    return auth_context.user_id


async def get_current_workspace_id(
    auth_context: AuthContext = Depends(get_auth_context),
) -> str:
    return auth_context.workspace_id


async def get_current_user_role(
    auth_context: AuthContext = Depends(get_auth_context),
) -> str:
    return auth_context.role
