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


def test_bandit_cancels_only_superseded_pull_request_runs() -> None:
    """Keep manual, push, and rerun scans independent while deduplicating first PR scans."""
    concurrency = _load_workflow("bandit.yml").get("concurrency")

    assert isinstance(concurrency, dict)
    assert concurrency == {
        "group": "${{ github.workflow }}-${{ github.repository }}-${{ github.event.pull_request.number || github.ref }}-${{ github.event_name == 'pull_request' && github.run_attempt == 1 && github.event.pull_request.number || github.run_id }}",
        "cancel-in-progress": "${{ github.event_name == 'pull_request' && github.run_attempt == 1 }}",
    }
