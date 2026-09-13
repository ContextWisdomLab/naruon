"""Regression tests for stable public Noema failure codes."""

import pytest

from services import noema_agent
from services.noema_agent import run_noema_agent
from services.orchestrator_gateway import OrchestratorGateway


async def _resolved_gateway(*_args, **_kwargs):
    return OrchestratorGateway(
        base_url="https://orchestrator.internal/v1",
        inference_token="orch-token",
    )


async def _noop_closer() -> None:
    return None


@pytest.mark.asyncio
async def test_run_noema_agent_codes_missing_optional_runtime(monkeypatch):
    async def _build_without_runtime(_gateway):
        return None, _noop_closer

    monkeypatch.setattr(noema_agent, "resolve_orchestrator_gateway", _resolved_gateway)
    monkeypatch.setattr(noema_agent, "build_noema_agent", _build_without_runtime)

    result = await run_noema_agent(
        object(),
        user_id="user-1",
        organization_id="org-1",
        workspace_id="workspace-1",
        prompt="hello",
    )

    assert result.status == "unavailable"
    assert result.error_code == "pydantic_ai_unavailable"


@pytest.mark.asyncio
async def test_run_noema_agent_codes_agent_run_failure(monkeypatch):
    class _FailingAgent:
        async def run(self, _prompt, *, deps):
            deps.tool_calls.append("before_failure")
            raise RuntimeError("provider failed")

    async def _build_failing_agent(_gateway):
        return _FailingAgent(), _noop_closer

    monkeypatch.setattr(noema_agent, "resolve_orchestrator_gateway", _resolved_gateway)
    monkeypatch.setattr(noema_agent, "build_noema_agent", _build_failing_agent)

    result = await run_noema_agent(
        object(),
        user_id="user-1",
        organization_id="org-1",
        workspace_id="workspace-1",
        prompt="hello",
    )

    assert result.status == "error"
    assert result.error_code == "noema_agent_run_failed"
    assert result.tool_calls == ("before_failure",)
