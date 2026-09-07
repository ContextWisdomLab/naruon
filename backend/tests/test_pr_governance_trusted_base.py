"""Regression coverage for trusted-base selection in PR Governance."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pr-governance.yml"


def test_automatic_governance_events_materialize_the_live_pr_base() -> None:
    """Keep queued automatic events from executing stale base-branch policy."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "github.event.pull_request.base.sha" not in workflow
    assert "github.event.workflow_run.pull_requests[0].base.sha" not in workflow
    assert "github.event.inputs.base_sha || ''" in workflow
    assert (
        'gh_api_with_retry "repos/${GITHUB_REPOSITORY}/pulls/${TRUSTED_PR_NUMBER}" '
        "--jq '.base.sha'"
    ) in workflow
