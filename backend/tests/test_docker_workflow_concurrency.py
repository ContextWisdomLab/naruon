"""Regression coverage for Docker workflow concurrency identity."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_pr_concurrency_isolates_reruns_from_first_attempts() -> None:
    """Keep manual reruns out of the first-attempt PR cancellation group."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    header = workflow.split("jobs:", 1)[0]

    assert (
        "docker-publish-${{ github.repository }}-${{ github.event_name == 'pull_request' && github.run_attempt == 1 && github.event.pull_request.number || github.run_id }}"
        in header
    )
    assert (
        "cancel-in-progress: ${{ github.event_name == 'pull_request' && github.run_attempt == 1 }}"
        in header
    )
    assert "github.event.pull_request.number || github.ref" not in header
