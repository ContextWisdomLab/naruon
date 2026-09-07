"""Run conditional restoration against a network-free kubectl unit double."""

import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("scenario", ["restored", "uid_changed", "spec_changed", "conflict", "response_lost", "unhealthy_restore", "readback_drift", "missing_resource"])
def test_restore_uses_owned_spec_and_atomic_resource_version(
    tmp_path: Path, scenario: str
) -> None:
    """Never overwrite a recreated/drifted resource or report ambiguous success."""
    before_state = {
        "kind": "Deployment",
        "metadata": {"name": "backend", "namespace": "naruon-dev", "uid": "unit-backend", "resourceVersion": "before-version"},
        "spec": {"replicas": 2, "template": {"spec": {"containers": [{"name": "backend", "image": "ghcr.io/unit/backend@sha256:" + "a" * 64}]}}},
    }
    owned_state = copy.deepcopy(before_state)
    owned_state["metadata"]["resourceVersion"] = "applied-version"
    owned_state["spec"]["replicas"] = 3
    owned_state["spec"]["template"]["spec"]["containers"][0]["image"] = "ghcr.io/unit/backend@sha256:" + "b" * 64
    current_state = copy.deepcopy(owned_state)
    current_state["metadata"]["resourceVersion"] = "controller-status-update"
    if scenario == "uid_changed":
        current_state["metadata"]["uid"] = "replacement-resource"
    if scenario == "spec_changed":
        current_state["spec"]["replicas"] = 7
    for file_name, payload in (("before.json", before_state), ("owned.json", owned_state)):
        (tmp_path / file_name).write_text(json.dumps(payload))
    state_path = tmp_path / "unit_state.json"
    state_path.write_text(json.dumps({"scenario": scenario, "current": current_state, "calls": []}))
    fake_binary = tmp_path / "kubectl"
    fixture_path = REPO_ROOT / "backend/tests/fixtures/runtime_restore_kubectl.py"
    fake_binary.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(fixture_path))} \"$@\"\n")
    fake_binary.chmod(0o700)
    jq_binary = shutil.which("jq")
    assert jq_binary, "jq is required for the deployment contract"
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/restore_runtime_deployment.sh"), "backend", str(tmp_path / "before.json"), str(tmp_path / "owned.json")],
        env={"PATH": os.pathsep.join([str(tmp_path), str(Path(jq_binary).parent), os.defpath]), "RUNNER_TEMP": str(tmp_path), "RESTORE_TEST_STATE": str(state_path)},
        capture_output=True, text=True, check=False,
    )
    final_state = json.loads(state_path.read_text())
    if scenario == "restored":
        assert result.returncode == 0, result.stderr
        assert final_state["current"]["spec"] == before_state["spec"]
        assert final_state["calls"] == ["get", "patch", "rollout", "get"]
        assert {item["path"] for item in final_state["patch_ops"] if item["op"] == "test"} >= {"/metadata/uid", "/metadata/resourceVersion"}
        assert "restore_verified:backend" in result.stdout
    else:
        assert result.returncode != 0
        assert "restore_verified:" not in result.stdout
        assert "restore_failed:" in result.stderr
        if scenario in {"uid_changed", "spec_changed", "missing_resource"}:
            assert "patch" not in final_state["calls"]


@pytest.mark.parametrize("scenario", ["deployed", "frontend_rollout_failed", "backend_drift", "frontend_response_lost"])
def test_partial_deployment_restores_only_confirmed_owned_resources(
    tmp_path: Path, scenario: str
) -> None:
    """Run the real caller and restore helper with admission-normalized objects."""
    resource_states = {}
    manifest_directory = tmp_path / "release-manifests"
    manifest_directory.mkdir()
    for image_component in ("backend", "frontend"):
        resource_states[image_component] = {
            "kind": "Deployment",
            "metadata": {"name": image_component, "namespace": "naruon-dev", "uid": "unit-" + image_component, "resourceVersion": "old-version"},
            "spec": {"replicas": 2, "revisionHistoryLimit": 10, "template": {"spec": {"containers": [{"name": image_component, "image": "ghcr.io/unit/" + image_component + "@sha256:" + "a" * 64}]}}},
        }
        desired_state = copy.deepcopy(resource_states[image_component])
        desired_state["spec"]["replicas"] = 3
        del desired_state["spec"]["revisionHistoryLimit"]
        desired_state["spec"]["template"]["spec"]["containers"][0]["image"] = "ghcr.io/unit/" + image_component + "@sha256:" + "b" * 64
        (manifest_directory / f"{image_component}-deployment.yaml").write_text(json.dumps(desired_state))
    prior_states = copy.deepcopy(resource_states)
    state_path = tmp_path / "unit_state.json"
    state_path.write_text(json.dumps({"scenario": scenario, "resources": resource_states, "calls": [], "operations": [], "applied_components": [], "restored_components": []}))
    fake_binary = tmp_path / "kubectl"
    fixture_path = REPO_ROOT / "backend/tests/fixtures/runtime_restore_kubectl.py"
    fake_binary.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(fixture_path))} \"$@\"\n")
    fake_binary.chmod(0o700)
    jq_binary = shutil.which("jq")
    assert jq_binary
    kubeconfig_path = tmp_path / "unit_kubeconfig"
    kubeconfig_path.write_text("unit-only-not-a-credential\n")
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/deploy.yml").read_text())
    apply_command = next(step["run"] for step in workflow["jobs"]["deploy"]["steps"] if step["name"] == "Apply to AKS")
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", apply_command],
        cwd=REPO_ROOT,
        env={"PATH": os.pathsep.join([str(tmp_path), str(Path(jq_binary).parent), os.defpath]), "RUNNER_TEMP": str(tmp_path), "RESTORE_TEST_STATE": str(state_path), "KUBECONFIG": str(kubeconfig_path)},
        capture_output=True, text=True, check=False,
    )
    final_state = json.loads(state_path.read_text())
    assert not kubeconfig_path.exists()
    assert final_state["applied_components"] == ["backend", "frontend"]
    for image_component in ("backend", "frontend"):
        assert final_state["resources"][image_component]["metadata"].get("annotations", {}) == prior_states[image_component]["metadata"].get("annotations", {})
    if scenario == "deployed":
        assert result.returncode == 0, result.stderr
        assert final_state["restored_components"] == []
        assert "deployment_verified" in result.stdout
    elif scenario == "frontend_rollout_failed":
        assert result.returncode != 0
        assert final_state["restored_components"] == ["frontend", "backend"]
        for image_component in ("backend", "frontend"):
            assert final_state["resources"][image_component]["spec"] == prior_states[image_component]["spec"]
        assert "rollback_verified" in result.stderr
    else:
        assert result.returncode != 0
        assert final_state["restored_components"] == []
        assert "rollback_verified" not in result.stderr
        if scenario == "backend_drift":
            assert final_state["resources"]["backend"]["spec"]["replicas"] == 99
