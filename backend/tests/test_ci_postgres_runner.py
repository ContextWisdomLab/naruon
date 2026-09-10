"""Execute the CI runner's lifecycle; real database evidence is separate."""

import os
import importlib
from pathlib import Path
import shutil
import shlex
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
pytest_plugins = ["pytester"]


@pytest.mark.parametrize(
    "module_name, helper_name",
    [
        ("test_workspace_document_migration", "_run_migrations"),
        ("test_email_read_state_migration_postgres", "_run_migrations"),
        ("test_email_read_state_migration_postgres", "_run_downgrade"),
    ],
)
def test_migration_children_exclude_implicit_operator_files(
    monkeypatch, module_name, helper_name
):
    """Intercept dispatch: losing the explicit selector must fail before any child runs."""
    helper_module = importlib.import_module(f".{module_name}", __package__)
    selected_sources = []

    def child_boundary(command, **options):
        """Record only the non-sensitive selector; never spawn or read dotenv."""
        selected_sources.append(options["env"].get("NARUON_ENV_FILE"))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(helper_module.subprocess, "run", child_boundary)
    getattr(helper_module, helper_name)(
        "postgresql+asyncpg://test.invalid/test", "base"
    )
    assert selected_sources == ["/dev/null"]


@pytest.mark.parametrize(
    "failure_stage", ["", "up", "migrate", "pytest", "down", "diagnostic", "bad_address"]
)
def test_runner_preserves_failures_and_cleans_only_its_project(tmp_path, failure_stage):
    """Command doubles exercise ordering and cleanup, not PostgreSQL correctness."""
    runner_path = REPOSITORY_ROOT / "scripts/ci/run_backend_postgres.sh"
    assert runner_path.is_file(), "Application CI must have an executable DB path"
    repository_dir = tmp_path / "checkout"
    (repository_dir / "scripts/ci").mkdir(parents=True)
    (repository_dir / "backend/.venv/bin").mkdir(parents=True)
    shutil.copy2(runner_path, repository_dir / "scripts/ci/run_backend_postgres.sh")
    command_dir = tmp_path / "commands"
    command_dir.mkdir()
    trace_path = tmp_path / "command_trace"
    command_source = """#!/usr/bin/env bash
set -euo pipefail
COMMAND_TRACE=__TRACE_PATH__
FAILURE_STAGE=__FAILURE_STAGE__
if [[ "${0##*/}" == docker ]]; then
  [[ "$*" == *'--env-file /dev/null'* ]]
  [[ "$*" == *'--project-name naruon-test-'* ]]
  command_stage=down
  [[ " $* " != *' up '* ]] || command_stage=up
  [[ " $* " != *' port '* ]] || command_stage=port
else
  [[ -n "$DATABASE_URL" && "$DATABASE_URL" == *'@127.0.0.1:49152/postgres' ]]
  [[ "$NARUON_ENV_FILE" == /dev/null ]]
  [[ -z "${READONLY_DATABASE_URL+x}" && -z "${OPENAI_API_KEY+x}" ]]
  database_secret="${DATABASE_URL#postgresql+asyncpg://postgres:}"
  database_secret="${database_secret%@*}"
  command_stage=migrate
  if [[ " $* " == *' pytest '* ]]; then
    command_stage=pytest
    printf 'test credentials: %s %s\\n' "$database_secret" "$AUTH_SESSION_HMAC_SECRET"
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == --junitxml ]]; then
        printf '<testsuites>%s %s</testsuites>\\n' "$database_secret" "$AUTH_SESSION_HMAC_SECRET" > "$2"
        break
      fi
      shift
    done
    if [[ "$FAILURE_STAGE" == diagnostic ]]; then printf 'Warn: lifecycle probe\\n'; fi
  fi
fi
printf '%s\\n' "$command_stage" >> "$COMMAND_TRACE"
if [[ "$command_stage" == port ]]; then
  if [[ "$FAILURE_STAGE" == bad_address ]]; then printf '0.0.0.0:49152\\n'; else printf '127.0.0.1:49152\\n'; fi
fi
if [[ "$command_stage" == "$FAILURE_STAGE" ]]; then exit 23; fi
"""
    command_source = command_source.replace("__TRACE_PATH__", shlex.quote(str(trace_path)))
    command_source = command_source.replace("__FAILURE_STAGE__", shlex.quote(failure_stage))
    for executable_path in (
        command_dir / "docker",
        repository_dir / "backend/.venv/bin/python",
    ):
        executable_path.write_text(command_source, encoding="utf-8")
        executable_path.chmod(0o700)
    result = subprocess.run(
        ["bash", str(repository_dir / "scripts/ci/run_backend_postgres.sh")],
        env={
            **os.environ,
            "PATH": f"{command_dir}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "READONLY_DATABASE_URL": "must-not-reach-child",
            "OPENAI_API_KEY": "unit-only-must-not-reach-child",
            "GITHUB_ACTIONS": "false",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    command_trace = trace_path.read_text(encoding="utf-8").splitlines()
    expected_trace = ["up", "port", "migrate", "migrate", "pytest", "down"]
    if failure_stage in ("up", "migrate"):
        expected_trace = expected_trace[: expected_trace.index(failure_stage) + 1]
        expected_trace.append("down")
    if failure_stage == "bad_address":
        expected_trace = ["up", "port", "down"]
    assert command_trace == expected_trace, result.stdout + result.stderr
    expected_status = 23 if failure_stage else 0
    if failure_stage in ("diagnostic", "bad_address"):
        expected_status = 1
    assert result.returncode == expected_status
    if "pytest" in command_trace:
        assert "test credentials: [redacted] [redacted]" in result.stdout
        evidence_dir = next(tmp_path.glob("naruon-postgres.*"))
        assert (evidence_dir / "pytest.xml").read_text() == (
            "<testsuites>[redacted] [redacted]</testsuites>\n"
        )
        assert not (evidence_dir / "pytest_raw.xml").exists()


def test_postgres_skip_is_a_failure_only_in_the_ci_plugin(pytester):
    """Run real pytest reports: ordinary optional skips remain distinguishable."""
    import ci_postgres_gate

    pytester.makeini(
        "[pytest]\nasyncio_default_fixture_loop_scope = function\n"
        "markers =\n    postgres: actual database evidence\n"
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.postgres
        def test_database_missing():
            pytest.skip("database unavailable")

        def test_optional_feature():
            pytest.skip("optional feature unavailable")

        @pytest.mark.postgres
        def test_database_ready():
            assert 2 + 2 == 4
        """
    )
    result = pytester.runpytest("-q", plugins=[ci_postgres_gate])
    result.assert_outcomes(failed=1, passed=1, skipped=1)
    result.stdout.fnmatch_lines(["*PostgreSQL evidence cannot be skipped*"])


@pytest.mark.parametrize("skip_mode", ["collection", "xfail", "xfail_run", "xpass"])
def test_ci_cannot_pass_without_executing_required_database_tests(pytester, skip_mode):
    """Collection skips and expected failures must produce a nonzero process status."""
    import ci_postgres_gate

    pytester.makeini(
        "[pytest]\nasyncio_default_fixture_loop_scope = function\n"
        "markers =\n    postgres: actual database evidence\n"
    )
    if skip_mode == "collection":
        database_source = (
            "import pytest\npytestmark = pytest.mark.postgres\n"
            "pytest.skip('database unavailable', allow_module_level=True)\n"
        )
    else:
        should_run = skip_mode != "xfail"
        database_source = (
            "import pytest\n@pytest.mark.postgres\n"
            f"@pytest.mark.xfail(run={should_run}, reason='database unavailable')\n"
            f"def test_database_query():\n    assert {skip_mode == 'xpass'}\n"
        )
    pytester.makepyfile(test_database=database_source, test_other="def test_ok(): pass")
    result = pytester.runpytest("-q", plugins=[ci_postgres_gate])
    assert result.ret != pytest.ExitCode.OK
    result.assert_outcomes(
        errors=1 if skip_mode in ("collection", "xfail") else 0,
        failed=1 if skip_mode in ("xfail_run", "xpass") else 0,
        passed=0 if skip_mode == "collection" else 1,
    )
