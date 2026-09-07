#!/usr/bin/env bash
# Restore one known existing deployment, never delete or force-undo a resource.
set -euo pipefail
if [[ "$#" != 3 || ( "$1" != backend && "$1" != frontend ) ]]; then
  printf 'restore_failed:invalid_arguments\n' >&2
  exit 1
fi
image_component="$1"
before_snapshot="$2"
owned_snapshot="$3"
umask 077
restore_directory="$(mktemp -d "${RUNNER_TEMP:?}/naruon-restore.XXXXXX")"
trap 'rm -f "$restore_directory/current.json" "$restore_directory/patch.json" "$restore_directory/restored.json" "$restore_directory/command-error"; rmdir "$restore_directory"' EXIT

fail_restore() {
  printf 'restore_failed:%s:%s\n' "$image_component" "$1" >&2
  exit 1
}

if ! kubectl get deployment "$image_component" -n naruon-dev -o json \
  > "$restore_directory/current.json" 2> "$restore_directory/command-error"; then
  fail_restore read_current
fi
# Compare server-normalized post-apply spec, not the client manifest. Status-only
# controller updates may advance resourceVersion without changing owned spec.
if ! jq -e -s --arg component "$image_component" '
  length == 3 and
  all(.[]; .kind == "Deployment" and .metadata.name == $component and
      .metadata.namespace == "naruon-dev" and
      (.metadata.uid | type == "string" and length > 0) and
      (.metadata.resourceVersion | type == "string" and length > 0) and
      (.spec | type == "object")) and
  .[0].metadata.uid == .[1].metadata.uid and
  .[1].metadata.uid == .[2].metadata.uid and .[1].spec == .[2].spec
' "$before_snapshot" "$owned_snapshot" "$restore_directory/current.json" \
  > /dev/null 2> "$restore_directory/command-error"; then
  fail_restore ownership_changed
fi
if ! jq -s '
  [{op:"test", path:"/metadata/uid", value:.[1].metadata.uid},
   {op:"test", path:"/metadata/resourceVersion", value:.[1].metadata.resourceVersion},
   {op:"replace", path:"/spec", value:.[0].spec}]
' "$before_snapshot" "$restore_directory/current.json" \
  > "$restore_directory/patch.json" 2> "$restore_directory/command-error"; then
  fail_restore patch_preparation
fi
if ! kubectl patch deployment "$image_component" -n naruon-dev --type=json \
  --patch-file "$restore_directory/patch.json" -o json \
  > "$restore_directory/restored.json" 2> "$restore_directory/command-error"; then
  # Includes optimistic conflict and an ambiguous response; never retry blindly.
  fail_restore patch_unconfirmed
fi
if ! kubectl rollout status "deployment/$image_component" -n naruon-dev --timeout=120s \
  > /dev/null 2> "$restore_directory/command-error"; then
  fail_restore rollout_unconfirmed
fi
if ! kubectl get deployment "$image_component" -n naruon-dev -o json \
  > "$restore_directory/restored.json" 2> "$restore_directory/command-error"; then
  fail_restore readback_unconfirmed
fi
if ! jq -e -s '
  length == 2 and .[0].metadata.uid == .[1].metadata.uid and .[0].spec == .[1].spec
' "$before_snapshot" "$restore_directory/restored.json" \
  > /dev/null 2> "$restore_directory/command-error"; then
  fail_restore readback_changed
fi
printf 'restore_verified:%s\n' "$image_component"
