"""Unit-only kubectl double; never opens a network connection."""

import copy
import json
import os
from pathlib import Path
import sys

state_path = Path(os.environ["RESTORE_TEST_STATE"])
test_state = json.loads(state_path.read_text())
command_args = sys.argv[1:]
operation_name = command_args[0]
test_state["calls"].append(operation_name)
image_component = "backend"
desired_state = None
if "resources" in test_state:
    if operation_name == "apply":
        file_flag = "-f" if "-f" in command_args else "--filename"
        desired_state = json.loads(Path(command_args[command_args.index(file_flag) + 1]).read_text())
        image_component = desired_state["metadata"]["name"]
    else:
        image_component = command_args[2].removeprefix("deployment/")
    test_state["current"] = test_state["resources"][image_component]
    test_state["operations"].append([operation_name, image_component])
exit_code = 0
if operation_name == "get":
    if test_state["scenario"] == "missing_resource":
        exit_code = 1
    else:
        print(json.dumps(test_state["current"]))
elif operation_name == "apply" and "--dry-run=server" in command_args:
    proposed_state = copy.deepcopy(test_state["current"])
    proposed_state["spec"] = desired_state["spec"]
    proposed_state["spec"]["revisionHistoryLimit"] = 10
    proposed_state["metadata"].setdefault("annotations", {})["kubectl.kubernetes.io/last-applied-configuration"] = "unit-dry-run-annotation"
    print(json.dumps(proposed_state))
elif operation_name == "patch":
    patch_path = Path(command_args[command_args.index("--patch-file") + 1])
    patch_ops = json.loads(patch_path.read_text())
    test_state["patch_ops"] = patch_ops
    if test_state["scenario"] == "conflict":
        test_state["current"]["metadata"]["resourceVersion"] = "external-update"
    for patch_op in patch_ops:
        if patch_op["op"] == "test":
            current_value = test_state["current"]
            for path_part in patch_op["path"].strip("/").split("/"):
                current_value = current_value[path_part]
            if current_value != patch_op["value"]:
                exit_code = 1
    if not exit_code:
        replacement = next(item["value"] for item in patch_ops if item["op"] == "replace" and item["path"] == "/spec")
        test_state["current"]["spec"] = replacement
        test_state["current"]["metadata"]["resourceVersion"] = "restored-version"
        forward_patch = False
        if "resources" in test_state:
            forward_patch = image_component not in test_state["applied_components"]
            state_key = "applied_components" if forward_patch else "restored_components"
            test_state[state_key].append(image_component)
        if test_state["scenario"] == "response_lost" or (forward_patch and image_component == "frontend" and test_state["scenario"] == "frontend_response_lost"):
            exit_code = 1
        else:
            print(json.dumps(test_state["current"]))
elif operation_name == "rollout":
    if (
        "resources" in test_state and image_component == "frontend"
        and image_component in test_state["applied_components"]
        and image_component not in test_state["restored_components"]
        and test_state["scenario"] in {"frontend_rollout_failed", "backend_drift"}
    ):
        exit_code = 1
        if test_state["scenario"] == "backend_drift":
            test_state["resources"]["backend"]["spec"]["replicas"] = 99
    if test_state["scenario"] == "unhealthy_restore":
        exit_code = 1
    if test_state["scenario"] == "readback_drift":
        test_state["current"]["spec"]["replicas"] = 99
else:
    exit_code = 2
state_path.write_text(json.dumps(test_state))
raise SystemExit(exit_code)
