#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="$repo_root/scripts/ci/pr_governance_gate.sh"

make_fake_gh() {
  local bin_dir="$1"
  cat > "$bin_dir/gh" <<'FAKEGH'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >> "$GH_LOG"

head_sha="0123456789abcdef0123456789abcdef01234567"
args="$*"

if [ "$1" = "pr" ] && [ "$2" = "view" ]; then
  case "${GH_SCENARIO:-pass}" in
    draft)
      printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":true,"mergeable":"MERGEABLE","mergeStateStatus":"CLEAN","reviewDecision":"","statusCheckRollup":[]}' "$head_sha"
      ;;
    changes_requested)
      printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":false,"mergeable":"MERGEABLE","mergeStateStatus":"CLEAN","reviewDecision":"CHANGES_REQUESTED","statusCheckRollup":[]}' "$head_sha"
      ;;
    transient_unknown)
      count_file="$GH_STATE_DIR/pr-view-count"
      count="$(cat "$count_file" 2>/dev/null || printf '0')"
      printf '%s\n' "$((count + 1))" > "$count_file"
      if [ "$count" -eq 0 ]; then
        printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":false,"mergeable":"UNKNOWN","mergeStateStatus":"UNKNOWN","reviewDecision":"","statusCheckRollup":[]}' "$head_sha"
      else
        printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":false,"mergeable":"MERGEABLE","mergeStateStatus":"CLEAN","reviewDecision":"","statusCheckRollup":[]}' "$head_sha"
      fi
      ;;
    merged_during_unknown)
      count_file="$GH_STATE_DIR/pr-view-count"
      count="$(cat "$count_file" 2>/dev/null || printf '0')"
      printf '%s\n' "$((count + 1))" > "$count_file"
      if [ "$count" -eq 0 ]; then
        printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":false,"mergeable":"UNKNOWN","mergeStateStatus":"UNKNOWN","reviewDecision":"","statusCheckRollup":[]}' "$head_sha"
      else
        printf '{"number":42,"state":"MERGED","headRefOid":"%s","isDraft":false,"mergeable":"UNKNOWN","mergeStateStatus":"UNKNOWN","reviewDecision":"APPROVED","statusCheckRollup":[]}' "$head_sha"
      fi
      ;;
    persistent_unknown)
      printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":false,"mergeable":"UNKNOWN","mergeStateStatus":"UNKNOWN","reviewDecision":"","statusCheckRollup":[]}' "$head_sha"
      ;;
    *)
      printf '{"number":42,"state":"OPEN","headRefOid":"%s","isDraft":false,"mergeable":"MERGEABLE","mergeStateStatus":"CLEAN","reviewDecision":"","statusCheckRollup":[]}' "$head_sha"
      ;;
  esac
  exit 0
fi

if [ "$1" = "api" ] && [[ "$2" == repos/*/pulls/42 ]]; then
  if [[ "$args" == *".base.sha"* ]]; then
    printf 'abcdefabcdefabcdefabcdefabcdefabcdefabcd'
  else
    latest_head_sha="$head_sha"
    latest_state="open"
    if [ "${GH_SCENARIO:-pass}" = "head_changed_during_evaluation" ]; then
      latest_head_sha="fedcba9876543210fedcba9876543210fedcba98"
    elif [ "${GH_SCENARIO:-pass}" = "closed_during_evaluation" ]; then
      latest_state="closed"
    fi
    printf '{"state":"%s","head":{"sha":"%s"}}' "$latest_state" "$latest_head_sha"
  fi
  exit 0
fi

if [ "$1" = "api" ] && [[ "$2" == repos/*/commits/* ]] && [[ "$2" != */check-runs* ]] && [[ "$2" != */status ]]; then
  printf '2026-05-19T00:00:00Z'
  exit 0
fi

if [ "$1" = "api" ] && [ "$2" = "graphql" ]; then
  if [ "${GH_SCENARIO:-pass}" = "graphql_error" ]; then
    printf 'GraphQL request failed\n' >&2
    exit 1
  fi
  if [ "${GH_SCENARIO:-pass}" = "coderabbit_resolved_current_review_comment" ]; then
    printf '{"data":{"repository":{"pullRequest":{"headRefOid":"%s","mergeStateStatus":"CLEAN","reviewThreads":{"nodes":[{"id":"thread-888","isResolved":true,"isOutdated":false,"comments":{"nodes":[{"databaseId":888}]}}]}}}}}' "$head_sha"
    exit 0
  fi
  if [ "${GH_SCENARIO:-pass}" = "coderabbit_current_review_comment" ] || [ "${GH_SCENARIO:-pass}" = "github_code_quality_current_review_comment" ]; then
    printf '{"data":{"repository":{"pullRequest":{"headRefOid":"%s","mergeStateStatus":"CLEAN","reviewThreads":{"nodes":[{"id":"thread-888","isResolved":false,"isOutdated":false,"comments":{"nodes":[{"databaseId":888}]}}]}}}}}' "$head_sha"
    exit 0
  fi
  if [ "${GH_SCENARIO:-pass}" = "review_threads_truncated" ]; then
    printf '{"data":{"repository":{"pullRequest":{"headRefOid":"%s","mergeStateStatus":"CLEAN","reviewThreads":{"pageInfo":{"hasNextPage":true},"nodes":[]}}}}}' "$head_sha"
    exit 0
  fi
  if [ "${GH_SCENARIO:-pass}" = "review_thread_comments_truncated" ]; then
    printf '{"data":{"repository":{"pullRequest":{"headRefOid":"%s","mergeStateStatus":"CLEAN","reviewThreads":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"thread-888","isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":true},"nodes":[{"databaseId":888}]}}]}}}}}' "$head_sha"
    exit 0
  fi
  if [ "${GH_SCENARIO:-pass}" = "persistent_unknown" ]; then
    printf '{"data":{"repository":{"pullRequest":{"headRefOid":"%s","mergeStateStatus":"UNKNOWN","reviewThreads":{"nodes":[]}}}}}' "$head_sha"
    exit 0
  fi
  printf '{"data":{"repository":{"pullRequest":{"headRefOid":"%s","mergeStateStatus":"CLEAN","reviewThreads":{"nodes":[]}}}}}' "$head_sha"
  exit 0
