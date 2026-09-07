"""Regression tests for Internal Mail Smoke concurrency semantics."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mail_smoke_concurrency_queues_without_discarding_pending_runs() -> None:
    """Require FIFO-style queuing instead of replacing an already-pending smoke."""
    workflow = (REPO_ROOT / ".github/workflows/mail-smoke.yml").read_text(
        encoding="utf-8"
    )
    workflow_header = workflow.split("jobs:", 1)[0]

    assert "concurrency:" in workflow_header
    assert "group: mail-smoke-${{ github.repository }}" in workflow_header
    assert "cancel-in-progress: false" in workflow_header
    assert "queue: max" in workflow_header
    assert "cancel-in-progress: true" not in workflow_header
