"""Regression coverage for trusted policy selection in PR Governance."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pr-governance.yml"


def test_all_governance_events_materialize_the_live_protected_default_policy() -> None:
    """Never execute policy from an event, caller override, or stacked PR base."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "github.event.pull_request.base.sha" not in workflow
    assert "github.event.workflow_run.pull_requests[0].base.sha" not in workflow
    assert "base_sha:" not in workflow
    assert "github.event.inputs.base_sha" not in workflow
    assert "TRUSTED_BASE_SHA" not in workflow
    assert "pulls/${TRUSTED_PR_NUMBER}" not in workflow
    assert (
        'gh_api_with_retry "repos/${GITHUB_REPOSITORY}" --jq \' .default_branch\''
        .replace("' .", "'.")
    ) in workflow
    assert 'branches/${trusted_default_branch}' in workflow
    assert "--jq '.protected'" in workflow
    assert "--jq '.commit.sha'" in workflow
    assert 'Trusted default branch must be protected' in workflow
