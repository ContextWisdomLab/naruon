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
    """Keep all image components inside the reusable release boundary."""
    release_workflow = (
        REPO_ROOT / ".github/workflows/docker-release-images.yml"
    ).read_text(encoding="utf-8")
    publish_section = release_workflow.split("jobs:\n", 1)[1]

    assert "workflow_call:" in release_workflow
    assert "matrix.component" in publish_section
    assert "push: true" in publish_section
    assert "sbom: true" in publish_section
    assert "provenance: true" in publish_section
    assert "packages: write" in release_workflow
    assert "password: ${{ secrets.GITHUB_TOKEN }}" in publish_section


def test_docker_release_publication_serializes_whole_image_set_per_ref() -> None:
    """Hold one same-ref release lock until every component publication completes."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    publish_section = workflow.split("  publish_images:\n", 1)[1].split(
        "\n  deploy_preflight:", 1
    )[0]
    expected_group = (
        "group: Build and Publish Docker Images-publish-set-"
        "${{ github.repository }}-${{ github.ref }}"
    )

    assert "uses: ./.github/workflows/docker-release-images.yml" in publish_section
    assert expected_group in publish_section
    assert "queue: max" in publish_section
    assert "cancel-in-progress: false" in publish_section
    assert "packages: write" in publish_section
    assert "matrix.component" not in publish_section


def test_release_serialization_decision_and_operability_docs_match_active_pr() -> None:
    """Keep release-set semantics documented without claiming protected acceptance."""
    adr = (
        REPO_ROOT / "docs/adr/0005-whole-release-publication-serialization.md"
    ).read_text(encoding="utf-8")
    adr_index = (REPO_ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    operations = (
        REPO_ROOT / "docs/operations/release-deployment-architecture.md"
    ).read_text(encoding="utf-8")

    assert "**Status:** Proposed" in adr
    assert "PR #1621; not protected-branch authority" in adr
    assert "queue: max" in adr
    assert "cancel-in-progress: false" in adr
    assert "docker-release-images.yml" in adr
    assert "ADR-0005" in adr_index
    assert "PR #1621 `ACTIVE-PR`; no protected-release acceptance yet" in adr_index
    assert "active-PR evidence, not protected-branch authority" in operations
    assert "docker-release-images.yml" in operations
    assert "A failed image publication blocks deployment" in operations
