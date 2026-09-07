"""Execute the release manifest contract without registry or cluster access."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = REPO_ROOT / "scripts/render_release_manifests.sh"
BACKEND_DIGEST = "sha256:" + "a" * 64
FRONTEND_DIGEST = "sha256:" + "b" * 64


def run_renderer(tmp_path: Path, backend_digest: str, frontend_digest: str) -> subprocess.CompletedProcess[str]:
    """Render checked-in manifests in an isolated directory using unit digests."""
    shutil.copytree(REPO_ROOT / "k8s", tmp_path / "k8s")
    shutil.copyfile(REPO_ROOT / "VERSION", tmp_path / "VERSION")
    return subprocess.run(
        ["bash", str(RENDER_SCRIPT), "ContextualWisdomLab", backend_digest, frontend_digest, "rendered"],
        cwd=tmp_path,
        env={"PATH": os.defpath},
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_renderer_binds_both_images_without_changing_source(tmp_path: Path) -> None:
    """Keep all pod security/configuration fields while replacing only image refs."""
    result = run_renderer(tmp_path, BACKEND_DIGEST, FRONTEND_DIGEST)
    assert result.returncode == 0, result.stderr
    for component, digest in (("backend", BACKEND_DIGEST), ("frontend", FRONTEND_DIGEST)):
        source_path = tmp_path / "k8s" / f"{component}-deployment.yaml"
        assert source_path.read_bytes() == (REPO_ROOT / "k8s" / source_path.name).read_bytes()
        expected = yaml.safe_load(source_path.read_text())
        expected["spec"]["template"]["spec"]["containers"][0]["image"] = (
            f"ghcr.io/contextualwisdomlab/ai_email_client-{component}@{digest}"
        )
        rendered = yaml.safe_load((tmp_path / "rendered" / source_path.name).read_text())
        assert rendered == expected


@pytest.mark.parametrize("invalid_digest", ["", "latest", "sha256:" + "a" * 63, "sha256:" + "A" * 64, BACKEND_DIGEST + "\ninjected", "$(touch injected)"])
@pytest.mark.parametrize("invalid_component", ["backend", "frontend"])
def test_release_renderer_rejects_either_invalid_digest_before_output(
    tmp_path: Path, invalid_digest: str, invalid_component: str
) -> None:
    """Reject absent or malformed identities before creating either manifest."""
    result = run_renderer(
        tmp_path,
        invalid_digest if invalid_component == "backend" else BACKEND_DIGEST,
        invalid_digest if invalid_component == "frontend" else FRONTEND_DIGEST,
    )
    assert result.returncode != 0
    assert "Invalid image digest" in result.stderr
    assert not (tmp_path / "rendered").exists()
    assert not (tmp_path / "injected").exists()


@pytest.mark.parametrize("failure_case", ["backend_missing", "frontend_missing", "backend_duplicate", "frontend_duplicate", "invalid_version", "existing_output"])
def test_release_renderer_preserves_prior_output_on_source_drift(
    tmp_path: Path, failure_case: str
) -> None:
    """Fail before publishing a second manifest set or overwriting prior evidence."""
    first_result = run_renderer(tmp_path, BACKEND_DIGEST, FRONTEND_DIGEST)
    assert first_result.returncode == 0, first_result.stderr
    prior_output = {path.name: path.read_bytes() for path in (tmp_path / "rendered").iterdir()}
    if failure_case == "invalid_version":
        (tmp_path / "VERSION").write_text("not-a-version\n")
    elif failure_case != "existing_output":
        component, mutation = failure_case.split("_")
        source_path = tmp_path / "k8s" / f"{component}-deployment.yaml"
        source_text = source_path.read_text()
        image_line = next(line for line in source_text.splitlines() if "image: ghcr.io/" in line)
        source_path.write_text(source_text.replace(image_line, "" if mutation == "missing" else image_line + "\n" + image_line))
    output_directory = "rendered" if failure_case == "existing_output" else "next_rendered"
    result = subprocess.run(
        ["bash", str(RENDER_SCRIPT), "ContextualWisdomLab", BACKEND_DIGEST, FRONTEND_DIGEST, output_directory],
        cwd=tmp_path,
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (tmp_path / "next_rendered").exists()
    assert {path.name: path.read_bytes() for path in (tmp_path / "rendered").iterdir()} == prior_output


def test_release_workflow_passes_separate_same_revision_artifacts() -> None:
    """Bind producer and deployment consumer without matrix output overwrites."""
    publish = yaml.safe_load((REPO_ROOT / ".github/workflows/docker-publish.yml").read_text())
    deploy = yaml.safe_load((REPO_ROOT / ".github/workflows/deploy.yml").read_text())
    upload = next(step for step in publish["jobs"]["publish_images"]["steps"] if step.get("id") == "upload_digest")
    assert "${{ matrix.component }}" in upload["with"]["name"]
    assert "${{ github.sha }}" in upload["with"]["name"]
    assert "${{ github.run_attempt }}" in upload["with"]["name"]
    assert upload["with"]["if-no-files-found"] == "error"
    steps = deploy["jobs"]["deploy"]["steps"]
    for component in ("backend", "frontend"):
        download = next(step for step in steps if step.get("id") == f"download_{component}_digest")
        assert download["with"]["name"] == upload["with"]["name"].replace("${{ matrix.component }}", component)
        assert download["with"]["digest-mismatch"] == "error"
        assert "github-token" not in download["with"]
    render = next(step for step in steps if step.get("id") == "render_manifests")
    assert "scripts/render_release_manifests.sh" in render["run"]
    apply_step = next(step for step in steps if step["name"] == "Apply to AKS")
    assert 'bash scripts/deploy_runtime_manifests.sh "$RUNNER_TEMP/release-manifests"' in apply_step["run"]


@pytest.mark.parametrize("artifact_state", ["valid", "missing_backend", "missing_frontend", "invalid_backend", "invalid_frontend"])
def test_deployment_executes_renderer_only_with_both_valid_artifacts(
    tmp_path: Path, artifact_state: str
) -> None:
    """Execute the real workflow shell before any credential or cluster step."""
    shutil.copytree(REPO_ROOT / "k8s", tmp_path / "k8s")
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(RENDER_SCRIPT, tmp_path / "scripts" / RENDER_SCRIPT.name)
    shutil.copyfile(REPO_ROOT / "VERSION", tmp_path / "VERSION")
    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()
    for component, digest in (("backend", BACKEND_DIGEST), ("frontend", FRONTEND_DIGEST)):
        digest_directory = runner_temp / f"{component}-digest"
        digest_directory.mkdir()
        if artifact_state != f"missing_{component}":
            (digest_directory / "image-digest.txt").write_text(
                "invalid\n" if artifact_state == f"invalid_{component}" else digest + "\n"
            )
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/deploy.yml").read_text())
    render_step = next(step for step in workflow["jobs"]["deploy"]["steps"] if step.get("id") == "render_manifests")
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", render_step["run"]],
        cwd=tmp_path,
        env={"PATH": os.defpath, "RUNNER_TEMP": str(runner_temp), "REPO_OWNER": "ContextualWisdomLab"},
        capture_output=True,
        text=True,
        check=False,
    )
    if artifact_state == "valid":
        assert result.returncode == 0, result.stderr
        for component, digest in (("backend", BACKEND_DIGEST), ("frontend", FRONTEND_DIGEST)):
            manifest = yaml.safe_load((runner_temp / "release-manifests" / f"{component}-deployment.yaml").read_text())
            assert manifest["spec"]["template"]["spec"]["containers"][0]["image"].endswith("@" + digest)
    else:
        assert result.returncode != 0
        assert not (runner_temp / "release-manifests").exists()
