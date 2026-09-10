# Application CI migrated PostgreSQL prerequisite

Status: Proposed; existing CI owner #1562, parent governance #1531. No
protected integration or hosted database evidence is established by this record.

## Baseline and dependency decision (2026-09-06)

Exact starting head `bc91b36dec70c14e0cde526e2330638f5e0ce352` runs backend
pytest without provisioning PostgreSQL or invoking Alembic. The focused
`test_search_postgres.py` baseline exited 0 with all five tests skipped because
the default local database rejected the test role. No search assertions ran.

An isolated, digest-pinned real PostgreSQL run then failed during revision
`0001_initial_control_plane`: `relation "emails" does not exist`, at
`CREATE INDEX IF NOT EXISTS ix_emails_owner_date ON emails ...`.
The process exited 1 and its task-only container/network were removed. This
failure happens before tests and is not evidence that database tests passed.

Before committing, select migration owner #1503 at
`19d5860bc27e860acba940390f5792721cd99e5e`, including #1565's declared
Starlette/httpx2 dependency. Integrate its full delta by a normal merge while
retaining #1562/#1531/#1554 ancestry; never copy sibling migration files or
substitute ORM-only bootstrap. This joins in-flight prerequisites, not an
immutable external service contract. A changed head needs fresh checks/review.

Local runtime repair #1317 at `af362d58190c0bf2ed122d718473fe3c2bd503c4`
demonstrates the shared need but its 242-test result is not this CI owner's
GREEN. CI provisioning, migration, full pytest, failure propagation, credential
redaction and task-scoped cleanup must be verified on this owner's own head.

## Existing boundary and rejected alternatives

The live-E2E Compose stack builds model services and runs bootstrap/seed jobs;
reusing the whole stack would add unrelated provider/environment requirements.
A standalone test-only PostgreSQL Compose service can be used by the same
repository-owned runner locally and in CI. It must keep loopback-only access,
generated per-invocation credentials, explicit writable tmpfs, non-root UID,
fresh/repeated Alembic execution, and cleanup limited to its unique project.

Registry inspection confirmed image index
`pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b`
contains both linux/amd64 and linux/arm64 manifests. The local image inspection
showed arm64 but did not prove the index was arm64-only; no architecture
fallback or mutable image tag is necessary.

DeepWiki incorrectly inferred migration execution from fixture/source-presence
tests. The exact workflow and actual failed install contradict that inference.
Context7 was quota-limited; official Compose CLI/service documentation is the
fallback. A ready DB alone is not a migrated schema or a passing test suite.

## Implemented candidate and verification

`scripts/ci/run_backend_postgres.sh` drives the one test-only service in
`docker-compose.test.yml`, runs `backend/scripts/migrate_db.py` twice, and then
executes full pytest with `-p ci_postgres_gate -W error`. The plugin changes
PostgreSQL-marked skips/expected failures into failures, clears expected-failure
metadata that otherwise leaves the process exit code zero, and rejects skipped
collection before a whole module can hide its markers. It does not represent
unconfigured live API tests as executed, or change application authentication.
Compose startup's 60-second health wait is a database startup bound, not an
application/model timeout. No model routing, provider pool or central required
workflow was changed. Shell and installed pytest APIs suffice; no new package
or test framework was introduced.

Application CI installs both existing hash-locked core/Noema requirements into
`backend/.venv`. Locally use the `uv pip install --python backend/.venv/bin/python`
command in `CLAUDE.md` to reproduce that environment: the separate uv core lock
alone does not install the optional Noema dependency or prove lock parity.

Candidate execution on 2026-09-06 installed fresh history through
`0019_email_read_state_repair`, then repeated the upgrade without changes.
The first complete suite returned **1859 passed, 2 skipped, zero failures/errors
in 26.38 seconds**. The two skips were precisely
`tests/live/test_live_api_sequence.py` cases requiring `LIVE_BASE_URL`;
all ten tests in the search/legacy-document/read-state PostgreSQL files ran.
These are database/API correctness fixtures, not representative customer mail,
provider calls, browser cookie/proxy evidence, deployment or p95 measurements.
This initial receipt predates final commit; the PR's current-head evidence block
must identify the final SHA, JUnit digest, denominator and cleanup result.