fi

if [ "$1" = "pr" ] && [ "$2" = "checks" ]; then
  if [ "${GH_SCENARIO:-pass}" = "no_required_checks" ]; then
    printf 'no required checks reported on the test branch\n' >&2
    exit 1
  fi
  if [ "${GH_SCENARIO:-pass}" = "pr_checks_error" ]; then
    printf 'Error: request failed: https://api.example/download?X-Amz-Signature=SECRETVALUE\n' >&2
    exit 1
  fi
  case "${GH_SCENARIO:-pass}" in
    pending|existing_gate_pending)
      printf '[{"name":"Application CI","state":"IN_PROGRESS","link":"https://checks/app-ci"}]'
      ;;
    unknown_state)
      printf '[{"name":"Application CI","state":"STALE","link":"https://checks/app-ci"}]'
      ;;
    startup_failure)
      printf '[{"name":"Application CI","state":"STARTUP_FAILURE","link":"https://checks/app-ci"}]'
      ;;
    failed)
      printf '[{"name":"Application CI","state":"FAILED","link":"https://checks/app-ci"}]'
      ;;
    failure|failed_existing)
      printf '[{"name":"Application CI","state":"FAILURE","link":"https://checks/app-ci"}]'
      ;;
    self_gate_failed)
      printf '[{"name":"metadata-only gate evaluation","state":"FAILURE","link":"https://checks/governance"},{"name":"Application CI","state":"SUCCESS","link":"https://checks/app-ci"}]'
      ;;
    *)
      printf '[{"name":"Application CI","state":"SUCCESS","link":"https://checks/app-ci"}]'
      ;;
  esac
  exit 0
fi

if [ "$1" = "api" ] && [[ "$2" == repos/*/commits/*/check-runs* ]]; then
  case "${GH_SCENARIO:-pass}" in
    clean_summary_success|clean_summary_skipped|clean_summary_neutral|clean_summary_failure|clean_without_skip_neutral|forged_clean_success|mixed_summary_success|mixed_summary_skipped|mixed_summary_neutral|qualified_summary_success|qualified_but_success)
      conclusion="${GH_SCENARIO##*_}"
      app_slug='coderabbitai'
      summary='No warnings found.'
      output_text='No actionable comments were generated'
      case "$GH_SCENARIO" in
        forged_clean_success) app_slug='github-actions' ;;
        clean_summary_skipped) summary=$' \tno WARNINGS found! \t\r' ;;
        clean_summary_neutral) output_text=$'Review skipped\nNo actionable comments were generated' ;;
        mixed_summary_*) output_text=$'Review skipped\nNo actionable comments were generated\nPre-merge blocking warning' ;;
        qualified_summary_success) summary='No warnings found except blocking issues' ;;
        qualified_but_success) summary='No warnings found, but a blocking issue remains' ;;
      esac
      jq -cn --arg app_slug "$app_slug" --arg conclusion "$conclusion" --arg summary "$summary" --arg text "$output_text" \
        '{check_runs:[{name:"CodeRabbit",app:{slug:$app_slug},status:"completed",conclusion:$conclusion,output:{summary:$summary,text:$text}}]}'
      ;;
    forged_check|forged_check_pending_notice)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"github-actions"},"status":"completed","conclusion":"success"}]}'
      ;;
    forged_status|forged_status_pending_notice|missing_status_creator|wrong_status_creator_type|github_code_quality_status)
      printf '{"check_runs":[]}'
      ;;
    github_code_quality_check)
      printf '{"check_runs":[{"name":"GitHub Code Quality","app":{"slug":"github-code-quality"},"status":"completed","conclusion":"success"}]}'
      ;;
    coderabbit_success_with_warning|coderabbit_skipped_with_warning)
      conclusion="${GH_SCENARIO#coderabbit_}"
      conclusion="${conclusion%_with_warning}"
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"%s","output":{"text":"Pre-merge blocking warning"}}]}' "$conclusion"
      ;;
    coderabbit_pending)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"in_progress","conclusion":null,"html_url":"https://checks/coderabbit"}]}'
      ;;
    missing_coderabbit|missing_coderabbit_with_adversarial_approval|missing_coderabbit_stale_approval|missing_coderabbit_actions_approval|missing_coderabbit_one_probe|missing_coderabbit_adversarial_approval_with_pending_notice|coderabbit_approval_pending|coderabbit_status_success_with_pending_notice|opencode_reviews_error|coderabbit_status_success|coderabbit_status_pending|coderabbit_status_failed|coderabbit_status_unknown)
      printf '{"check_runs":[]}'
      ;;
    coderabbit_failed)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"failure","html_url":"https://checks/coderabbit"}]}'
      ;;
    coderabbit_neutral)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"neutral","output":{"title":"CodeRabbit","summary":"Review completed","text":"No skip evidence"},"html_url":"https://checks/coderabbit"}]}'
      ;;
    coderabbit_review_skipped)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"neutral","output":{"title":"CodeRabbit","summary":"Review skipped","text":"Review skipped"},"html_url":"https://checks/coderabbit"}]}'
      ;;
    coderabbit_skip_with_warning)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"neutral","output":{"title":"CodeRabbit","summary":"Review skipped","text":"Pre-merge blocking warning"},"html_url":"https://checks/coderabbit"}]}'
      ;;
    existing_gate|existing_gate_pending)
      printf '{"check_runs":[{"id":999,"name":"metadata-only gate evaluation","external_id":"pr-governance:42:0123456789abcdef0123456789abcdef01234567","app":{"slug":"github-actions"},"status":"completed","conclusion":"failure"},{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"success","html_url":"https://checks/coderabbit"}]}'
      ;;
    *)
      printf '{"check_runs":[{"name":"CodeRabbit","app":{"slug":"coderabbitai"},"status":"completed","conclusion":"success","html_url":"https://checks/coderabbit"}]}'
      ;;
  esac
  exit 0
