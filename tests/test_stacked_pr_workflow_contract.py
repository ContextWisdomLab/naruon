"""Regression coverage for governed checks on stacked pull requests."""

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
GOVERNED_PULL_REQUEST_WORKFLOWS = (
    "app-ci.yml",
    "bandit.yml",
    "dependency-review.yml",
    "docker-publish.yml",
)


def test_governed_pull_request_workflows_accept_stacked_base_branches() -> None:
    """Required repository checks must run for every PR base, including stacks."""
    for name in GOVERNED_PULL_REQUEST_WORKFLOWS:
        workflow = (REPO_ROOT / ".github" / "workflows" / name).read_text()
        pull_request_trigger = re.search(
            r"(?ms)^  pull_request:\s*$\n(?P<body>(?:^    .*$\n)*)",
            workflow,
        )
        assert pull_request_trigger is not None, f"{name} must run on pull_request"
        assert "branches:" not in pull_request_trigger.group("body"), (
            f"{name} must not exclude stacked PR base branches"
        )