Test-first evidence: six new command-lifecycle/plugin tests initially failed
because the runner and plugin were absent. During implementation the teardown
failure test caught a swallowed exit code; the runner now preserves a command
failure even when cleanup runs with shell errexit disabled. Real nested pytest
reports verify database-skip failure and unrelated optional-skip preservation.
Additional probes cover unsafe advertised DB addresses, failure-class output,
and generated credential redaction in logs/JUnit. Command doubles establish
runner behavior, not database migration correctness.

Premortem exposed a separate bootstrap gap: Compose's `--env-file /dev/null`
does not control Python's implicit operator dotenv chain or inherited replica/
provider settings. The existing `core.env_paths.operator_env_file_paths` now
honors the already established `NARUON_ENV_FILE` bootstrap selector, shared by
Settings and `start_backend` preflight. Without a selector, existing local
defaults remain; an explicit missing path never falls back to them. This is a
bootstrap transport choice, not a new runtime credential source or KV bypass.
The runner's Python children receive an explicit minimal environment and
`NARUON_ENV_FILE=/dev/null`. The production default and signature/tenant
authorization semantics are unchanged.

Negative configuration tests use controlled file-reader probes and key-only
assertions: never read an operator file to demonstrate that it must not be read,
or assert against whole credential dictionaries that pytest may render on
failure. Command probes inject unusable replica/provider sentinel values and
verify their absence in children. No provider endpoint is contacted to prove
this exclusion. The earlier 1859-test receipt does not establish this later
environment repair; rerun the complete isolated command on the final head.

After bootstrap isolation and the review repairs, the full local candidate ran
**1871 passed, 2 live-only skips, zero failures/errors in 32.63 seconds**, with
fresh/repeated migrations and completed task-only cleanup. Its denominator
includes the real subprocess signal tests. Local macOS execution does not prove
the Linux Actions run; obtain a terminal receipt for the unchanged committed
head before protected landing. Local dependency installation used the two
hash-pinned requirements files, including optional Noema, not only the uv core
lock. No coverage-percentage or real customer workload claim is made.

Only the generated Compose project is removed. A raw per-run JUnit file is
deleted after successful redaction; no repository/customer data is deleted.
Independent review reproduced deferred shell cancellation and interruption
during teardown leaving raw reports. Commands now run in task-owned process
groups with interruptible waits. Cancellation stops that group and retains
exit 130/143; report sanitization precedes teardown. Cleanup records subsequent
signals while finishing, has a 20-second command bound and a 10-second Docker
stop grace, and reaps its timer group. No application or model limit is added.
Redacted logs/JUnit are retained, and Actions uploads them with `always()` after
the runner produces its output directory. The upload action's v7.0.1 tag was
resolved to `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` before pinning.
Remaining acceptance: exact-head hosted Application CI, independent review,
protected integration and separately configured live/API/browser evidence.

## Merge-ref dependency follow-up (2026-09-06)

After pushing `ef858172152615d54b393ea3ca5748ab2c4e03db`, GitHub merge ref
`a7d2d409d146a134817df4c258ece4ab8e171508` has the identical tree
`67dab67ba5534258c690a110724d9ef6da503623`. The refreshed Trivy HIGH/CRITICAL,
fixable vulnerability/misconfiguration scan exits 1 for `js-yaml@4.3.0` in
`frontend/pnpm-lock.yaml` (GHSA-5p4m-2wfm-xmqj); no HIGH/CRITICAL
misconfiguration is found. A separate secret scan exits zero, not a substitute
for this dependency gate.

Before integration, the existing dependency owner #1571 was verified at
`c3cf4efc478a264a0a010df82d1ea90b48776610` on protected `develop`. Its complete
three-file delta pins patched `4.3.1` using the existing pnpm workspace override,
regenerates the lock, and adds two executable lock/source conformance tests.
Choose a normal prerequisite merge, preserving its lock provenance and test;
do not duplicate the patch, suppress the finding or close its owner. This
changes development tooling, not a shipped browser YAML parser. Re-run frozen
installation, frontend tests/lint, full backend evidence and the new merge-tree
security scan. Earlier-head receipts do not transfer.

