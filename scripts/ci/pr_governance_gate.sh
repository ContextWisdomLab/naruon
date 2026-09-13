#!/usr/bin/env bash
set -euo pipefail

# Inside Actions, ignore PATH entries prepended via GITHUB_PATH by earlier
# steps so gh/jq/coreutils resolve from the runner's system directories only.
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
fi

COMMENT_MARKER='<!-- pr-governance:metadata-gate -->'
CHECK_NAME='metadata-only gate evaluation'
REVIEW_BOT_LOGIN_PATTERN='coderabbit|github-code-quality'

PR_NUMBER="${DIRECT_PR_NUMBER:-${TARGET_PR_NUMBER:-${WORKFLOW_RUN_PR_NUMBER:-${CHECK_RUN_PR_NUMBER:-}}}}"
if [ -z "$PR_NUMBER" ]; then
  printf 'No pull request number is available for event %s; nothing to evaluate.\n' "${EVENT_NAME:-unknown}"
  exit 0
fi
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  # Do not echo the value: a crafted PR number could smuggle workflow commands
  # into the run log.
  printf 'Pull request number is not a positive integer; refusing to evaluate.\n'
  exit 1
fi

OWNER="${GITHUB_REPOSITORY%/*}"
REPO="${GITHUB_REPOSITORY#*/}"
BLOCKERS=()
WAITING=()
PR_CHECKS_ERROR_FILE="$(mktemp)"
ISSUE_COMMENTS_ERROR_FILE="$(mktemp)"
REVIEW_COMMENTS_ERROR_FILE="$(mktemp)"
OPENCODE_REVIEWS_ERROR_FILE="$(mktemp)"
COMMIT_STATUS_ERROR_FILE="$(mktemp)"
RUN_DETAILS_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID:-unknown}"

cleanup_temp_files() {
  rm -f \
    "$PR_CHECKS_ERROR_FILE" \
    "$ISSUE_COMMENTS_ERROR_FILE" \
    "$REVIEW_COMMENTS_ERROR_FILE" \
    "$OPENCODE_REVIEWS_ERROR_FILE" \
    "$COMMIT_STATUS_ERROR_FILE"
}

trap cleanup_temp_files EXIT

publish_gate_error_check() {
  # Fail closed: replace any previously published gate result so a transient
  # evaluation error cannot leave a stale success pinned to the head.
  [ -n "${HEAD_SHA:-}" ] || return 0
  if [ -z "${CHECK_RUNS:-}" ]; then
    CHECK_RUNS='{"check_runs":[]}'
  fi
  publish_gate_check \
    completed \
    failure \
    'PR governance metadata gate errored' \
    "Gate evaluation failed unexpectedly for PR ${PR_NUMBER}; see the workflow run log." || true
}

trap publish_gate_error_check ERR

add_blocker() {
  BLOCKERS+=("$1")
}

add_waiting() {
  WAITING+=("$1")
}

read_pr_metadata_with_merge_state_retry() {
  local attempt retry_delay

  for attempt in 1 2 3 4; do
    PR_JSON="$(gh pr view "$PR_NUMBER" --repo "$GITHUB_REPOSITORY" --json number,state,headRefOid,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup)"
    PR_STATE="$(printf '%s' "$PR_JSON" | jq -r '.state // "OPEN"')"
    MERGE_STATE="$(printf '%s' "$PR_JSON" | jq -r '.mergeStateStatus')"
    if [ "$PR_STATE" != "OPEN" ] || [ "$MERGE_STATE" != "UNKNOWN" ]; then
      return 0
    fi
    if [ "$attempt" -lt 4 ]; then
      retry_delay=$((PR_GOVERNANCE_RETRY_SLEEP_SECONDS * attempt))
      printf 'Merge state lookup attempt %s of 4 returned UNKNOWN; retrying in %s second(s).\n' \
        "$attempt" "$retry_delay"
      sleep "$retry_delay"
    fi
  done
}