fi

if [ "$1" = "api" ] && [[ "$2" == repos/*/commits/*/status ]]; then
  case "${GH_SCENARIO:-pass}" in
    missing_status_creator)
      printf '{"statuses":[{"context":"CodeRabbit","state":"success"}]}'
      ;;
    wrong_status_creator_type)
      printf '{"statuses":[{"context":"CodeRabbit","state":"success","creator":{"login":"coderabbitai[bot]","type":"User"}}]}'
      ;;
    github_code_quality_status)
      printf '{"statuses":[{"context":"GitHub Code Quality","state":"success","creator":{"login":"github-code-quality[bot]","type":"Bot"}}]}'
      ;;
    forged_status|forged_status_pending_notice)
      printf '{"statuses":[{"context":"CodeRabbit","state":"success","creator":{"login":"unrelated-app[bot]","type":"Bot"}}]}'
      ;;
    coderabbit_status_success|coderabbit_status_success_with_pending_notice)
      printf '{"statuses":[{"context":"CodeRabbit","creator":{"login":"coderabbitai[bot]","type":"Bot"},"state":"success","description":"Review approved","created_at":"2026-07-29T01:54:41Z","updated_at":"2026-07-29T01:54:41Z"}]}'
      ;;
    coderabbit_status_pending)
      printf '{"statuses":[{"context":"CodeRabbit","creator":{"login":"coderabbitai[bot]","type":"Bot"},"state":"pending","description":"Review in progress","created_at":"2026-07-29T01:54:41Z","updated_at":"2026-07-29T01:54:41Z"}]}'
      ;;
    coderabbit_status_failed)
      printf '{"statuses":[{"context":"CodeRabbit","creator":{"login":"coderabbitai[bot]","type":"Bot"},"state":"failure","description":"Review failed","created_at":"2026-07-29T01:54:41Z","updated_at":"2026-07-29T01:54:41Z"}]}'
      ;;
    coderabbit_status_unknown)
      printf '{"statuses":[{"context":"CodeRabbit","creator":{"login":"coderabbitai[bot]","type":"Bot"},"state":"stale","description":"Unrecognized state","created_at":"2026-07-29T01:54:41Z","updated_at":"2026-07-29T01:54:41Z"}]}'
      ;;
    *)
      printf '{"statuses":[]}'
      ;;
  esac
  exit 0
fi

if [ "$1" = "api" ] && [[ "$args" == *repos/*/pulls/42/reviews* ]]; then
  if [ "${GH_SCENARIO:-pass}" = "opencode_reviews_error" ]; then
    printf 'Error: review lookup failed: https://api.example/reviews?token=SECRETVALUE\n' >&2
    exit 1
  fi
  case "${GH_SCENARIO:-pass}" in
    missing_coderabbit_with_adversarial_approval|missing_coderabbit_adversarial_approval_with_pending_notice)
      printf '[[{"user":{"login":"opencode-agent[bot]"},"state":"APPROVED","commit_id":"%s","body":"## Adversarial validation\\n\\n```json\\n{\\\"status\\\":\\\"passed\\\",\\\"probes\\\":[{\\\"outcome\\\":\\\"falsified\\\"},{\\\"outcome\\\":\\\"falsified\\\"}]}\\n```\\n\\nHead SHA: `%s`"}]]' "$head_sha" "$head_sha"
      ;;
    missing_coderabbit_stale_approval)
      printf '[[{"user":{"login":"opencode-agent[bot]"},"state":"APPROVED","commit_id":"%s","body":"## Adversarial validation\\n\\n```json\\n{\\\"status\\\":\\\"passed\\\",\\\"probes\\\":[{\\\"outcome\\\":\\\"falsified\\\"},{\\\"outcome\\\":\\\"falsified\\\"}]}\\n```\\n\\nHead SHA: `old-head`"}]]' "$head_sha"
      ;;
    missing_coderabbit_actions_approval)
      printf '[[{"user":{"login":"github-actions[bot]"},"state":"APPROVED","commit_id":"%s","body":"## Adversarial validation\\n\\n```json\\n{\\\"status\\\":\\\"passed\\\",\\\"probes\\\":[{\\\"outcome\\\":\\\"falsified\\\"},{\\\"outcome\\\":\\\"falsified\\\"}]}\\n```\\n\\nHead SHA: `%s`"}]]' "$head_sha" "$head_sha"
      ;;
    missing_coderabbit_one_probe)
      printf '[[{"user":{"login":"opencode-agent[bot]"},"state":"APPROVED","commit_id":"%s","body":"## Adversarial validation\\n\\n```json\\n{\\\"status\\\":\\\"passed\\\",\\\"probes\\\":[{\\\"outcome\\\":\\\"falsified\\\"}]}\\n```\\n\\nHead SHA: `%s`"}]]' "$head_sha" "$head_sha"
      ;;
    *)
      printf '[]'
      ;;
  esac
  exit 0
fi

if [ "$1" = "api" ] && [ "$2" = "--method" ] && [ "$3" = "POST" ] && [[ "$4" == repos/*/check-runs ]]; then
  if [ "${GH_SCENARIO:-pass}" = "check_publish_failure" ]; then
    printf 'check publication failed\n' >&2
    exit 1
  fi
  printf '{"id":999}'
  exit 0
