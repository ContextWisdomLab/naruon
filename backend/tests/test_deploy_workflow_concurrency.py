"""Regression tests for AKS deploy workflow concurrency semantics."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deploy_concurrency_queues_without_cancelling_in_progress_applies() -> None:
    """Serialize AKS applies; never cancel an in-progress deploy publication."""
    workflow = (REPO_ROOT / ".github/workflows/deploy.yml").read_text(
        encoding="utf-8"
    )
    workflow_header = workflow.split("jobs:", 1)[0]

    assert "concurrency:" in workflow_header
    assert "group: deploy-aks-${{ github.repository }}" in workflow_header
    assert "cancel-in-progress: false" in workflow_header
    assert "queue: max" in workflow_header
    assert "cancel-in-progress: true" not in workflow_header
