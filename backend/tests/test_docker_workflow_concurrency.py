"""Regression coverage for Docker workflow concurrency identity."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_pr_concurrency_isolates_reruns_from_first_attempts() -> None:
    """Keep manual reruns out of the first-attempt PR cancellation group."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    header = workflow.split("jobs:", 1)[0]
    expected_group = (
        "group: docker-publish-${{ github.repository }}-"
        "${{ github.event.pull_request.number || github.ref }}-"
        "${{ github.event_name == 'pull_request' && github.run_attempt == 1 "
        "&& 'first-attempt' || github.run_id }}"
    )
    bare_group = (
        "group: docker-publish-${{ github.repository }}-"
        "${{ github.event.pull_request.number || github.ref }}"
    )

    assert expected_group in header
    assert bare_group not in header.splitlines()
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in header


def test_docker_release_publication_queues_each_component_per_ref() -> None:
    """Serialize same-ref image publication without evicting pending release jobs."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    publish_section = workflow.split("  publish_images:\n", 1)[1].split(
        "\n  deploy_preflight:", 1
    )[0]
    expected_group = (
        "group: Build and Publish Docker Images-publish-${{ github.repository }}-"
        "${{ github.ref }}-${{ matrix.component }}"
    )
    bare_group = (
        "group: Build and Publish Docker Images-publish-${{ github.repository }}-"
        "${{ github.ref }}"
    )

    assert expected_group in publish_section
    assert bare_group not in publish_section.splitlines()
    assert "queue: max" in publish_section
    assert "cancel-in-progress: false" in publish_section
