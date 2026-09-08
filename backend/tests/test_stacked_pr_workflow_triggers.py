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
UPLOAD_ARTIFACT_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


@pytest.mark.parametrize("workflow_path", PR_VALIDATION_WORKFLOWS)
def test_repo_local_pr_validation_accepts_stacked_base_branches(workflow_path: str) -> None:
    """Do not silently skip exact-head checks when a PR targets a feature-stack base."""
    workflow_text = (REPO_ROOT / workflow_path).read_text(encoding="utf-8")
    # BaseLoader preserves the Actions `on` key instead of YAML 1.1 boolean coercion.
    workflow_events = yaml.load(workflow_text, Loader=yaml.BaseLoader)["on"]
    assert "pull_request" in workflow_events
    pull_request_config = workflow_events["pull_request"] or {}
    assert "branches-ignore" not in pull_request_config
    if "branches" in pull_request_config:
        branch_patterns = pull_request_config["branches"]
        assert isinstance(branch_patterns, list) and "**" in branch_patterns
        last_wildcard = len(branch_patterns) - 1 - branch_patterns[::-1].index("**")
        assert not any(pattern.startswith("!") for pattern in branch_patterns[last_wildcard + 1:])


@pytest.mark.parametrize("branch_filter", [
    "branches: ['**', '!feature/**']",
    "branches: [develop] # '**' is only a comment",
])
def test_stacked_trigger_guard_rejects_excluded_bases(tmp_path, monkeypatch, branch_filter):
    """A wildcard comment or later exclusion must not masquerade as all-base CI."""
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(f"on:\n  pull_request:\n    {branch_filter}\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "REPO_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_repo_local_pr_validation_accepts_stacked_base_branches("workflow.yml")


def test_application_ci_retains_full_product_smoke_screenshot_evidence() -> None:
    """A passing browser smoke must publish its PNG evidence instead of discarding it."""
    workflow_text = (REPO_ROOT / ".github/workflows/app-ci.yml").read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    frontend_steps = workflow["jobs"]["frontend"]["steps"]
    upload_steps = [
        step
        for step in frontend_steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]

    assert len(upload_steps) == 1
    upload_step = upload_steps[0]
    assert upload_step["uses"] == f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}"
    assert upload_step["with"] == {
        "name": "naruon-full-product-smoke-${{ github.event.pull_request.number || github.run_id }}-${{ github.sha }}",
        "path": "/tmp/naruon-full-product-smoke/*.png",
        "if-no-files-found": "error",
        "retention-days": "14",
    }