The first combined candidate installed the frozen lock and passed all 439
frontend tests and lint, but `pnpm exec tsc --noEmit` exited 2 with TS1503 at
`frontend/src/dependency-lock.security.test.ts:30`: the named capture requires
ES2018 while the product targets ES2017. Record that failed candidate rather
than calling its Vitest pass complete. Repair the existing #1571 test with an
equivalent numbered capture; do not raise the product target or rewrite the
patched lock. Preserve the original prerequisite merge, then integrate that
owner's ordinary child commit and revalidate the combined tree.

## Nested migration isolation repair (2026-09-06)

Shared-send consumer #1417 exposed a remaining boundary at CI owner head
`4d2e4abc2c369d5e85bced4027b6f81857721ea2`. The workspace migration helper and
the email-read-state upgrade/downgrade helpers construct new subprocess
environments containing only a database URL and generated signing material.
Python replaces the inherited environment when `env` is supplied; consequently
all three calls lose the parent's explicit `NARUON_ENV_FILE=/dev/null` selector
and can re-enable implicit operator dotenv lookup. The parent runner's clean
environment alone cannot prove nested isolation (Python Software Foundation,
n.d.). Do not execute those unsafe children to demonstrate the defect.

`test_migration_children_exclude_implicit_operator_files` intercepts the actual
three helpers' subprocess boundary, records only the selector, and never starts
the child or reads a dotenv file. After correcting the test's relative package
import, all three cases failed with `[None]` instead of `['/dev/null']`.
Adding the explicit selector at each child launch made all three pass. This
is test/bootstrap configuration; no application defaults, secrets, tenant
authorization, migration DDL, or dependency pins change. A generic environment
wrapper is unnecessary for these three concrete callers.

Re-run the entire real-database runner, including its nested migration tests,
before treating this repair as local GREEN. Record exact head, denominator,
JUnit hash and completed task-only cleanup in the PR. Consumer #1417 must
inherit the complete ordinary child commit, not copy these helper edits.
Earlier-head security scans remain historical until their merge ref is rescanned.

## Signal-probe startup observation repair (2026-09-06)

Consumer #1417 at `56025b17d752b8fbe2c759d9420876a73e26d51c`, inheriting CI
owner `30d8476b5fa1d4379684acaf2f334414597e97c4`, failed its immutable-head
full rerun before SIGTERM was sent: `runner did not reach the controlled
blocking stage` at `test_ci_postgres_signals.py:188`. The result was 1888 passed,
one failure and two live-only skips. The failed JUnit SHA-256 is
`27c1ac50cb7073bdb5299170618e6ee204ad437199658285f68cb44621e593bb`.
Retained task-only trace subsequently reached `pytest`, `down`, and `down_done`;
its ready marker was later than the test's teardown release marker. Thus the
five-second pre-signal observation expired during startup, not during the
cancellation assertion. A passing isolated rerun does not erase this failure.

A new six-second controlled startup-delay case reproduces the same RED without
real Docker, a database or operator files. Give only pre-signal startup a
30-second observation bound; several fresh interpreter launches are setup,
not the behavior being timed. Keep the existing five-second post-SIGTERM wait,
exit 143, exactly one completed teardown, redaction, and no surviving owned
child/timer assertions unchanged. This addresses an overly strict timing
precondition (pytest Development Team, n.d.-c), not an application performance
target. The runner shell, deployment/model timeouts and cleanup bounds do not
change. The new delayed case remains in the complete suite; no skip, automatic
retry, fixture warm-up or failure suppression is added. Revalidate the CI owner
and normally inherit its full child in #1417 before accepting their new heads.

Focused reproduction uses the repository conftest (the migration-helper probes
import application settings); `--noconftest` is valid for the standalone signal
file but makes the combined invocation fail on missing test configuration.
Keep implicit operator files excluded in either case:

```sh
env -i PATH="$PATH" NARUON_ENV_FILE=/dev/null backend/.venv/bin/python -m pytest \
  -q -W error backend/tests/test_ci_postgres_signals.py backend/tests/test_ci_postgres_runner.py
```

## Cancellation before process ownership is recorded (2026-09-06)

