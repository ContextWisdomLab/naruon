"""Guard repo-local PR validation on dependent stacked pull requests."""

from __future__ import annotations

from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PR_VALIDATION_WORKFLOWS = (
    ".github/workflows/app-ci.yml",
    ".github/workflows/bandit.yml",
    ".github/workflows/dependency-review.yml",
    ".github/workflows/docker-publish.yml",
)


def _pull_request_event_block(workflow_text: str) -> str:
    """Return the top-level pull_request event block from workflow source."""
    event = re.search(
        r"(?ms)^  pull_request:(?P<body>.*?)(?=^  [A-Za-z_][A-Za-z0-9_-]*:|\Z)",
        workflow_text,
    )
    assert event is not None, "workflow must declare a pull_request trigger"
    return event.group(0)


@pytest.mark.parametrize("workflow_path", PR_VALIDATION_WORKFLOWS)
def test_repo_local_pr_validation_accepts_stacked_base_branches(workflow_path: str) -> None:
    """Do not silently skip exact-head checks when a PR targets a feature-stack base."""
    workflow_text = (REPO_ROOT / workflow_path).read_text(encoding="utf-8")
    pull_request_block = _pull_request_event_block(workflow_text)

    assert "branches-ignore:" not in pull_request_block
    if "branches:" in pull_request_block:
        assert re.search(r"(?m)(?:^|[\[,\s])['\"]?\*\*['\"]?(?:[\],\s]|$)", pull_request_block), (
            f"{workflow_path} filters pull_request bases without an all-branch '**' pattern"
        )
