"""Contract tests for the Keyverse credential-resolution application port."""
from __future__ import annotations

import pytest

from core.credential_resolution import (
    CredentialReference,
    CredentialResolutionUnavailable,
    UnavailableCredentialResolver,
)


def test_credential_reference_rejects_blank_identity_fields() -> None:
    """Credential references must bind every authorization identity dimension."""
    for field_name in (
        "authority",
        "tenant_id",
        "environment_name",
        "secret_namespace",
        "secret_key",
        "secret_version",
        "purpose_name",
    ):
        values = {
            "authority": "keyverse",
            "tenant_id": "workspace-123",
            "environment_name": "production",
            "secret_namespace": "naruon/runtime",
            "secret_key": "auth_session_hmac_secret",
            "secret_version": "v1",
            "purpose_name": "session-signing",
        }
        values[field_name] = "  "
        with pytest.raises(ValueError, match=field_name):
            CredentialReference(**values)


def test_credential_reference_repr_contains_no_secret_value() -> None:
    """Value-free references are safe to log and review."""
    reference = CredentialReference(
        authority="keyverse",
        tenant_id="workspace-123",
        environment_name="production",
        secret_namespace="naruon/runtime",
        secret_key="auth_session_hmac_secret",
        secret_version="v1",
        purpose_name="session-signing",
    )

    rendered = repr(reference)

    assert "workspace-123" in rendered
    assert "auth_session_hmac_secret" in rendered
    assert "secret_value" not in rendered


def test_unavailable_resolver_fails_closed_without_fallback() -> None:
    """An unreleased Keyverse data plane cannot fall back to env or dotenv."""
    resolver = UnavailableCredentialResolver(
        reason="Keyverse workload credential API is not released"
    )
    reference = CredentialReference(
        authority="keyverse",
        tenant_id="workspace-123",
        environment_name="production",
        secret_namespace="naruon/runtime",
        secret_key="encryption_key",
        secret_version="v1",
        purpose_name="data-encryption",
    )

    with pytest.raises(
        CredentialResolutionUnavailable,
        match="Keyverse workload credential API is not released",
    ):
        resolver.resolve_credential(reference)
