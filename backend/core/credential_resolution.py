"""Application port for resolving credentials from an external authority.

The concrete Keyverse transport adapter intentionally does not live here yet.
Consumers can depend on this value-free contract while the owner publishes an
immutable workload credential-resolution API and release artifact.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Protocol


@dataclass(frozen=True)
class CredentialReference:
    """Identify one credential without carrying its secret value."""

    authority: str
    tenant_id: str
    environment_name: str
    secret_namespace: str
    secret_key: str
    secret_version: str
    purpose_name: str

    def __post_init__(self) -> None:
        """Reject references that cannot be authorized unambiguously."""
        for reference_field in fields(self):
            field_value = getattr(self, reference_field.name)
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(
                    f"{reference_field.name} must be a non-blank credential reference field"
                )


@dataclass(frozen=True, repr=False)
class ResolvedCredential:
    """Hold one resolved secret while keeping its value out of repr output."""

    secret_value: str
    reference: CredentialReference

    def __repr__(self) -> str:
        """Render only value-free identity metadata."""
        return f"ResolvedCredential(reference={self.reference!r}, secret_value=<redacted>)"


class CredentialResolutionUnavailable(RuntimeError):
    """Raised when the configured credential authority cannot resolve safely."""


class CredentialResolver(Protocol):
    """Resolve one credential reference through an external authority."""

    def resolve_credential(self, reference: CredentialReference) -> ResolvedCredential:
        """Resolve one credential or fail closed without local fallback."""
        pass


@dataclass(frozen=True)
class UnavailableCredentialResolver:
    """Fail closed until an immutable Keyverse workload adapter is available."""

    reason: str

    def resolve_credential(self, reference: CredentialReference) -> ResolvedCredential:
        """Reject resolution instead of consulting environment or dotenv state."""
        del reference
        raise CredentialResolutionUnavailable(self.reason)
