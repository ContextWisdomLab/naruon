"""Guard hosted buyer-facing evidence retention in Application CI."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_CI_PATH = REPO_ROOT / ".github/workflows/app-ci.yml"
UPLOAD_ARTIFACT_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def test_application_ci_retains_full_product_smoke_screenshot_evidence() -> None:
    """A passing browser smoke must publish PR-head-bound PNG evidence instead of discarding it."""
    workflow_text = APPLICATION_CI_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    frontend_steps = workflow["jobs"]["frontend"]["steps"]

    smoke_indices = [
        index
        for index, step in enumerate(frontend_steps)
        if step.get("name") == "Run full product smoke"
    ]
    upload_indices = [
        index
        for index, step in enumerate(frontend_steps)
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]

    assert len(smoke_indices) == 1
    assert len(upload_indices) == 1
    assert upload_indices[0] == smoke_indices[0] + 1

    upload_step = frontend_steps[upload_indices[0]]
    assert upload_step["uses"] == f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}"
    assert upload_step["with"] == {
        "name": "naruon-full-product-smoke-${{ github.event.pull_request.number || github.run_id }}-${{ github.event.pull_request.head.sha || github.sha }}",
        "path": "/tmp/naruon-full-product-smoke-*/*.png",
        "if-no-files-found": "error",
        "retention-days": "14",
    }
