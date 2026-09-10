"""Exercise cancellation with task-owned command doubles, never a real database."""

import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_CANARY = "8b" * 32
SESSION_CANARY = "Cj9v+K7h/M4s" * 5

COMMAND_DOUBLE = r'''
import os
from pathlib import Path
import sys
import time

root = Path(__ROOT__)
blocked_stage = __BLOCKED_STAGE__
database_canary = __DATABASE_CANARY__
session_canary = __SESSION_CANARY__
arguments = sys.argv[1:]
command_name = Path(sys.argv[0]).name
if command_name == "openssl":
    print(database_canary if "-hex" in arguments else session_canary)
    raise SystemExit(0)
if command_name == "sleep":
    stage = "timer"
elif command_name == "docker":
    if arguments[arguments.index("--env-file") + 1] != "/dev/null":
        raise SystemExit(64)
    project = arguments[arguments.index("--project-name") + 1]
    if not project.startswith("naruon-test-"):
        raise SystemExit(64)
    stage = next(value for value in ("up", "port", "down") if value in arguments)
    project_file = root / "project"
    if stage == "up":
        project_file.write_text(project)
    elif project_file.read_text() != project:
        raise SystemExit(64)
elif arguments == ["scripts/migrate_db.py"]:
    stage = "migrate"
elif arguments[:2] == ["-m", "pytest"]:
    stage = "pytest"
    report = Path(arguments[arguments.index("--junitxml") + 1])
    report.write_text(f"<testsuites>{database_canary} {session_canary}</testsuites>\n")
    print(f"fixture credentials: {database_canary} {session_canary}", flush=True)
else:
    raise SystemExit(64)

if stage == "up":
    time.sleep(__STARTUP_DELAY__)

def _record_probe_event(event):
    """Append only task-owned event names and process identities."""
    with (root / "trace").open("a") as stream:
        stream.write(f"{event} {os.getpid()} {os.getpgrp()}\n")

_record_probe_event(stage)
if stage == "timer":
    time.sleep(20)
if stage == "port":
    print("127.0.0.1:49152")
if stage == blocked_stage:
    ready = root / "ready.tmp"
    ready.write_text(f"{os.getpid()} {os.getpgrp()}\n")
    ready.rename(root / "ready")
    deadline = time.monotonic() + 15
    while not (root / "release").exists():
        if time.monotonic() >= deadline:
            raise SystemExit(75)
        time.sleep(0.01)
if stage == "down":
    _record_probe_event("down_done")
'''


def _read_probe_trace(root):
    """Read controlled event names, child PIDs, and owned process groups."""
    trace_file = root / "trace"
    if not trace_file.exists():
        return []
    return [
        (event, int(pid), int(group))
        for event, pid, group in (
            line.split() for line in trace_file.read_text().splitlines()
        )
    ]


