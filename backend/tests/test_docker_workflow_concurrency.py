"""Regression coverage for Docker workflow concurrency identity."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_releases_keep_pending_runs_in_a_shared_destination() -> None:
    """Do not silently restore the single-pending default for release writers."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    )
    concurrency = workflow["concurrency"]
    assert concurrency.get("queue") == (
        "${{ github.event_name == 'pull_request' && 'single' || 'max' }}"
    )
    assert "|| 'release-ghcr-aks' }}" in concurrency["group"]
    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


def test_docker_pr_concurrency_isolates_reruns_from_first_attempts() -> None:
    """Keep manual reruns out of the first-attempt PR cancellation group."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    header = workflow.split("jobs:", 1)[0]
    expected_group = (
        "group: docker-publish-${{ github.repository }}-"
        "${{ github.event_name == 'pull_request' && format('{0}-{1}', "
        "github.event.pull_request.number, github.run_attempt == 1 "
        "&& 'first-attempt' || github.run_id) || 'release-ghcr-aks' }}"
    )
    bare_group = (
        "group: docker-publish-${{ github.repository }}-"
        "${{ github.event.pull_request.number || github.ref }}"
    )

    assert expected_group in header
    assert bare_group not in header.splitlines()
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in header