pr_snapshot_is_current() {
  local latest_pr_json latest_pr_state latest_head_sha

  latest_pr_json="$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}")"
  latest_pr_state="$(printf '%s' "$latest_pr_json" | jq -r '.state // "unknown"')"
  latest_head_sha="$(printf '%s' "$latest_pr_json" | jq -r '.head.sha // ""')"

  if [ "$latest_pr_state" != "open" ]; then
    printf 'PR state became %s during gate evaluation; skipping stale gate publication.\n' \
      "$(printf '%s' "$latest_pr_state" | tr '[:lower:]' '[:upper:]')"
    return 1
  fi
  if [ "$latest_head_sha" != "$HEAD_SHA" ]; then
    printf 'PR head changed during gate evaluation from %s to %s; skipping stale gate publication.\n' \
      "$HEAD_SHA" "${latest_head_sha:-unknown}"
    return 1
  fi
  return 0
}

join_items() {
  local item
  for item in "$@"; do
    printf -- '- %s\n' "$item"
  done
}

post_or_update_blocker_comment() {
  local head_ref_oid="$1"
  local body existing_comment_id
  # shellcheck disable=SC2016  # Markdown backticks are literal.
  body="$(printf '%s\nPR governance metadata gate is not ready for `%s`:\n\n%s' \
    "$COMMENT_MARKER" \
    "$head_ref_oid" \
    "$(join_items "${BLOCKERS[@]}")")"

  existing_comment_id="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq ".[] | select(.body | contains(\"${COMMENT_MARKER}\")) | .id" \
    | tail -n 1 || true)"

  if [ -n "$existing_comment_id" ]; then
    gh api --method PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${existing_comment_id}" -f body="$body"
  else
    gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" -f body="$body"
  fi
}

update_existing_marker_comment_status() {
  local head_ref_oid="$1"
  local status_message="$2"
  local body existing_comment_id

  existing_comment_id="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq ".[] | select(.body | contains(\"${COMMENT_MARKER}\")) | .id" \
    | tail -n 1 || true)"
  [ -n "$existing_comment_id" ] || return 0

  # shellcheck disable=SC2016  # Markdown backticks are literal.
  body="$(printf '%s\nPR governance metadata gate update for `%s`: no current blocking failures remain.\n\n%s' \
    "$COMMENT_MARKER" \
    "$head_ref_oid" \
    "$status_message")"
  gh api --method PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${existing_comment_id}" -f body="$body"
}

publish_gate_check() {
  local status="$1"
  local conclusion="$2"
  local title="$3"
  local summary="$4"
  local external_id existing_check existing_check_id existing_check_status

  external_id="pr-governance:${PR_NUMBER}:${HEAD_SHA}"
  existing_check="$(printf '%s' "$CHECK_RUNS" | jq -r \
    --arg name "$CHECK_NAME" \
    --arg external_id "$external_id" '
      [.check_runs[]
        | select(.name == $name)
        | select(.external_id == $external_id)
        | select(.app.slug == "github-actions")]
      | last
      | if . == null then empty else "\(.id) \(.status)" end
    ')"
  existing_check_id="${existing_check%% *}"
  existing_check_status="${existing_check##* }"

  # The check-runs API silently refuses to move a completed check-run back to a
  # non-completed status (PATCH returns 200 but the run stays completed), which
  # leaves a stale failure pinned to the head. Publish non-completed states as a
  # fresh check-run instead; required-check evaluation follows the newest run.
  if [ "$status" != "completed" ] && [ "$existing_check_status" = "completed" ]; then
    existing_check_id=""
  fi

  # shellcheck disable=SC2016  # Markdown backticks are literal.
  printf 'Publishing `%s` as %s on PR head %s.\n' "$CHECK_NAME" "$status" "$HEAD_SHA"
  if [ -n "$existing_check_id" ]; then
    if [ "$status" = "completed" ]; then
      gh api --method PATCH "repos/${GITHUB_REPOSITORY}/check-runs/${existing_check_id}" \
        -f name="$CHECK_NAME" \
        -f status="$status" \
        -f conclusion="$conclusion" \
        -f details_url="$RUN_DETAILS_URL" \
        -f 'output[title]'="$title" \
        -f 'output[summary]'="$summary"
    else
      gh api --method PATCH "repos/${GITHUB_REPOSITORY}/check-runs/${existing_check_id}" \
        -f name="$CHECK_NAME" \
        -f status="$status" \
        -f details_url="$RUN_DETAILS_URL" \
        -f 'output[title]'="$title" \
        -f 'output[summary]'="$summary"
    fi
    return
  fi

  if [ "$status" = "completed" ]; then
    gh api --method POST "repos/${GITHUB_REPOSITORY}/check-runs" \
      -f name="$CHECK_NAME" \
      -f head_sha="$HEAD_SHA" \
      -f status="$status" \
      -f conclusion="$conclusion" \
      -f external_id="$external_id" \
      -f details_url="$RUN_DETAILS_URL" \
      -f 'output[title]'="$title" \
      -f 'output[summary]'="$summary"
  else
    gh api --method POST "repos/${GITHUB_REPOSITORY}/check-runs" \
      -f name="$CHECK_NAME" \
      -f head_sha="$HEAD_SHA" \
      -f status="$status" \
      -f external_id="$external_id" \
      -f details_url="$RUN_DETAILS_URL" \
      -f 'output[title]'="$title" \
      -f 'output[summary]'="$summary"
  fi
}

PR_GOVERNANCE_RETRY_SLEEP_SECONDS="${PR_GOVERNANCE_RETRY_SLEEP_SECONDS:-3}"
if ! [[ "$PR_GOVERNANCE_RETRY_SLEEP_SECONDS" =~ ^[0-9]+$ ]] || [ "$PR_GOVERNANCE_RETRY_SLEEP_SECONDS" -gt 30 ]; then
  printf 'PR governance retry sleep must be an integer between 0 and 30 seconds.\n' >&2
  exit 1
fi

PR_JSON=''
PR_STATE='OPEN'
MERGE_STATE='UNKNOWN'
read_pr_metadata_with_merge_state_retry
case "$PR_STATE" in
  OPEN)
    ;;
  CLOSED | MERGED)
    printf 'PR state became %s during merge-state refresh; no gate status is required.\n' "$PR_STATE"
    exit 0
    ;;
  *)
    printf 'GitHub returned an unrecognized PR state; refusing to evaluate.\n' >&2
    exit 1
    ;;