fi

if [ "$1" = "api" ] && [ "$2" = "--method" ] && [ "$3" = "PATCH" ] && [[ "$4" == repos/*/check-runs/* ]]; then
  printf '{"id":999}'
  exit 0
fi

if [ "$1" = "api" ] && [[ "$args" == *repos/*/issues/42/comments* ]]; then
  if [[ "$args" == *"--jq"* ]]; then
    if [ "${GH_SCENARIO:-pass}" = "failed_existing" ] || [ "${GH_SCENARIO:-pass}" = "resolved_existing" ]; then
      printf '555\n'
    fi
    exit 0
  fi
  if [[ "$args" == *"--paginate"* ]]; then
    case "${GH_SCENARIO:-pass}" in
      coderabbit_blocking_comment)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"Pre-merge warning for 0123456789abcdef0123456789abcdef01234567"}]'
        ;;
      coderabbit_stale_blocking_comment)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"Pre-merge warning for older head"}]'
        ;;
      coderabbit_review_limit_comment)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"Review limit reached. This is an operational warning for 0123456789abcdef0123456789abcdef01234567; retry later."}]'
        ;;
      coderabbit_no_actionable_summary)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"No actionable comments were generated in the recent review. Reviewing files between base and 0123456789abcdef0123456789abcdef01234567.\\n\\n<details><summary>Walkthrough</summary>The gate distinguishes non-blocking summaries from substantive blocking language and potential issues.</details>"}]'
        ;;
      coderabbit_no_actionable_with_blocker)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"No actionable comments were generated in the recent review. Blocking issue remains on 0123456789abcdef0123456789abcdef01234567."}]'
        ;;
      coderabbit_approval_pending|missing_coderabbit_adversarial_approval_with_pending_notice|coderabbit_check_success_with_pending_notice|coderabbit_status_success_with_pending_notice|forged_check_pending_notice|forged_status_pending_notice)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"<!-- approval_notice_start -->\\nCodeRabbit has no unresolved comments, but it has not reviewed the latest commit. \\nCodeRabbit will approve the changes if it finds no blocking issues. <!-- {\\"headCommitId\\":\\"0123456789abcdef0123456789abcdef01234567\\"} -->\\n<!-- approval_notice_end -->"}]'
        ;;
      coderabbit_approval_pending_with_separate_blocking_warning)
        printf '[{"id":777,"user":{"login":"coderabbitai[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"<!-- approval_notice_start -->\\nCodeRabbit has no unresolved comments, but it has not reviewed the latest commit. \\nCodeRabbit will approve the changes if it finds no blocking issues. <!-- {\\"headCommitId\\":\\"0123456789abcdef0123456789abcdef01234567\\"} -->\\n<!-- approval_notice_end -->\\n\\nSeparately: Pre-merge blocking warning for 0123456789abcdef0123456789abcdef01234567."}]'
        ;;
      github_code_quality_blocking_comment)
        printf '[{"id":777,"user":{"login":"github-code-quality[bot]"},"created_at":"2026-05-19T00:01:00Z","body":"Potential issue for 0123456789abcdef0123456789abcdef01234567"}]'
        ;;
      *)
        printf '[]'
        ;;
    esac
    exit 0
  fi
  printf 'posted\n'
  exit 0
fi

if [ "$1" = "api" ] && [[ "$args" == *repos/*/pulls/42/comments* ]]; then
  case "${GH_SCENARIO:-pass}" in
    coderabbit_current_review_comment|coderabbit_resolved_current_review_comment)
      printf '[{"id":888,"user":{"login":"coderabbitai[bot]"},"commit_id":"0123456789abcdef0123456789abcdef01234567","original_commit_id":"old","created_at":"2026-05-19T00:01:00Z","body":"Potential issue on current head"}]'
      ;;
    github_code_quality_current_review_comment)
      printf '[{"id":888,"user":{"login":"github-code-quality[bot]"},"commit_id":"0123456789abcdef0123456789abcdef01234567","original_commit_id":"old","created_at":"2026-05-19T00:01:00Z","body":"Potential issue on current head"}]'
      ;;
    coderabbit_stale_review_comment)
      printf '[{"id":888,"user":{"login":"coderabbitai[bot]"},"commit_id":"old","original_commit_id":"old","created_at":"2026-05-19T00:01:00Z","body":"Potential issue on stale head"}]'
      ;;
    *)
      printf '[]'
      ;;
  esac
  exit 0
fi

if [ "$1" = "api" ] && [ "$2" = "--method" ] && [ "$3" = "PATCH" ] && [[ "$4" == repos/*/issues/comments/555 ]]; then
  printf 'patched\n'
  exit 0
fi

if [ "$1" = "pr" ] && [ "$2" = "merge" ]; then
  printf 'merge requested\n'
  exit 0
fi

printf 'unexpected gh invocation: %s\n' "$*" >&2
exit 99
FAKEGH
  chmod +x "$bin_dir/gh"
}

run_gate() {
  local scenario="$1"
  local temp_dir="$2"
  mkdir -p "$temp_dir/bin"
  make_fake_gh "$temp_dir/bin"
  set +e
  GH_LOG="$temp_dir/gh.log" \
  GH_STATE_DIR="$temp_dir" \
  GH_SCENARIO="$scenario" \
  PR_GOVERNANCE_RETRY_SLEEP_SECONDS="0" \
  PATH="$temp_dir/bin:$PATH" \
  GITHUB_REPOSITORY="owner/repo" \
  GH_TOKEN="fake" \
  EVENT_NAME="pull_request_target" \
  TARGET_PR_NUMBER="42" \
  DIRECT_PR_NUMBER="" \
  WORKFLOW_RUN_PR_NUMBER="" \
    bash "$script" > "$temp_dir/output.txt" 2>&1
  local status=$?
  set -e
  printf '%s\n' "$status" > "$temp_dir/status.txt"
}

