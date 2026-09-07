"""Regression contracts for independently deployable OCI runtime images.

The release workflow publishes three compatibility surfaces: a backend image, a
frontend image, and the legacy combined ``naruon`` image.  Each matrix entry must
select an explicit Docker build target so a future Dockerfile stage reorder
cannot silently turn the backend artifact back into the combined runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docker-publish.yml"


def _component_entry(workflow: dict[object, object], job_name: str, component: str) -> dict[str, object]:
    """Return one named image-matrix entry from a release workflow job."""
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_name]
    assert isinstance(job, dict)
    strategy = job["strategy"]
    assert isinstance(strategy, dict)
    matrix = strategy["matrix"]
    assert isinstance(matrix, dict)
    entries = matrix["include"]
    assert isinstance(entries, list)
    matches = [entry for entry in entries if entry.get("component") == component]
    assert len(matches) == 1, f"expected exactly one {component!r} matrix entry"
    entry = matches[0]
    assert isinstance(entry, dict)
    return entry


def test_release_workflow_selects_explicit_independent_runtime_targets() -> None:
    """Publish backend/frontend artifacts from explicit independent stages."""
    workflow_text = DOCKER_PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    assert isinstance(workflow, dict)

    for job_name in ("pull_request_image_validation", "publish_images"):
        backend = _component_entry(workflow, job_name, "backend")
        frontend = _component_entry(workflow, job_name, "frontend")
        combined = _component_entry(workflow, job_name, "naruon")

        assert backend["dockerfile"] == "Dockerfile"
        assert backend["target"] == "backend-runtime"
        assert frontend["dockerfile"] == "frontend/Dockerfile"
        assert frontend["target"] == "frontend-runtime"
        assert combined["dockerfile"] == "Dockerfile"
        assert combined["target"] == "combined-runtime"

    assert workflow_text.count("target: ${{ matrix.target }}") == 2

    root_dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "FROM backend-runtime AS combined-runtime" in root_dockerfile
    assert " AS frontend-runtime" in frontend_dockerfile.splitlines()[0]


def test_frontend_command_executes_next_without_an_outer_shell() -> None:
    """Keep runtime PORT expansion while replacing the sole shell with Next."""
    frontend_dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    command_lines = [line for line in frontend_dockerfile.splitlines() if line.startswith("CMD ")]
    assert len(command_lines) == 1
    command_args = json.loads(command_lines[0].removeprefix("CMD "))
    assert command_args == [
        "sh",
        "-c",
        'exec ./node_modules/.bin/next start --hostname 0.0.0.0 --port "${PORT:-3000}"',
    ]