At owner `b2e98a52588db72e501c0843b33816e2e5bc698b`, `run_evidence`
starts a background pipeline before assigning `active_command_pid`. A SIGTERM
in that interval enters `cancel_execution` with no recorded PID. Teardown can
finish while the original command group remains alive. The caller is the same
runner used by `.github/workflows/app-ci.yml`; consumers must inherit the owner
repair, not copy the shell function.

The `before_pid` signal case runs an unchanged copy of the actual runner with
task-owned command doubles and a task-owned `BASH_ENV` DEBUG hook. It waits for
the real child process to reach its controlled barrier, then sends SIGTERM
immediately before PID assignment. Assertions cover process exit, completed
cleanup, no surviving recorded children/timer, and redacted reports. The first
probe used unsupported `BASHPID` on macOS Bash 3.2 and was invalid; replacing it
with the parent shell's `$$` produced the meaningful RED: the five-second
communication assertion failed while `down` and `down_done` were already in
the trace. Test teardown released and reaped its own processes.

The fix records a pending signal during only the launch/PID-registration
interval and handles it once ownership is known. It clears pending state before
entering teardown. Existing process-group termination, cancellation status,
report sanitization and the 20-second cleanup bound remain unchanged. The new
case passes, followed by all 19 runner/signal tests, ShellCheck and Ruff. A
generic process manager, ignored signals, longer cleanup bound, or per-caller
workaround would not address this ownership interval. Bash's documented
asynchronous `wait`/trap behavior informs the design, but the boundary result
comes from the executed repository regression, not the manual alone (Free
Software Foundation, 2002).

This is **not the established cause of the earlier exit137 incident**. At
unchanged `b2e9`, the full test phase passed 1875 cases with two live-only skips;
consumer `dc8b53d38ddf80b726b5dc6cff1d21f2c25d293e` passed 1890 with the same
two skips. Both runners then exited137 during Docker removal. That is consistent
with the cleanup watchdog, but retained logs do not prove signal attribution or
why the daemon operation was slow. The later unchanged-owner diagnostic passed
18 cases and completed real migration/cleanup with exit0 (JUnit SHA-256
`e3d0ebafe18391ba49f9159505f0c1672e4c67d7c530ddcf126534962b0ead17`);
it does not replace either failed full lifecycle. Keep the incident open, retain
the original failed receipts in the PR, and revalidate complete owner/consumer
lifecycles plus their hosted gates on each new exact head.

## References

Free Software Foundation. (2002). *Signals*. In *Bash reference manual*
(Version 2.05a). https://ftp.gnu.org/pub/old-gnu/Manuals/bash-2.05a/html_node/bashref_51.html

Python Software Foundation. (n.d.). *subprocess—Subprocess management*.
Python 3.14 documentation. Retrieved September 6, 2026, from
https://docs.python.org/3.14/library/subprocess.html

Docker, Inc. (n.d.). *Docker compose up*. Retrieved September 6, 2026, from
https://docs.docker.com/reference/cli/docker/compose/up/

Docker, Inc. (n.d.). *Define services in Docker Compose*. Retrieved September
6, 2026, from https://docs.docker.com/reference/compose-file/services/

Docker, Inc. (n.d.). *Docker compose down*. Retrieved September 6, 2026, from
https://docs.docker.com/reference/cli/docker/compose/down/

pytest Development Team. (n.d.-a). *API reference*. Retrieved September 6, 2026,
from https://docs.pytest.org/en/stable/reference/reference.html#pytest.hookspec.pytest_runtest_makereport

pytest Development Team. (n.d.-b). *How to use skip and xfail to deal with tests
that cannot succeed*. Retrieved September 6, 2026, from
https://docs.pytest.org/en/stable/how-to/skipping.html

pytest Development Team. (n.d.-c). *Flaky tests*. Retrieved September 6, 2026,
from https://docs.pytest.org/en/stable/explanation/flaky.html

GitHub. (n.d.). *Upload a build artifact* (Version 7.0.1) [Computer software].
https://github.com/actions/upload-artifact/tree/v7.0.1

nodeca. (2026, July 31). *JS-YAML: Quadratic CPU consumption in !!omap
resolution (3.x and 4.x)* [Security advisory]. GitHub.
https://github.com/advisories/GHSA-5p4m-2wfm-xmqj