assert_in_file() {
  local pattern="$1"
  local file="$2"
  grep -q -- "$pattern" "$file"
}

assert_not_in_file() {
  local pattern="$1"
  local file="$2"
  if grep -q -- "$pattern" "$file"; then
    printf 'unexpected pattern found in %s: %s\n' "$file" "$pattern" >&2
    printf '%s\n' '--- file contents ---' >&2
    sed -n '1,200p' "$file" >&2
    return 1
  fi
}

assert_exit_code() {
  local expected="$1"
  local temp_dir="$2"
  local actual
  actual="$(<"$temp_dir/status.txt")"
  if [ "$actual" != "$expected" ]; then
    printf 'expected exit code %s, got %s\n' "$expected" "$actual" >&2
    printf '%s\n' '--- output ---' >&2
    sed -n '1,200p' "$temp_dir/output.txt" >&2
    printf '%s\n' '--- gh log ---' >&2
    sed -n '1,200p' "$temp_dir/gh.log" >&2
    return 1
  fi
}

assert_no_comment_or_merge_for_pending_checks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate pending "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Waiting for 1 required check' "$temp_dir/output.txt"
  assert_in_file 'head_sha=0123456789abcdef0123456789abcdef01234567 -f status=in_progress' "$temp_dir/gh.log"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_transient_unknown_merge_state_is_retried() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate transient_unknown "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Merge state lookup attempt 1 of 4 returned UNKNOWN' "$temp_dir/output.txt"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_in_file 'conclusion=success' "$temp_dir/gh.log"
  assert_not_in_file 'Merge state is UNKNOWN; resolve conflicts' "$temp_dir/gh.log"
  assert_not_in_file 'conclusion=failure' "$temp_dir/gh.log"
}

assert_persistent_unknown_merge_state_waits_without_false_failure() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate persistent_unknown "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Merge state lookup attempt 3 of 4 returned UNKNOWN' "$temp_dir/output.txt"
  assert_in_file 'Merge state is still UNKNOWN after 4 attempts' "$temp_dir/output.txt"
  assert_in_file 'status=in_progress' "$temp_dir/gh.log"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
  assert_not_in_file 'conclusion=failure' "$temp_dir/gh.log"
}

assert_pr_merged_during_unknown_retry_exits_without_stale_gate() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate merged_during_unknown "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR state became MERGED during merge-state refresh' "$temp_dir/output.txt"
  assert_not_in_file 'check-runs' "$temp_dir/gh.log"
  assert_not_in_file 'issues/42/comments -f body=' "$temp_dir/gh.log"
  assert_not_in_file '--method PATCH repos/owner/repo/issues/comments' "$temp_dir/gh.log"
}

assert_head_change_during_evaluation_skips_stale_publication() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate head_changed_during_evaluation "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR head changed during gate evaluation from 0123456789abcdef0123456789abcdef01234567 to fedcba9876543210fedcba9876543210fedcba98' "$temp_dir/output.txt"
  assert_not_in_file '--method POST repos/owner/repo/check-runs' "$temp_dir/gh.log"
  assert_not_in_file '--method PATCH repos/owner/repo/check-runs' "$temp_dir/gh.log"
  assert_not_in_file 'issues/42/comments -f body=' "$temp_dir/gh.log"
  assert_not_in_file '--method PATCH repos/owner/repo/issues/comments' "$temp_dir/gh.log"
}

assert_closed_during_evaluation_skips_stale_publication() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate closed_during_evaluation "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR state became CLOSED during gate evaluation; skipping stale gate publication' "$temp_dir/output.txt"
  assert_not_in_file '--method POST repos/owner/repo/check-runs' "$temp_dir/gh.log"
  assert_not_in_file '--method PATCH repos/owner/repo/check-runs' "$temp_dir/gh.log"
  assert_not_in_file 'issues/42/comments -f body=' "$temp_dir/gh.log"
  assert_not_in_file '--method PATCH repos/owner/repo/issues/comments' "$temp_dir/gh.log"
}

