# Shared-send migrated PostgreSQL evidence

Status: Proposed; existing source owner [PR #1417](https://github.com/ContextualWisdomLab/naruon/pull/1417).
Local checks do not establish protected integration, delivery, or performance.

## Problem, dependency and preserved histories

Starting head `a9f334a442538b666e03e694731745d8aab4b45a` uses a PostgreSQL
transaction-scoped advisory lock, database clock, rolling 10-attempt/60-second
quota, and user/organization/workspace scope. However, its database smoke
creates ORM tables, reduces the quota to one and injects time. Its one-slot
pool regression uses a semaphore double. Neither proves the migrated runtime
or real pool/cancellation behavior.

Before committing, claim the existing owner and normally merge complete CI
prerequisite #1562 at `4d2e4abc2c369d5e85bced4027b6f81857721ea2`, including
#1503/#1565/#1571, rather than copy a runner or migration. This produced a real
fresh-install RED: Alembic reported two heads, `0018_security_audit_events`
and `0019_email_read_state_repair`. Preserve both histories with
`0020_merge_send_registry`, a no-DDL merge revision. Do not delete either parent,
stamp over missing work, switch the deployment target to a partial branch, or
claim an unreleased foundation is available. Only CHANGELOG had a textual merge
conflict; both entries were retained. Keep this PR Draft on the CI prerequisite.

Alembic's merge-node mechanism makes both parent paths prerequisites of one
head (Bayer, n.d.). The same runner now completes fresh and repeated upgrades.
This is repository-local stack integration, not permission to consume source
from an external service or bypass an immutable release contract.

## Behavioral checks and failure analysis

The updated database fixture reads the migrated audit table without creating
it. New tests use the production quota and database time: 80 concurrent attempts
across four scopes produce 10 allowed reservations and one durable quota event
per scope; the real 61-second wait verifies expiration without accelerating the
clock. Each dimension changes independently, so a missing user, organization or
workspace predicate cannot borrow another dimension's isolation.

A separate one-slot engine queues behind a real advisory lock. The test waits
until PostgreSQL observes that wait, cancels the task, verifies no checked-out
connection remains and confirms a subsequent attempt creates exactly one
reservation. Initial observation failed because PostgreSQL caches activity
snapshots within a transaction. Refreshing with `pg_stat_clear_snapshot()` fixes
the test observation without releasing the barrier lock; this was not a runtime
limiter defect (PostgreSQL Global Development Group, n.d.-b).

A real signed backend HTTP request reads persisted tenant configuration and
uses the same one-slot pool as the real limiter. Only DNS validation and SMTP
delivery are substituted at the external boundary. Removing the existing
request rollback temporarily makes this test fail with HTTP 503 and exhausted
pool capacity; restoring it recovers the existing behavior. No mutation is
retained. An initially invalid reserved recipient suffix was corrected in the
test fixture; validation was not weakened. This does not exercise the browser
cookie/proxy path, prove actual SMTP delivery, or measure customer latency.

Before final commit, the focused four-file run passed 74 tests in 62.09 seconds
with fresh/repeated migrations and completed test-only container/network cleanup.
The final PR receipt must name the unchanged committed head and JUnit digest.
Subsequent whole-suite execution must first inherit #1562's nested subprocess
isolation follow-up; the parent environment alone does not protect children
that replace it. Retain failed candidates separately from GREEN evidence.

Run after installing the existing hash-locked core and Noema requirements:

```sh
bash scripts/ci/run_backend_postgres.sh
```

Ponytail reuse keeps the existing limiter, transaction cleanup and CI lifecycle;
only migration reconciliation and missing behavior checks are added. No new
runtime package, generic abstraction, quota heuristic or model timeout is needed.
Remaining acceptance: current-head hosted checks and independent review, parent
integration, protected merge, delivery/browser evidence, and realistic load.
No coverage percentage, release, deployment or p95 claim is established here.

## SMTP connection cancellation follow-up

At `1666f76cf94c31e34c2762c9d75f52ea3040b9a2`, the shared
`services.email_client._connect_validated_smtp_socket` closes the raw socket for
`Exception`, but `asyncio.CancelledError` derives from `BaseException` (Python
Software Foundation, n.d.). Cancellation while awaiting `sock_connect` therefore
escapes before the socket reaches the caller's `finally`. A cancelled send can
retain an open descriptor until later object reclamation. Both direct
`send_email` and `runner.local_mail_adapters.LocalMailAdapters.send_smtp` use
this helper; the latter is not a separate SMTP implementation.

The two new `test_smtp_connect_cancellation_closes_socket` cases exercise those
real consumers and create real OS sockets. Only DNS and the pending external
connect are substituted. After the connection starts, cancelling the actual
task must propagate the cancellation message and leave `fileno() == -1` before
the test releases its socket reference. Both cases were RED with an open
descriptor (`14 != -1`); the test's own `finally` still closes it so a failing
candidate does not leak the test resource. A five-second synchronization guard
bounds the test observation, not a model or application timeout.

Extend the existing cleanup handler to include `asyncio.CancelledError`, close
the socket synchronously, and re-raise without replacement or suppression.
Per-caller guards were rejected because neither caller owns the socket before
the helper returns. A new resource abstraction or dependency adds no value to
this one-line ownership fix. DNS pinning, TLS hostname checks, quota semantics,
and successful ownership transfer remain unchanged. The focused SMTP, message,
and registered-adapter suites passed 55 tests with warnings treated as errors.
The final exact-head whole-suite receipt belongs in PR #1417.

DeepWiki's September 6 lookup described a nonexistent connection `finally` and
excluded the registered Connector from the shared path. Current CodeGraph
source/caller evidence and the RED reproduction contradict that summary; do
not treat generated documentation as exact-revision runtime evidence. This
follow-up proves deterministic cleanup before connection completion, not real
SMTP delivery, browser cancellation propagation, recipient acceptance, or
post-delivery retry safety. No external message was sent.

## References (APA 7)

Bayer, M. (n.d.). *Working with branches*. Alembic documentation. Retrieved
September 6, 2026, from https://alembic.sqlalchemy.org/en/latest/branches.html

PostgreSQL Global Development Group. (n.d.-a). *Explicit locking*.
PostgreSQL 16 documentation. Retrieved September 6, 2026, from
https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS

PostgreSQL Global Development Group. (n.d.-b). *The cumulative statistics system*.
PostgreSQL 16 documentation. Retrieved September 6, 2026, from
https://www.postgresql.org/docs/16/monitoring-stats.html

Python Software Foundation. (n.d.). *Exceptions*. Python 3.14 documentation.
Retrieved September 6, 2026, from
https://docs.python.org/3.14/library/asyncio-exceptions.html
