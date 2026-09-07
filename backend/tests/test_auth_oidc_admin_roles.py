"""Focused contracts for high-privilege OIDC session authority."""

import time

import pytest
from fastapi import HTTPException

from api import auth as auth_module
from core.config import settings


ADMIN_ROLES = (
    "system_admin",
    "platform_admin",
    "tenant_admin",
    "organization_admin",
)


def _oidc_payload(role: str) -> dict[str, object]:
    """Build a short-lived payload from the configured authoritative OIDC issuer."""
    return {
        "iss": "https://login.example.test/realms/naruon",
        "aud": "naruon-api",
        "sub": "alice",
        "role": role,
        "org": "org-acme",
        "groups": ["group-1"],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }


def _hmac_payload(role: str) -> dict[str, object]:
    """Build compatibility-session metadata without granting membership authority."""
    return {
        "ver": 1,
        "iss": auth_module.SESSION_ISSUER,
        "aud": auth_module.SESSION_AUDIENCE,
        "sub": "alice",
        "role": role,
        "org": "org-acme",
        "groups": ["group-1"],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }


@pytest.mark.parametrize("admin_role", ADMIN_ROLES)
def test_trusted_oidc_session_can_supply_admin_role(monkeypatch, admin_role: str) -> None:
    """A configured JWKS-backed IdP remains usable for authorized administrators."""
    previous_issuer_url = settings.OIDC_ISSUER_URL
    previous_client_id = settings.OIDC_CLIENT_ID
    settings.OIDC_ISSUER_URL = "https://login.example.test/realms/naruon"
    settings.OIDC_CLIENT_ID = "naruon-api"
    payload = _oidc_payload(admin_role)

    monkeypatch.setattr(auth_module, "jwks_client", object())
    monkeypatch.setattr(
        auth_module,
        "_decode_cached_oidc_session_payload",
        lambda _token: payload,
    )

    try:
        verified_payload, verifier = auth_module._verify_signed_session_token(
            "trusted-idp-token"
        )
        context = auth_module._auth_context_from_session_payload(
            verified_payload, verifier
        )
    finally:
        settings.OIDC_ISSUER_URL = previous_issuer_url
        settings.OIDC_CLIENT_ID = previous_client_id

    assert verifier == "oidc"
    assert context.role == admin_role
    assert context.organization_id == "org-acme"
    assert context.workspace_id == "workspace-org-acme"
    assert context.session_verifier == "oidc"


@pytest.mark.parametrize("admin_role", ADMIN_ROLES)
def test_hmac_compatibility_session_cannot_supply_admin_role(admin_role: str) -> None:
    """HMAC compatibility credentials never become authoritative admin membership."""
    with pytest.raises(HTTPException) as exc:
        auth_module._auth_context_from_session_payload(
            _hmac_payload(admin_role), "hmac"
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication required"
