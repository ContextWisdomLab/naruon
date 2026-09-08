"""Guard exact-head source checkout in repository-owned pull-request validation."""

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
EXPECTED_EXACT_REF = "${{ github.event.pull_request.head.sha || github.sha }}"


@pytest.mark.parametrize("workflow_path", PR_VALIDATION_WORKFLOWS)
def test_repo_local_validation_checks_out_exact_pr_head(workflow_path: str) -> None:
    """Do not report pull-request merge-tree execution as exact-head validation."""
    workflow_text = (REPO_ROOT / workflow_path).read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    checkout_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("actions/checkout@")
    ]

    assert checkout_steps
    for checkout_step in checkout_steps:
        assert checkout_step.get("with", {}).get("ref") == EXPECTED_EXACT_REF