esac
HEAD_SHA="$(printf '%s' "$PR_JSON" | jq -r '.headRefOid // ""')"
if ! [[ "$HEAD_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  printf 'GitHub returned an invalid PR head SHA; refusing to evaluate.\n' >&2
  exit 1
fi
HEAD_REF_OID="$HEAD_SHA" # headRefOid equivalent for REST metadata paths.
IS_DRAFT="$(printf '%s' "$PR_JSON" | jq -r '.isDraft')"
REVIEW_DECISION="$(printf '%s' "$PR_JSON" | jq -r '.reviewDecision // ""')"

if [ "$IS_DRAFT" = "true" ]; then
  add_waiting 'Draft PR: merge automation is paused.'
fi

if [ "$MERGE_STATE" = "BEHIND" ]; then
  add_blocker 'Branch is BEHIND the base branch; update the branch and re-run checks.'
fi

if [ "$MERGE_STATE" = "DIRTY" ]; then
  add_blocker 'Merge state is DIRTY; resolve conflicts before merge.'
fi

if [ "$MERGE_STATE" = "UNKNOWN" ]; then
  add_waiting "Merge state is still UNKNOWN after 4 attempts on ${HEAD_REF_OID}; waiting for GitHub to refresh mergeability."
fi

if [ "$REVIEW_DECISION" = "CHANGES_REQUESTED" ]; then
  add_blocker 'Review decision is CHANGES_REQUESTED; address requested changes before merge.'
fi

# shellcheck disable=SC2016  # GraphQL variables must remain literal.
THREADS_JSON="$(gh api graphql \
  -F owner="$OWNER" \
  -F repo="$REPO" \
  -F number="$PR_NUMBER" \
  -f query='query($owner:String!, $repo:String!, $number:Int!) { repository(owner:$owner, name:$repo) { pullRequest(number:$number) { headRefOid mergeStateStatus reviewThreads(first:100) { pageInfo { hasNextPage } nodes { id isResolved isOutdated comments(first:100) { pageInfo { hasNextPage } nodes { databaseId } } } } } } }')"
THREAD_METADATA_TRUNCATED="$(printf '%s' "$THREADS_JSON" | jq '
  (.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage // false)
  or any(
    .data.repository.pullRequest.reviewThreads.nodes[]?;
    (.comments.pageInfo.hasNextPage // false)
  )'
)"
if [ "$THREAD_METADATA_TRUNCATED" = "true" ]; then
  add_blocker 'Review thread metadata was truncated; current resolution state could not be proven.'
fi
UNRESOLVED_THREADS="$(printf '%s' "$THREADS_JSON" | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false and .isOutdated == false)] | length')"
UNRESOLVED_REVIEW_COMMENT_IDS_JSON="$(printf '%s' "$THREADS_JSON" | jq '
  [.data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == false and .isOutdated == false)
    | .comments.nodes[]?
    | .databaseId
    | select(. != null)]
  | unique'
)"
if [ "$UNRESOLVED_THREADS" != "0" ]; then
  add_blocker "${UNRESOLVED_THREADS} unresolved current review thread(s) remain."
fi

if ! REQUIRED_CHECKS="$(gh pr checks "$PR_NUMBER" --repo "$GITHUB_REPOSITORY" --required --json name,state,link 2>"$PR_CHECKS_ERROR_FILE")"; then
  PR_CHECKS_ERROR="$(<"$PR_CHECKS_ERROR_FILE")"
  if printf '%s' "$PR_CHECKS_ERROR" | grep -qi 'no required checks reported'; then
    add_waiting "Ruleset-governed branch: no legacy required status contexts reported for ${HEAD_REF_OID}; relying on ruleset workflows and code-scanning gates."
  else
    # Raw CLI diagnostics stay in the run log (indented so they cannot be
    # parsed as workflow commands); the published blocker stays generic.
    printf 'gh pr checks failed:\n'
    printf '%s\n' "$PR_CHECKS_ERROR" | sed 's/^/    /'
    add_blocker 'Required check metadata could not be read; see the workflow run log.'
  fi
else
  # Fail closed: any state outside the explicit pass and pending lists is a
  # blocker, so unrecognized or errored states cannot slip through as success.
  while IFS= read -r item; do
    [ -n "$item" ] && add_blocker "$item"
  done < <(printf '%s' "$REQUIRED_CHECKS" | jq -r --arg check_name "$CHECK_NAME" '
    .[]
    | select(.name != $check_name)
    | (.state | ascii_upcase) as $state
    | select(["SUCCESS", "PASS", "SKIPPED", "NEUTRAL"] | index($state) | not)
    | select(["PENDING", "QUEUED", "IN_PROGRESS", "REQUESTED", "WAITING", "EXPECTED"] | index($state) | not)
    | "Required check `\(.name | gsub("[`\\r\\n]"; " "))` is \($state) on the current head."
  ')

  PENDING_REQUIRED_COUNT="$(printf '%s' "$REQUIRED_CHECKS" | jq --arg check_name "$CHECK_NAME" '[.[] | select(.name != $check_name) | select((.state | ascii_upcase) as $state | ["PENDING", "QUEUED", "IN_PROGRESS", "REQUESTED", "WAITING", "EXPECTED"] | index($state))] | length')"
  if [ "$PENDING_REQUIRED_COUNT" != "0" ]; then
    add_waiting "Waiting for ${PENDING_REQUIRED_COUNT} required check(s) to finish on ${HEAD_REF_OID}."
  fi
fi

CODERABBIT_BLOCKING_PATTERN='pre[- ]merge|blocking|failure|failed|warning|potential issue|actionable comment|actionable comments'
CODERABBIT_ISSUE_BLOCKING_PATTERN='pre[- ]merge[^\n]*(blocking|failure|failed|warning|potential issue)|blocking (issue|finding)|potential issue|actionable comments?|changes requested|request changes'
CODERABBIT_ISSUE_SUBSTANTIVE_BLOCKING_PATTERN='pre[- ]merge[^\n]*(blocking|failure|failed|warning|potential issue)|blocking (issue|finding)|potential issue|changes requested|request changes'
CODERABBIT_NO_ACTIONABLE_PATTERN='no actionable comments? (were )?generated'
CHECK_RUNS="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${HEAD_SHA}/check-runs?per_page=100")"
COMMIT_STATUS_JSON='{"statuses":[]}'
if ! COMMIT_STATUS_JSON="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${HEAD_SHA}/status" 2>"$COMMIT_STATUS_ERROR_FILE")"; then
  printf 'commit status lookup failed:\n'
  printf '%s\n' "$(<"$COMMIT_STATUS_ERROR_FILE")" | sed 's/^/    /'
  add_blocker 'Current-head commit statuses could not be read; see the workflow run log.'
fi
CODERABBIT_MATCHES="$(printf '%s' "$CHECK_RUNS" | jq '
  [.check_runs[]
    | select(
        .app.slug == "coderabbitai"
        or .app.slug == "github-code-quality"
        or (.name | test("CodeRabbit|coderabbit|GitHub Code Quality|github-code-quality"; "i"))
      )]'
)"
CODERABBIT_STATUS_MATCHES="$(printf '%s' "$COMMIT_STATUS_JSON" | jq '
  [.statuses[]
    | select((.context // "") | test("CodeRabbit|coderabbit|GitHub Code Quality|github-code-quality"; "i"))]
  | group_by((.context // "") | ascii_downcase)
  | map(sort_by(.updated_at // .created_at // "") | last)
')"
CODERABBIT_CHECK_COUNT="$(printf '%s' "$CODERABBIT_MATCHES" | jq 'length')"
CODERABBIT_STATUS_COUNT="$(printf '%s' "$CODERABBIT_STATUS_MATCHES" | jq 'length')"
CODERABBIT_COUNT=$((CODERABBIT_CHECK_COUNT + CODERABBIT_STATUS_COUNT))
if [ "$CODERABBIT_COUNT" = "0" ]; then
  if ! OPENCODE_REVIEWS_JSON="$(gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/reviews" 2>"$OPENCODE_REVIEWS_ERROR_FILE")"; then
    printf 'OpenCode review lookup failed:\n'
    printf '%s\n' "$(<"$OPENCODE_REVIEWS_ERROR_FILE")" | sed 's/^/    /'
    add_blocker 'OpenCode adversarial review evidence could not be read; see the workflow run log.'
  else
    OPENCODE_ADVERSARIAL_APPROVAL_COUNT="$(printf '%s' "$OPENCODE_REVIEWS_JSON" | jq --arg head_sha "$HEAD_SHA" '
      [.[][]
        | select(((.user.login // "") | ascii_downcase) as $login
          | $login == "opencode-agent" or $login == "opencode-agent[bot]")
        | select((.state // "" | ascii_upcase) == "APPROVED")
        | select((.commit_id // "") == $head_sha)
        | select((.body // "") | contains("Head SHA: `" + $head_sha + "`"))
        | select((.body // "") | contains("## Adversarial validation"))
        | select((.body // "") | test("\\\"status\\\"\\s*:\\s*\\\"passed\\\""))
        | select([(.body // "") | scan("\\\"outcome\\\"\\s*:\\s*\\\"falsified\\\"")] | length >= 2)]
      | length'
    )"
    if [ "$OPENCODE_ADVERSARIAL_APPROVAL_COUNT" = "0" ]; then
      add_waiting "Waiting for current-head CodeRabbit evidence or a structured OpenCode App adversarial approval on ${HEAD_REF_OID}."
    else
      printf 'CodeRabbit check is absent; accepted current-head OpenCode App adversarial approval on %s.\n' "$HEAD_REF_OID"
    fi
  fi
else
  CODERABBIT_PENDING="$(printf '%s' "$CODERABBIT_MATCHES" | jq '[.[] | select(.status != "completed")] | length')"
  CODERABBIT_STATUS_PENDING="$(printf '%s' "$CODERABBIT_STATUS_MATCHES" | jq '[.[] | select((.state // "" | ascii_downcase) == "pending")] | length')"
  CODERABBIT_FAILED="$(printf '%s' "$CODERABBIT_MATCHES" | jq --arg pattern "$CODERABBIT_BLOCKING_PATTERN" '
    [.[]
      | select(.status == "completed")
      | select((.conclusion // "") as $conclusion
        | if $conclusion == "success" or $conclusion == "skipped" then false
          elif $conclusion == "neutral" then
            # Skip evidence only counts when the output carries no blocking
            # language alongside it.
            (([.output.title, .output.summary, .output.text] | map(. // "") | join("\n")) as $neutral_output
              | (($neutral_output | test("Review skipped"; "i"))
                 and (($neutral_output | test($pattern; "i")) | not))
              | not)
          else true
          end)]
    | length'
  )"
  CODERABBIT_STATUS_FAILED="$(printf '%s' "$CODERABBIT_STATUS_MATCHES" | jq '[.[] | select((.state // "" | ascii_downcase) as $state | $state == "error" or $state == "failure")] | length')"
  CODERABBIT_STATUS_UNKNOWN="$(printf '%s' "$CODERABBIT_STATUS_MATCHES" | jq '[.[] | select((.state // "" | ascii_downcase) as $state | ["success", "pending", "error", "failure"] | index($state) | not)] | length')"
  if [ "$CODERABBIT_FAILED" != "0" ]; then
    add_blocker "Current-head CodeRabbit check has a blocking conclusion on ${HEAD_REF_OID}."
  fi
  if [ "$CODERABBIT_STATUS_FAILED" != "0" ]; then
    add_blocker "Current-head CodeRabbit commit status has a blocking conclusion on ${HEAD_REF_OID}."
  fi
  if [ "$CODERABBIT_STATUS_UNKNOWN" != "0" ]; then
    add_blocker "Current-head CodeRabbit commit status has an unrecognized state on ${HEAD_REF_OID}."
  fi
  if [ "$CODERABBIT_FAILED" != "0" ] || [ "$CODERABBIT_STATUS_FAILED" != "0" ] || [ "$CODERABBIT_STATUS_UNKNOWN" != "0" ]; then
    :
  elif [ "$CODERABBIT_PENDING" != "0" ] || [ "$CODERABBIT_STATUS_PENDING" != "0" ]; then
    add_waiting "Waiting for current-head CodeRabbit evidence on ${HEAD_REF_OID}."
  fi
fi

if ! ISSUE_COMMENTS_JSON="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" 2>"$ISSUE_COMMENTS_ERROR_FILE")"; then
  printf 'issue comment lookup failed:\n'
  printf '%s\n' "$(<"$ISSUE_COMMENTS_ERROR_FILE")" | sed 's/^/    /'
  add_blocker 'PR issue comments could not be read; see the workflow run log.'
else
  CODERABBIT_ISSUE_BLOCKERS="$(printf '%s' "$ISSUE_COMMENTS_JSON" | jq -s \
    --arg head_sha "$HEAD_SHA" \
    --arg pattern "$CODERABBIT_ISSUE_BLOCKING_PATTERN" \
    --arg substantive_pattern "$CODERABBIT_ISSUE_SUBSTANTIVE_BLOCKING_PATTERN" \
    --arg no_actionable_pattern "$CODERABBIT_NO_ACTIONABLE_PATTERN" '
    [.[][]
      | select((.user.login // "") | test("'"$REVIEW_BOT_LOGIN_PATTERN"'"; "i"))
      | select(
          (.body // "") as $body
          | ($body | split("<details>")[0]) as $summary
          | ($body | test($pattern; "i"))
            and (
              (($body | test($no_actionable_pattern; "i")) | not)
              or ($summary | test($substantive_pattern; "i"))
            )
        )
      | select((.body // "") | contains($head_sha))]
    | length'
  )"
  if [ "$CODERABBIT_ISSUE_BLOCKERS" != "0" ]; then
    add_blocker "Current-head CodeRabbit issue comment has blocking warning/failure evidence on ${HEAD_REF_OID}."
  fi
fi

if ! REVIEW_COMMENTS_JSON="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/comments" 2>"$REVIEW_COMMENTS_ERROR_FILE")"; then
  printf 'review comment lookup failed:\n'
  printf '%s\n' "$(<"$REVIEW_COMMENTS_ERROR_FILE")" | sed 's/^/    /'
  add_blocker 'PR review comments could not be read; see the workflow run log.'
else
  CODERABBIT_REVIEW_BLOCKERS="$(printf '%s' "$REVIEW_COMMENTS_JSON" | jq -s \
    --arg head_sha "$HEAD_SHA" \
    --arg pattern "$CODERABBIT_BLOCKING_PATTERN" \
    --argjson unresolved_comment_ids "$UNRESOLVED_REVIEW_COMMENT_IDS_JSON" '
    [.[][]
      | select((.user.login // "") | test("'"$REVIEW_BOT_LOGIN_PATTERN"'"; "i"))
      | select((.body // "") | test($pattern; "i"))
      | select(.id as $comment_id | ($unresolved_comment_ids | index($comment_id)) != null)
      | select(((.commit_id // "") == $head_sha) or ((.original_commit_id // "") == $head_sha) or ((.body // "") | contains($head_sha)))]
    | length'
  )"
  if [ "$CODERABBIT_REVIEW_BLOCKERS" != "0" ]; then
    add_blocker "Current-head CodeRabbit review comment has blocking warning/failure evidence on ${HEAD_REF_OID}."
  fi
fi

if ! pr_snapshot_is_current; then
  exit 0
fi

if [ "${#BLOCKERS[@]}" -gt 0 ]; then
  BLOCKER_SUMMARY="$(join_items "${BLOCKERS[@]}")"
  printf 'PR governance blockers for %s on %s:\n%s\n' "$PR_NUMBER" "$HEAD_REF_OID" "$BLOCKER_SUMMARY"
  post_or_update_blocker_comment "$HEAD_REF_OID"
  publish_gate_check \
    completed \
    failure \
    'PR governance metadata gate blocked' \
    "$BLOCKER_SUMMARY"
  exit 0
fi

if [ "${#WAITING[@]}" -gt 0 ]; then
  WAITING_SUMMARY="$(join_items "${WAITING[@]}")"
  printf '%s\n' "$WAITING_SUMMARY"
  update_existing_marker_comment_status \
    "$HEAD_REF_OID" \
    'PR governance metadata gate is waiting on current-head requirements; see the latest check for pending reasons.'
  publish_gate_check \
    in_progress \
    '' \
    'PR governance metadata gate is waiting' \
    "$WAITING_SUMMARY"
  exit 0
fi

# shellcheck disable=SC2016  # Markdown backticks are literal.
printf 'PR governance metadata gate is ready for `%s` on `%s`.\n' "$PR_NUMBER" "$HEAD_REF_OID"
update_existing_marker_comment_status \
  "$HEAD_REF_OID" \
  'PR governance metadata gate is ready; all current-head requirements passed.'
publish_gate_check \
  completed \
  success \
  'PR governance metadata gate is ready' \
  "All current-head governance requirements passed for PR ${PR_NUMBER} on ${HEAD_REF_OID}."
