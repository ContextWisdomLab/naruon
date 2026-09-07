"""Regression tests for GitHub Actions concurrency boundaries."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_workflow(workflow_name: str) -> dict[str, object]:
    path = REPO_ROOT / ".github" / "workflows" / workflow_name
    assert path.exists(), f"workflow is missing: {workflow_name}"
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), (
        f"workflow must parse as a mapping: {workflow_name}"
    )
    return parsed


def test_bandit_coalesces_pr_and_protected_branch_push_scans() -> None:
    """Cancel superseded PR and push scans; keep manual dispatch unique."""
    concurrency = _load_workflow("bandit.yml").get("concurrency")

    assert isinstance(concurrency, dict)
    group = concurrency.get("group")
    assert isinstance(group, str)
    assert "bandit-security-scan-${{ github.repository }}-" in group
    assert "github.event.pull_request.number" in group
    assert "github.event_name == 'push' && format('push-{0}', github.ref_name)" in group
    assert "github.run_id" in group
    assert "github.run_attempt" not in group
    assert concurrency.get("cancel-in-progress") is True
