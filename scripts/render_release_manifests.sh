#!/usr/bin/env bash
# Render only the two checked-in runtime manifests; never contact a cluster.
set -euo pipefail

if [[ "$#" != 4 ]]; then
  printf 'Expected repository owner, backend digest, frontend digest, output directory\n' >&2
  exit 1
fi
repo_owner="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
backend_digest="$2"
frontend_digest="$3"
output_directory="$4"
if [[ ! "$repo_owner" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  printf 'Invalid repository owner\n' >&2
  exit 1
fi
for image_digest in "$backend_digest" "$frontend_digest"; do
  if [[ ! "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    printf 'Invalid image digest\n' >&2
    exit 1
  fi
done
release_version="$(cat VERSION)"
if [[ ! "$release_version" =~ ^[0-9]+[.][0-9]+[.][0-9]+([-.][0-9A-Za-z.-]+)?$ ]]; then
  printf 'Invalid release version\n' >&2
  exit 1
fi
# Validate both sources before writing either result; preserve source manifests.
for image_component in backend frontend; do
  image_pattern="^([[:space:]]*image: )ghcr[.]io/[A-Za-z0-9._-]+/ai_email_client-${image_component}:REPLACE_ME_VERSION$"
  match_count="$(grep -Ec "$image_pattern" "k8s/${image_component}-deployment.yaml" || true)"
  if [[ "$match_count" != 1 ]]; then
    printf 'Expected one runtime image placeholder per manifest\n' >&2
    exit 1
  fi
done
mkdir "$output_directory"
for image_component in backend frontend; do
  image_digest="$backend_digest"
  if [[ "$image_component" == frontend ]]; then image_digest="$frontend_digest"; fi
  image_pattern="^([[:space:]]*image: )ghcr[.]io/[A-Za-z0-9._-]+/ai_email_client-${image_component}:REPLACE_ME_VERSION$"
  sed -E "s#${image_pattern}#\1ghcr.io/${repo_owner}/ai_email_client-${image_component}@${image_digest}#" \
    "k8s/${image_component}-deployment.yaml" > "$output_directory/${image_component}-deployment.yaml"
done
