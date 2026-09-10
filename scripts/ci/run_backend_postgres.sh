#!/usr/bin/env bash
# The same disposable, migrated database lifecycle runs locally and in Actions.
set +x
set -euo pipefail
# Native job control gives each background command tree its own process group.
set -m
umask 077
active_command_pid=""
launch_in_progress=0
pending_signal_status=""

repository_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_command="$repository_dir/backend/.venv/bin/python"
[[ -x "$python_command" ]] || { echo 'Install backend dependencies in backend/.venv first.' >&2; exit 1; }
evidence_dir="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/naruon-postgres.XXXXXXXX")"
project_suffix="$(printf '%s' "${evidence_dir##*.}" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
compose_command=(docker compose --env-file /dev/null -f "$repository_dir/docker-compose.test.yml"
  --project-name "naruon-test-$project_suffix")
export TEST_POSTGRES_SECRET AUTH_SESSION_HMAC_SECRET
TEST_POSTGRES_SECRET="$(openssl rand -hex 32)"
AUTH_SESSION_HMAC_SECRET="$(openssl rand -base64 48)"
export PYTHONWARNINGS=error DISABLE_BACKGROUND_WORKERS=1

redact_evidence() {
  local output_line
  while IFS= read -r output_line || [[ -n "$output_line" ]]; do
    output_line="${output_line//"$TEST_POSTGRES_SECRET"/[redacted]}"
    output_line="${output_line//"$AUTH_SESSION_HMAC_SECRET"/[redacted]}"
    printf '%s\n' "$output_line"
  done
}

run_evidence() {
  local log_name="$1" command_status=0 cleanup_timer_pid=""
  shift
  launch_in_progress=1
  (set +m; "$@" 2>&1 | redact_evidence | tee "$evidence_dir/$log_name") &
  active_command_pid=$!
  launch_in_progress=0
  if [[ -n "$pending_signal_status" ]]; then
    cancel_execution "$pending_signal_status"
  fi
  if [[ "$log_name" == cleanup.log ]]; then
    # A stalled Docker daemon must not prevent cancellation/report finalization.
    (set +m; sleep 20; kill -KILL -- "-$active_command_pid" 2>/dev/null || true) &
    cleanup_timer_pid=$!
  fi
  while true; do
    wait "$active_command_pid" && { command_status=0; break; } || command_status=$?
    # Cleanup records later signals but keeps waiting for its bounded command.
    kill -0 "$active_command_pid" 2>/dev/null || break
  done
  active_command_pid=""
  if [[ -n "$cleanup_timer_pid" ]]; then
    kill -TERM -- "-$cleanup_timer_pid" 2>/dev/null || true
    wait "$cleanup_timer_pid" 2>/dev/null || true
  fi
  [[ $command_status -eq 0 ]] || return "$command_status"
  if grep -qiE 'timeout|fatal|warn|denied' "$evidence_dir/$log_name"; then
    echo 'Execution emitted a failure-class diagnostic.' >&2
    return 1
  fi
}

cancel_execution() {
  local signal_status="$1"
  # Record ownership before cancellation can enter teardown and launch another group.
  if [[ "$launch_in_progress" == 1 ]]; then
    pending_signal_status="$signal_status"
    return
  fi
  pending_signal_status=""
  trap '' INT TERM
  if [[ -n "$active_command_pid" ]]; then
    # Cancellation is not clean test evidence; stop the whole owned command tree.
    kill -TERM -- "-$active_command_pid" 2>/dev/null || true
    kill -KILL -- "-$active_command_pid" 2>/dev/null || true
    wait "$active_command_pid" 2>/dev/null || true
    active_command_pid=""
  fi
  exit "$signal_status"
}

cleanup_database() {
  local run_status=$? cleanup_status
  trap - EXIT
  trap 'run_status=130' INT
  trap 'run_status=143' TERM
  set +e
  if [[ -f "$evidence_dir/pytest_raw.xml" ]]; then
    # Delete only this invocation's raw report after its redacted copy exists.
    if redact_evidence < "$evidence_dir/pytest_raw.xml" > "$evidence_dir/pytest.xml"; then
      rm -- "$evidence_dir/pytest_raw.xml" || run_status=1
    else
      run_status=1
    fi
  fi
  run_evidence cleanup.log "${compose_command[@]}" down --volumes --timeout 10
  cleanup_status=$?
  [[ $run_status -ne 0 ]] || run_status=$cleanup_status
  printf 'Backend evidence: %s\n' "$evidence_dir"
  exit "$run_status"
}
trap cleanup_database EXIT
trap 'cancel_execution 130' INT
trap 'cancel_execution 143' TERM

if [[ "${GITHUB_ACTIONS:-false}" == true ]]; then
  printf '::add-mask::%s\n' "$TEST_POSTGRES_SECRET" "$AUTH_SESSION_HMAC_SECRET"
  printf 'evidence_dir=%s\n' "$evidence_dir" >> "$GITHUB_OUTPUT"
fi

run_evidence database.log "${compose_command[@]}" up -d --wait --wait-timeout 60
run_evidence address.log "${compose_command[@]}" port test_postgres 5432
database_address="$(< "$evidence_dir/address.log")"
[[ "$database_address" =~ ^127\.0\.0\.1:[0-9]+$ ]] || { echo 'Unexpected test database address.' >&2; exit 1; }
export DATABASE_URL="postgresql+asyncpg://postgres:${TEST_POSTGRES_SECRET}@${database_address}/postgres"
# Bootstrap/test transport only: exclude inherited provider/replica/live settings
# and implicit operator dotenv files without changing HOME or runtime auth.
python_environment=(env -i "PATH=$PATH" "DATABASE_URL=$DATABASE_URL"
  "AUTH_SESSION_HMAC_SECRET=$AUTH_SESSION_HMAC_SECRET" NARUON_ENV_FILE=/dev/null
  PYTHONWARNINGS=error DISABLE_BACKGROUND_WORKERS=1)
cd "$repository_dir/backend"
run_evidence migrate_fresh.log "${python_environment[@]}" "$python_command" scripts/migrate_db.py
run_evidence migrate_repeat.log "${python_environment[@]}" "$python_command" scripts/migrate_db.py
run_evidence pytest.log "${python_environment[@]}" "$python_command" -m pytest -q -ra -W error -p ci_postgres_gate \
  --junitxml "$evidence_dir/pytest_raw.xml" "$@"