def _probe_is_running(pid):
    """Check a recorded child, reaping it directly when it belongs to this process."""
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _reap_probe(process, root):
    """Release doubles first so even a failing runner can reap its own pipeline."""
    (root / "release").touch()
    try:
        process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    # These groups come only from our new session and our generated doubles.
    groups = set()
    candidates = [(process.pid, process.pid)] + [
        (pid, group) for _, pid, group in _read_probe_trace(root)
    ]
    for pid, group in candidates:
        try:
            if os.getsid(pid) == process.pid and os.getpgid(pid) == group:
                groups.add(group)
        except ProcessLookupError:
            pass
    for group in groups:
        assert group > 1 and group != os.getpgrp()
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.communicate(timeout=3)
    child_pids = {pid for _, pid, _ in _read_probe_trace(root)}
    deadline = time.monotonic() + 3
    while (
        any(_probe_is_running(pid) for pid in child_pids)
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert not any(_probe_is_running(pid) for pid in child_pids), (
        "probe child was not reaped"
    )


@pytest.mark.parametrize(
    "blocked_stage, startup_delay, signal_window",
    [
        pytest.param("pytest", 0, "running", id="pytest"),
        pytest.param("down", 0, "running", id="down"),
        pytest.param("pytest", 6, "running", id="slow_startup"),
        pytest.param("pytest", 0, "before_pid", id="before_pid"),
    ],
)
def test_runner_sigterm_finishes_scoped_cleanup_and_sanitizes_reports(
    tmp_path, blocked_stage, startup_delay, signal_window
):
    """Require cancellation status, completed teardown, and sanitized evidence."""
    checkout = tmp_path / "checkout"
    runner = checkout / "scripts/ci/run_backend_postgres.sh"
    runner.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY_ROOT / "scripts/ci/run_backend_postgres.sh", runner)
    command_dir = tmp_path / "commands"
    command_dir.mkdir()
    python_double = checkout / "backend/.venv/bin/python"
    python_double.parent.mkdir(parents=True)
    source = COMMAND_DOUBLE.replace("__ROOT__", repr(str(tmp_path)))
    source = source.replace("__BLOCKED_STAGE__", repr(blocked_stage))
    source = source.replace("__DATABASE_CANARY__", repr(DATABASE_CANARY))
    source = source.replace("__SESSION_CANARY__", repr(SESSION_CANARY))
    source = source.replace("__STARTUP_DELAY__", repr(startup_delay))
    # A shell exec supports interpreter paths containing spaces and adds no child.
    # Python -c sets argv[0] to -c; restore the controlled executable name first.
    executable_source = (
        "#!/bin/sh\nexec "
        + shlex.quote(sys.executable)
        + " -I -c "
        + shlex.quote("import sys; sys.argv.pop(0)\n" + source)
        + ' "$0" "$@"\n'
    )
    for target in (
        command_dir / "docker",
        command_dir / "openssl",
        command_dir / "sleep",
        python_double,
    ):
        target.write_text(executable_source)
        target.chmod(0o700)
    probe_environment = {
        "PATH": str(command_dir) + os.pathsep + os.defpath,
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_ACTIONS": "false",
    }
    if signal_window == "before_pid":
        # Inject a real signal at the shell boundary without editing the runner.
        launch_probe = tmp_path / "launch_probe.sh"
        launch_probe.write_text(r"""
probe_launch_window() {
  if [[ ${log_name:-} == pytest.log && $1 == 'active_command_pid=$!' ]]; then
    local observation_end=$((SECONDS + 30))
    while [[ ! -f "$RUNNER_TEMP/ready" ]]; do
      [[ $SECONDS -lt $observation_end ]] || exit 76
      /bin/sleep 0.01
    done
    : > "$RUNNER_TEMP/launch_window"
    kill -TERM "$$"
  fi
}
set -T
trap 'probe_launch_window "$BASH_COMMAND"' DEBUG
""")
        probe_environment["BASH_ENV"] = str(launch_probe)
    process = subprocess.Popen(
        ["/bin/bash", str(runner)],
        cwd=checkout,
        env=probe_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        # Startup launches several interpreters; cancellation is timed only below.
        deadline = time.monotonic() + 30
        while not (tmp_path / "ready").exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail("runner did not reach the controlled blocking stage")
            time.sleep(0.01)
        evidence_dir = next(tmp_path.glob("naruon-postgres.*"))
        sanitized_before_down = not (evidence_dir / "pytest_raw.xml").exists()
        if signal_window == "running":
            process.send_signal(signal.SIGTERM)
        if blocked_stage == "down":
            # Give the handler a turn before allowing teardown to complete.
            time.sleep(0.1)
            (tmp_path / "release").touch()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pytest.fail("SIGTERM did not interrupt the foreground command")
        assert process.returncode == 143, "cancellation must remain a failed run"
        if signal_window == "before_pid":
            assert (tmp_path / "launch_window").exists(), (
                "launch signal was not injected"
            )
        trace = _read_probe_trace(tmp_path)
        events = [event for event, _, _ in trace]
        assert events.count("down") == 1 and events.count("down_done") == 1
        deadline = time.monotonic() + 3
        while (
            any(_probe_is_running(pid) for _, pid, _ in trace)
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert not any(_probe_is_running(pid) for _, pid, _ in trace), (
            "runner left a task-owned command or cleanup timer alive"
        )
        assert not (evidence_dir / "pytest_raw.xml").exists()
        report = (evidence_dir / "pytest.xml").read_text()
        outputs = stdout + stderr + report
        outputs += "".join(file.read_text() for file in evidence_dir.glob("*.log"))
        credentials_absent = all(
            canary not in outputs for canary in (DATABASE_CANARY, SESSION_CANARY)
        )
        assert credentials_absent, "a task-owned credential was not redacted"
        report_redacted = "[redacted] [redacted]" in report
        assert report_redacted, "sanitized report must retain redaction evidence"
        if blocked_stage == "down":
            assert sanitized_before_down, (
                "sanitize before potentially blocking teardown"
            )
    finally:
        _reap_probe(process, tmp_path)
