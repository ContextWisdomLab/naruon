"""Regression tests for system-level roles in source access policies."""

import pytest

from api.auth import AuthContext
from api.security import _access_request, _source_policy
from services.access_policy import evaluate_access


@pytest.mark.parametrize("role", ["system_admin", "platform_admin"])
def test_source_policy_allows_system_admin_roles_in_current_organization(role):
    auth_context = AuthContext(
        user_id="global-admin",
        role=role,
        organization_id="org-acme",
        group_ids=(),
        workspace_id="workspace-org-acme",
    )
    policy = _source_policy(
        auth_context,
        owner_id="source-owner",
        organization_id="org-acme",
        workspace_id="workspace-org-acme",
        writeback_enabled=False,
    )

    decision = evaluate_access(_access_request(auth_context), policy)

    assert decision.allowed is True
    assert decision.reason == "allowed"


@pytest.mark.parametrize("role", ["system_admin", "platform_admin"])
def test_source_policy_keeps_system_admin_roles_inside_current_organization(role):
    auth_context = AuthContext(
        user_id="global-admin",
        role=role,
        organization_id="org-acme",
        group_ids=(),
        workspace_id="workspace-org-acme",
    )
    policy = _source_policy(
        auth_context,
        owner_id="source-owner",
        organization_id="org-rival",
        workspace_id="workspace-org-acme",
        writeback_enabled=False,
    )

    decision = evaluate_access(_access_request(auth_context), policy)

    assert decision.allowed is False
    assert decision.reason == "organization_denied"


@pytest.mark.parametrize("role", ["system_admin", "platform_admin"])
def test_source_policy_does_not_delegate_orgless_legacy_sources(role):
    """Missing organization identity must not become an implicit admin delegation."""
    auth_context = AuthContext(
        user_id="global-admin",
        role=role,
        organization_id=None,
        group_ids=(),
        workspace_id="workspace-legacy",
    )
    policy = _source_policy(
        auth_context,
        owner_id="source-owner",
        organization_id=None,
        workspace_id="workspace-legacy",
        writeback_enabled=False,
    )

    decision = evaluate_access(_access_request(auth_context), policy)

    assert decision.allowed is False
    assert decision.reason == "ownership_denied"