assert_startup_failure_creates_marker_comment() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate startup_failure "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file "Required check \`Application CI\` is STARTUP_FAILURE" "$temp_dir/gh.log"
  assert_in_file '<!-- pr-governance:metadata-gate -->' "$temp_dir/gh.log"
  assert_in_file 'head_sha=0123456789abcdef0123456789abcdef01234567 -f status=completed -f conclusion=failure' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_failed_checks_create_marker_comment() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate failed "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is not ready' "$temp_dir/gh.log"
  assert_in_file '<!-- pr-governance:metadata-gate -->' "$temp_dir/gh.log"
  assert_in_file 'Application CI' "$temp_dir/gh.log"
  assert_not_in_file 'https://checks/app-ci' "$temp_dir/gh.log"
  assert_in_file 'head_sha=0123456789abcdef0123456789abcdef01234567 -f status=completed -f conclusion=failure' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_draft_pr_waits_without_false_failure() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate draft "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Draft PR: merge automation is paused.' "$temp_dir/gh.log"
  assert_in_file 'status=in_progress' "$temp_dir/gh.log"
  assert_not_in_file 'conclusion=failure' "$temp_dir/gh.log"
  assert_not_in_file 'PR governance metadata gate is not ready' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_existing_marker_comment_is_patched() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate failed_existing "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'api --method PATCH repos/owner/repo/issues/comments/555' "$temp_dir/gh.log"
  assert_not_in_file 'repos/owner/repo/issues/42/comments -f body' "$temp_dir/gh.log"
}

assert_resolved_marker_comment_is_updated_on_ready_gate() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate resolved_existing "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'api --method PATCH repos/owner/repo/issues/comments/555' "$temp_dir/gh.log"
  assert_in_file 'no current blocking failures remain' "$temp_dir/gh.log"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/gh.log"
  assert_not_in_file 'repos/owner/repo/issues/42/comments -f body' "$temp_dir/gh.log"
}

assert_coderabbit_pending_waits_without_hard_comment() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_pending "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Waiting for current-head CodeRabbit evidence' "$temp_dir/output.txt"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_robot_evidence_requires_publisher_and_clean_output() {
  local scenario temp_dir
  for scenario in forged_check forged_check_pending_notice forged_status forged_status_pending_notice missing_status_creator wrong_status_creator_type forged_clean_success; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"
    assert_exit_code 0 "$temp_dir"
    assert_in_file 'status=in_progress' "$temp_dir/gh.log"
    assert_not_in_file 'conclusion=success' "$temp_dir/gh.log"
    assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  done
  for scenario in coderabbit_success_with_warning coderabbit_skipped_with_warning; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"
    assert_exit_code 0 "$temp_dir"
    assert_in_file 'conclusion=failure' "$temp_dir/gh.log"
    assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  done
  for scenario in github_code_quality_check github_code_quality_status; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"
    assert_exit_code 0 "$temp_dir"
    assert_in_file 'conclusion=success' "$temp_dir/gh.log"
    assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  done
}

assert_clean_summaries_preserve_real_blockers() {
  local scenario temp_dir
  for scenario in clean_summary_success clean_summary_skipped clean_summary_neutral; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"
    assert_exit_code 0 "$temp_dir"
    assert_in_file 'conclusion=success' "$temp_dir/gh.log"
    assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  done
  for scenario in clean_summary_failure clean_without_skip_neutral mixed_summary_success mixed_summary_skipped mixed_summary_neutral qualified_summary_success qualified_but_success; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"
    assert_exit_code 0 "$temp_dir"
    assert_in_file 'conclusion=failure' "$temp_dir/gh.log"
    assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  done
}

assert_coderabbit_success_commit_status_completes_gate() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_status_success "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_in_file 'status=completed -f conclusion=success' "$temp_dir/gh.log"
  assert_not_in_file 'Waiting for current-head CodeRabbit evidence' "$temp_dir/output.txt"
}

assert_coderabbit_pending_commit_status_waits() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_status_pending "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Waiting for current-head CodeRabbit evidence' "$temp_dir/output.txt"
  assert_in_file 'status=in_progress' "$temp_dir/gh.log"
}

assert_coderabbit_failed_commit_status_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_status_failed "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'CodeRabbit commit status has a blocking conclusion' "$temp_dir/output.txt"
  assert_in_file 'status=completed -f conclusion=failure' "$temp_dir/gh.log"
}

assert_coderabbit_unknown_commit_status_fails_closed() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_status_unknown "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'CodeRabbit commit status has an unrecognized state' "$temp_dir/output.txt"
  assert_in_file 'status=completed -f conclusion=failure' "$temp_dir/gh.log"
}

assert_missing_coderabbit_waits_for_adversarial_opencode_approval() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate missing_coderabbit "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Waiting for current-head CodeRabbit evidence or a structured OpenCode App adversarial approval' "$temp_dir/output.txt"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_missing_coderabbit_accepts_exact_head_adversarial_opencode_approval() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate missing_coderabbit_with_adversarial_approval "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'accepted current-head OpenCode App adversarial approval' "$temp_dir/output.txt"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_in_file 'conclusion=success' "$temp_dir/gh.log"
}

assert_missing_coderabbit_adversarial_approval_overrides_pending_notice() {
  # With no CodeRabbit check-run, its issue-comment notice is not gate
  # evidence. The exact-head structured OpenCode approval satisfies the
  # documented fallback even while that notice remains present.
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate missing_coderabbit_adversarial_approval_with_pending_notice "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'accepted current-head OpenCode App adversarial approval' "$temp_dir/output.txt"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_in_file 'conclusion=success' "$temp_dir/gh.log"
}

assert_coderabbit_approval_pending_notice_does_not_hide_separate_blocking_warning() {
  # A CodeRabbit issue comment can legitimately carry both the boilerplate
  # approval-pending notice and a separate, genuine pre-merge blocking
  # warning in the same body. Excluding the whole comment from the
  # blocking-evidence scan whenever the pending-notice marker appears
  # anywhere in it would hide that second, real finding -- only the
  # marker-delimited span itself should be exempted.
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_approval_pending_with_separate_blocking_warning "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit issue comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_in_file 'conclusion=failure' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_missing_coderabbit_rejects_non_authoritative_opencode_evidence() {
  local scenario temp_dir
  for scenario in \
    missing_coderabbit_stale_approval \
    missing_coderabbit_actions_approval \
    missing_coderabbit_one_probe; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"

    assert_exit_code 0 "$temp_dir"
    assert_in_file 'Waiting for current-head CodeRabbit evidence or a structured OpenCode App adversarial approval' "$temp_dir/output.txt"
    assert_not_in_file 'accepted current-head OpenCode App adversarial approval' "$temp_dir/output.txt"
    assert_in_file 'status=in_progress' "$temp_dir/gh.log"
  done
}

assert_opencode_review_lookup_error_is_logged_but_not_published_verbatim() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate opencode_reviews_error "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'OpenCode review lookup failed' "$temp_dir/output.txt"
  assert_in_file 'SECRETVALUE' "$temp_dir/output.txt"
  assert_in_file 'OpenCode adversarial review evidence could not be read; see the workflow run log' "$temp_dir/gh.log"
  assert_not_in_file 'SECRETVALUE' "$temp_dir/gh.log"
  assert_in_file 'status=completed -f conclusion=failure' "$temp_dir/gh.log"
}

assert_completed_gate_check_is_republished_as_new_run() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate existing_gate_pending "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Waiting for 1 required check' "$temp_dir/output.txt"
  assert_in_file 'head_sha=0123456789abcdef0123456789abcdef01234567 -f status=in_progress' "$temp_dir/gh.log"
  assert_not_in_file 'api --method PATCH repos/owner/repo/check-runs/999' "$temp_dir/gh.log"
}

assert_coderabbit_failure_creates_marker_comment() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_failed "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit check has a blocking conclusion' "$temp_dir/gh.log"
  assert_in_file '<!-- pr-governance:metadata-gate -->' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_neutral_without_skip_evidence_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_neutral "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit check has a blocking conclusion' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_review_skipped_neutral_is_ready_without_merge() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_review_skipped "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
}

assert_coderabbit_skip_with_blocking_language_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_skip_with_warning "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit check has a blocking conclusion' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_unrecognized_required_check_state_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate unknown_state "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file "Required check \`Application CI\` is STALE" "$temp_dir/gh.log"
  assert_in_file 'status=completed -f conclusion=failure' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_pr_checks_error_is_not_published_verbatim() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate pr_checks_error "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Required check metadata could not be read; see the workflow run log' "$temp_dir/gh.log"
  assert_in_file 'SECRETVALUE' "$temp_dir/output.txt"
  assert_not_in_file 'SECRETVALUE' "$temp_dir/gh.log"
}

assert_invalid_pr_number_fails_closed_without_gh_calls() {
  local temp_dir status
  temp_dir="$(mktemp -d)"
  mkdir -p "$temp_dir/bin"
  make_fake_gh "$temp_dir/bin"
  : > "$temp_dir/gh.log"
  set +e
  GH_LOG="$temp_dir/gh.log" \
  GH_SCENARIO="pass" \
  PATH="$temp_dir/bin:$PATH" \
  GITHUB_REPOSITORY="owner/repo" \
  GH_TOKEN="fake" \
  EVENT_NAME="workflow_dispatch" \
  DIRECT_PR_NUMBER="$(printf '42\n::error::injected')" \
  TARGET_PR_NUMBER="" \
  WORKFLOW_RUN_PR_NUMBER="" \
    bash "$script" > "$temp_dir/output.txt" 2>&1
  status=$?
  set -e
  if [ "$status" = "0" ]; then
    printf 'expected non-zero exit for invalid PR number\n' >&2
    return 1
  fi
  assert_not_in_file '^::' "$temp_dir/output.txt"
  if [ -s "$temp_dir/gh.log" ]; then
    printf 'expected no gh invocations for invalid PR number\n' >&2
    return 1
  fi
}

assert_evaluation_error_publishes_gate_failure() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate graphql_error "$temp_dir"

  local actual
  actual="$(<"$temp_dir/status.txt")"
  if [ "$actual" = "0" ]; then
    printf 'expected non-zero exit when evaluation errors\n' >&2
    return 1
  fi
  assert_in_file 'PR governance metadata gate errored' "$temp_dir/gh.log"
  assert_in_file 'status=completed -f conclusion=failure' "$temp_dir/gh.log"
}

assert_coderabbit_blocking_issue_comment_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_blocking_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit issue comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_github_code_quality_blocking_issue_comment_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate github_code_quality_blocking_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit issue comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_stale_issue_comment_does_not_block() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_stale_blocking_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit issue comment' "$temp_dir/output.txt"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_review_limit_issue_comment_does_not_block() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_review_limit_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit issue comment' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit issue comment' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_no_actionable_summary_does_not_block() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_no_actionable_summary "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit issue comment' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit issue comment' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_no_actionable_summary_with_blocker_still_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_no_actionable_with_blocker "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit issue comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_success_overrides_stale_pending_notice() {
  local scenario temp_dir
  for scenario in coderabbit_check_success_with_pending_notice coderabbit_status_success_with_pending_notice; do
    temp_dir="$(mktemp -d)"
    run_gate "$scenario" "$temp_dir"
    assert_exit_code 0 "$temp_dir"
    assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
    assert_in_file 'conclusion=success' "$temp_dir/gh.log"
    assert_not_in_file 'Waiting for CodeRabbit to review the latest commit' "$temp_dir/output.txt"
    assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  done
}

assert_coderabbit_approval_pending_waits_without_blocking() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_approval_pending "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Waiting for CodeRabbit to review the latest commit' "$temp_dir/output.txt"
  assert_in_file 'status=in_progress' "$temp_dir/gh.log"
  assert_not_in_file 'Current-head CodeRabbit issue comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_current_review_comment_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_current_review_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit review comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_resolved_current_review_comment_does_not_block() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_resolved_current_review_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit review comment' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit review comment' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_truncated_review_thread_metadata_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate review_threads_truncated "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Review thread metadata was truncated; current resolution state could not be proven.' "$temp_dir/gh.log"
  assert_in_file '<!-- pr-governance:metadata-gate -->' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_truncated_review_thread_comments_metadata_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate review_thread_comments_truncated "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Review thread metadata was truncated; current resolution state could not be proven.' "$temp_dir/gh.log"
  assert_in_file '<!-- pr-governance:metadata-gate -->' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_github_code_quality_current_review_comment_blocks() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate github_code_quality_current_review_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Current-head CodeRabbit review comment has blocking warning/failure evidence' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_coderabbit_stale_review_comment_does_not_block() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate coderabbit_stale_review_comment "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file 'Current-head CodeRabbit review comment' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_changes_requested_creates_marker_comment() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate changes_requested "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'Review decision is CHANGES_REQUESTED' "$temp_dir/gh.log"
  assert_in_file '<!-- pr-governance:metadata-gate -->' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_passing_gate_is_metadata_only_without_merge() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate pass "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_in_file 'head_sha=0123456789abcdef0123456789abcdef01234567 -f status=completed -f conclusion=success' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
  assert_not_in_file 'checkout' "$temp_dir/gh.log"
  assert_not_in_file 'dismiss' "$temp_dir/gh.log"
  assert_not_in_file 'continue-on-error' "$temp_dir/gh.log"
}

assert_no_required_checks_waits_without_hard_comment() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate no_required_checks "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'no legacy required status contexts reported' "$temp_dir/output.txt"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_self_gate_failure_does_not_recurse() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate self_gate_failed "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'PR governance metadata gate is ready' "$temp_dir/output.txt"
  assert_not_in_file "Required check \`metadata-only gate evaluation\`" "$temp_dir/output.txt"
  assert_not_in_file 'issues/42/comments -f body' "$temp_dir/gh.log"
  assert_in_file 'conclusion=success' "$temp_dir/gh.log"
}

assert_existing_pr_head_check_is_updated() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate existing_gate "$temp_dir"

  assert_exit_code 0 "$temp_dir"
  assert_in_file 'api --method PATCH repos/owner/repo/check-runs/999' "$temp_dir/gh.log"
  assert_not_in_file 'api --method POST repos/owner/repo/check-runs' "$temp_dir/gh.log"
}

assert_check_publication_failure_fails_closed() {
  local temp_dir
  temp_dir="$(mktemp -d)"
  run_gate check_publish_failure "$temp_dir"

  assert_exit_code 1 "$temp_dir"
  assert_in_file 'check publication failed' "$temp_dir/output.txt"
  assert_not_in_file '^pr merge' "$temp_dir/gh.log"
}

assert_workflow_separates_controller_from_required_check() {
  local workflow="$repo_root/.github/workflows/pr-governance.yml"

	assert_in_file '^  checks: read$' "$workflow"
	assert_in_file '^      checks: write$' "$workflow"
	assert_in_file '^  pull-requests: read$' "$workflow"
	assert_in_file '^      pull-requests: write$' "$workflow"
	assert_in_file '^  issues: read$' "$workflow"
	assert_in_file '^      issues: write$' "$workflow"
  assert_in_file '^  pull_request_review:$' "$workflow"
  assert_in_file "github.event_name == 'pull_request_review'" "$workflow"
  assert_in_file '^    name: PR governance metadata controller$' "$workflow"
  assert_not_in_file '^    name: metadata-only gate evaluation$' "$workflow"
}

assert_current_head_check_lookup_uses_maximum_page_size() {
  assert_in_file 'check-runs?per_page=100' "$repo_root/scripts/ci/pr_governance_gate.sh"
}

assert_no_comment_or_merge_for_pending_checks
assert_transient_unknown_merge_state_is_retried
assert_persistent_unknown_merge_state_waits_without_false_failure
assert_pr_merged_during_unknown_retry_exits_without_stale_gate
assert_head_change_during_evaluation_skips_stale_publication
assert_closed_during_evaluation_skips_stale_publication
assert_startup_failure_creates_marker_comment
assert_failed_checks_create_marker_comment
assert_draft_pr_waits_without_false_failure
assert_existing_marker_comment_is_patched
assert_resolved_marker_comment_is_updated_on_ready_gate
assert_coderabbit_pending_waits_without_hard_comment
assert_robot_evidence_requires_publisher_and_clean_output
assert_clean_summaries_preserve_real_blockers
assert_coderabbit_success_commit_status_completes_gate
assert_coderabbit_pending_commit_status_waits
assert_coderabbit_failed_commit_status_blocks
assert_coderabbit_unknown_commit_status_fails_closed
assert_missing_coderabbit_waits_for_adversarial_opencode_approval
assert_missing_coderabbit_accepts_exact_head_adversarial_opencode_approval
assert_missing_coderabbit_adversarial_approval_overrides_pending_notice
assert_missing_coderabbit_rejects_non_authoritative_opencode_evidence
assert_opencode_review_lookup_error_is_logged_but_not_published_verbatim
assert_completed_gate_check_is_republished_as_new_run
assert_coderabbit_failure_creates_marker_comment
assert_coderabbit_neutral_without_skip_evidence_blocks
assert_coderabbit_review_skipped_neutral_is_ready_without_merge
assert_coderabbit_skip_with_blocking_language_blocks
assert_unrecognized_required_check_state_blocks
assert_pr_checks_error_is_not_published_verbatim
assert_invalid_pr_number_fails_closed_without_gh_calls
assert_evaluation_error_publishes_gate_failure
assert_coderabbit_blocking_issue_comment_blocks
assert_github_code_quality_blocking_issue_comment_blocks
assert_coderabbit_stale_issue_comment_does_not_block
assert_coderabbit_review_limit_issue_comment_does_not_block
assert_coderabbit_no_actionable_summary_does_not_block
assert_coderabbit_no_actionable_summary_with_blocker_still_blocks
assert_coderabbit_success_overrides_stale_pending_notice
assert_coderabbit_approval_pending_waits_without_blocking
assert_coderabbit_approval_pending_notice_does_not_hide_separate_blocking_warning
assert_coderabbit_current_review_comment_blocks
assert_coderabbit_resolved_current_review_comment_does_not_block
assert_truncated_review_thread_metadata_blocks
assert_truncated_review_thread_comments_metadata_blocks
assert_github_code_quality_current_review_comment_blocks
assert_coderabbit_stale_review_comment_does_not_block
assert_changes_requested_creates_marker_comment
assert_passing_gate_is_metadata_only_without_merge
assert_no_required_checks_waits_without_hard_comment
assert_self_gate_failure_does_not_recurse
assert_existing_pr_head_check_is_updated
assert_check_publication_failure_fails_closed
assert_workflow_separates_controller_from_required_check
assert_current_head_check_lookup_uses_maximum_page_size

printf 'test_pr_governance_gate: PASS\n'
