"""Guard repo-local PR validation on dependent stacked pull requests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PR_VALIDATION_WORKFLOWS = (
    ".github/workflows/app-ci.yml",
    ".github/workflows/bandit.yml",
    ".github/workflows/dependency-review.yml",
    ".github/workflows/docker-publish.yml",
)


@pytest.mark.parametrize("workflow_path", PR_VALIDATION_WORKFLOWS)
def test_repo_local_pr_validation_accepts_every_base_branch(workflow_path: str) -> None:
    """Require an unfiltered pull_request trigger for every stacked PR base."""
    workflow_text = (REPO_ROOT / workflow_path).read_text(encoding="utf-8")
    # BaseLoader preserves the Actions `on` key instead of YAML 1.1 boolean coercion.
    workflow_events = yaml.load(workflow_text, Loader=yaml.BaseLoader)["on"]
    assert "pull_request" in workflow_events
    pull_request_config = workflow_events["pull_request"] or {}
    assert "branches" not in pull_request_config
    assert "branches-ignore" not in pull_request_config


@pytest.mark.parametrize(
    "branch_filter",
    [
        "branches: ['**']",
        "branches: ['**', '!feature/**']",
        "branches: [develop] # '**' is only a comment",
        "branches-ignore: [archive/**]",
    ],
)
def test_stacked_trigger_guard_rejects_any_base_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, branch_filter: str
) -> None:
    """Do not encode all-base verification through mutable branch patterns."""
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(
        f"on:\n  pull_request:\n    {branch_filter}\n", encoding="utf-8"
    )
    monkeypatch.setitem(globals(), "REPO_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_repo_local_pr_validation_accepts_every_base_branch("workflow.yml")
