"""Regression coverage for trusted policy selection in PR Governance."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pr-governance.yml"


def test_all_governance_events_materialize_the_live_protected_default_policy() -> None:
    """Keep PR metadata separate from the executable governance policy source."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "github.event.pull_request.base.sha" not in workflow
    assert "github.event.workflow_run.pull_requests[0].base.sha" not in workflow
    assert "base_sha:" not in workflow
    assert "github.event.inputs.base_sha" not in workflow
    assert "TRUSTED_BASE_SHA" not in workflow

    # The live PR base is metadata only. A stacked feature base must never become
    # the archive from which the write-capable governance script executes.
    assert (
        'gh_api_with_retry "repos/${GITHUB_REPOSITORY}/pulls/${TRUSTED_PR_NUMBER}" '
        "--jq '.base.sha'"
    ) in workflow
    assert "evaluated_pr_base_sha" in workflow
    assert 'trusted_ref="$evaluated_pr_base_sha"' not in workflow

    # The executable policy always comes from the repository's live protected
    # default ref, resolved independently of the PR target branch.
    assert "defaultBranchRef" in workflow
    assert "--jq '.data.repository.defaultBranchRef.name'" in workflow
    assert 'branches/${trusted_default_ref}' in workflow
    assert "--jq '.protected'" in workflow
    assert "--jq '.commit.sha'" in workflow
    assert "Trusted default branch must be protected" in workflow
    assert 'trusted_ref="$(gh_api_with_retry "repos/${GITHUB_REPOSITORY}/branches/' in workflow
