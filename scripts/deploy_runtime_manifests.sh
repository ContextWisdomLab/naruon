#!/usr/bin/env bash
# Update an existing pair only after both server dry runs and rollback baselines.
set -euo pipefail
if [[ "$#" != 1 ]]; then
  printf 'deployment_failed:invalid_arguments\n' >&2
  exit 1
fi
manifest_directory="$1"
script_directory="$(cd "$(dirname "$0")" && pwd)"
umask 077
snapshot_directory="$(mktemp -d "${RUNNER_TEMP:?}/naruon-deployment.XXXXXX")"
cleanup_snapshots() {
  local image_component
  for image_component in backend frontend; do
    rm -f "$snapshot_directory/$image_component.before.json" \
      "$snapshot_directory/$image_component.proposed.json" \
      "$snapshot_directory/$image_component.forward-patch.json" \
      "$snapshot_directory/$image_component.applied.json" \
      "$snapshot_directory/$image_component.owned.json" \
      "$snapshot_directory/$image_component.current.json"
  done
  rm -f "$snapshot_directory/command-error"
  rmdir "$snapshot_directory"
}
trap cleanup_snapshots EXIT
fail_deployment() {
  printf 'deployment_failed:%s\n' "$1" >&2
  exit 1
}
same_owned_spec() {
  jq -e -s 'length == 2 and .[0].metadata.uid == .[1].metadata.uid and .[0].spec == .[1].spec' \
    "$1" "$2" > /dev/null 2> "$snapshot_directory/command-error"
}
verify_owned_pair() {
  local image_component
  for image_component in backend frontend; do
    [[ -f "$snapshot_directory/$image_component.owned.json" ]] || continue
    kubectl get deployment "$image_component" -n naruon-dev -o json \
      > "$snapshot_directory/$image_component.current.json" 2> "$snapshot_directory/command-error" || return 1
    same_owned_spec "$snapshot_directory/$image_component.owned.json" \
      "$snapshot_directory/$image_component.current.json" || return 1
  done
}
restore_owned_pair() {
  local image_component
  # Refuse all automatic rollback if either resource has another writer's spec.
  verify_owned_pair || return 1
  for image_component in frontend backend; do
    [[ -f "$snapshot_directory/$image_component.owned.json" ]] || continue
    bash "$script_directory/restore_runtime_deployment.sh" "$image_component" \
      "$snapshot_directory/$image_component.before.json" \
      "$snapshot_directory/$image_component.owned.json" || return 1
  done
  # Two resources are not atomic; recheck both after the last restoration.
  for image_component in backend frontend; do
    [[ -f "$snapshot_directory/$image_component.owned.json" ]] || continue
    kubectl get deployment "$image_component" -n naruon-dev -o json \
      > "$snapshot_directory/$image_component.current.json" 2> "$snapshot_directory/command-error" || return 1
    same_owned_spec "$snapshot_directory/$image_component.before.json" \
      "$snapshot_directory/$image_component.current.json" || return 1
  done
}
for image_component in backend frontend; do
  kubectl rollout status "deployment/$image_component" -n naruon-dev --timeout=120s \
    > /dev/null 2> "$snapshot_directory/command-error" || fail_deployment baseline_unhealthy
  kubectl get deployment "$image_component" -n naruon-dev -o json \
    > "$snapshot_directory/$image_component.before.json" 2> "$snapshot_directory/command-error" || fail_deployment baseline_missing
  kubectl apply --dry-run=server -f "$manifest_directory/$image_component-deployment.yaml" -o json \
    > "$snapshot_directory/$image_component.proposed.json" 2> "$snapshot_directory/command-error" || fail_deployment dry_run_failed
  # Both objects must be existing, digest-pinned, and on the same observed
  # revision. The later JSON Patch uses that resourceVersion as a server-side CAS.
  jq -e -s --arg component "$image_component" '
    length == 2 and all(.[];
      .kind == "Deployment" and .metadata.name == $component and
      .metadata.namespace == "naruon-dev" and
      (.metadata.uid | type == "string" and length > 0) and
      (.metadata.resourceVersion | type == "string" and length > 0) and
      (.spec | type == "object") and
      (.spec.template.spec.containers | length > 0) and
      all((.spec.template.spec.containers + (.spec.template.spec.initContainers // []))[];
        .image | test("@sha256:[0-9a-f]{64}$"))) and
    .[0].metadata.uid == .[1].metadata.uid and
    .[0].metadata.resourceVersion == .[1].metadata.resourceVersion and
    (.[0].metadata.labels // {}) == (.[1].metadata.labels // {}) and
    ((.[0].metadata.annotations // {}) | del(."kubectl.kubernetes.io/last-applied-configuration")) ==
    ((.[1].metadata.annotations // {}) | del(."kubectl.kubernetes.io/last-applied-configuration"))
  ' "$snapshot_directory/$image_component.before.json" "$snapshot_directory/$image_component.proposed.json" \
    > /dev/null 2> "$snapshot_directory/command-error" || fail_deployment baseline_or_proposal_invalid
done
for image_component in backend frontend; do
  # Dry-run apply may add last-applied annotations. Only change spec; metadata
  # migrations need their own contract, not an incomplete spec-only rollback.
  jq -s '
    [{op:"test", path:"/metadata/uid", value:.[0].metadata.uid},
     {op:"test", path:"/metadata/resourceVersion", value:.[0].metadata.resourceVersion},
     {op:"replace", path:"/spec", value:.[1].spec}]
  ' "$snapshot_directory/$image_component.before.json" "$snapshot_directory/$image_component.proposed.json" \
    > "$snapshot_directory/$image_component.forward-patch.json" 2> "$snapshot_directory/command-error" || fail_deployment patch_preparation
  # A lost write response is ambiguous. Do not attempt blind rollback or retry.
  kubectl patch deployment "$image_component" -n naruon-dev --type=json \
    --patch-file "$snapshot_directory/$image_component.forward-patch.json" -o json \
    > "$snapshot_directory/$image_component.applied.json" 2> "$snapshot_directory/command-error" || fail_deployment write_unconfirmed
  kubectl get deployment "$image_component" -n naruon-dev -o json \
    > "$snapshot_directory/$image_component.owned.json" 2> "$snapshot_directory/command-error" || fail_deployment ownership_unconfirmed
  same_owned_spec "$snapshot_directory/$image_component.applied.json" \
    "$snapshot_directory/$image_component.owned.json" || fail_deployment ownership_changed
  if ! kubectl rollout status "deployment/$image_component" -n naruon-dev --timeout=120s \
    > /dev/null 2> "$snapshot_directory/command-error"; then
    if restore_owned_pair; then
      fail_deployment rollback_verified
    fi
    fail_deployment rollback_unconfirmed
  fi
done
verify_owned_pair || fail_deployment final_ownership_changed
printf 'deployment_verified\n'
