"""Contract tests for the Keyverse credential-resolution application port."""
from __future__ import annotations

import pytest

from core.credential_resolution import (
    CredentialReference,
    CredentialResolutionUnavailable,
    ResolvedCredential,
    UnavailableCredentialResolver,
)


def _credential_reference() -> CredentialReference:
    """Return one complete value-free Keyverse credential reference."""
    return CredentialReference(
        authority="keyverse",
        tenant_id="workspace-123",
        environment_name="production",
        secret_namespace="naruon/runtime",
        secret_key="auth_session_hmac_secret",
        secret_version="v1",
        purpose_name="session-signing",
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


@pytest.mark.parametrize(
    "invalid_value",
    [
        pytest.param(None, id="none"),
        pytest.param(1, id="integer"),
        pytest.param(b"bytes", id="bytes"),
        pytest.param([], id="list"),
    ],
)
def test_credential_reference_rejects_non_string_identity_fields(
    invalid_value: object,
) -> None:
    """Runtime construction must reject non-string identity dimensions uniformly."""
    values: dict[str, object] = {
        "authority": invalid_value,
        "tenant_id": "workspace-123",
        "environment_name": "production",
        "secret_namespace": "naruon/runtime",
        "secret_key": "auth_session_hmac_secret",
        "secret_version": "v1",
        "purpose_name": "session-signing",
    }

    with pytest.raises(ValueError, match="authority"):
        CredentialReference(**values)


def test_credential_reference_repr_contains_no_secret_value() -> None:
    """Value-free references are safe to log and review."""
    rendered = repr(_credential_reference())

    assert "workspace-123" in rendered
    assert "auth_session_hmac_secret" in rendered
    assert "secret_value" not in rendered


def test_resolved_credential_repr_redacts_secret_value() -> None:
    """Resolved credential values never appear in ordinary object rendering."""
    credential = ResolvedCredential(
        secret_value="do-not-log-this-secret",
        reference=_credential_reference(),
    )

    rendered = repr(credential)

    assert "do-not-log-this-secret" not in rendered
    assert "<redacted>" in rendered
    assert "workspace-123" in rendered


def test_unavailable_resolver_fails_closed_without_fallback() -> None:
    """An unreleased Keyverse data plane cannot fall back to env or dotenv."""
    resolver = UnavailableCredentialResolver(
        reason="Keyverse workload credential API is not released"
    )

    with pytest.raises(
        CredentialResolutionUnavailable,
        match="Keyverse workload credential API is not released",
    ):
        resolver.resolve_credential(_credential_reference())
