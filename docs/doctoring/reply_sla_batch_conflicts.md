# Reply SLA conflict recovery (issue #1669)

## Finding and inspected sources

The 2026-09-11 Jules notification points to an N+1 flush in
`backend/services/reply_sla_escalation_service.py`.

| Source | Inspected commit | Finding |
| --- | --- | --- |
| Default `develop` | `042b0c70531b229af3acbd0421a2f23098d848b3` | Ordinary writes are batched; repeated-conflict fallback becomes row-at-a-time. Invalid expunge and expired-mail recovery also fail. |
| PR #1486 | `1709ebb8d79f55c688a141aa932fa00468bf836d` | Removes invalid expunge, but retains row savepoints and reloads expired mail individually. Also owns workspace/scheduler changes outside this fix. |
| PR #1648 | `8ad819786c6c2a99e0a158d2192054eb8189b2f4` | Same backend service as develop; effective change is a frontend authoritative-response regression, not a backend repair. |

The original service blob is `7800f121c8c9d5704de6cf33e26583c7836051c0`.
A byte-for-byte copy, verified with `git hash-object`, was used for the baseline.

The add loop at the first fallback attempt is followed by one flush. It is not
itself an N+1 flush. Only after successive uniqueness races does the old code
switch to a savepoint and flush per remaining task. Removing necessary flushes
would prevent safe reconciliation rather than fix that branch.

SQLAlchemy rollback expunges pending inserts and expires persisted objects even
with `expire_on_commit=False`. Expunging those inserts again is invalid. Reading
expired Email attributes without explicit async loading risks implicit I/O.
Additionally, `begin_nested()` flushes pending work before creating a SAVEPOINT;
a failure there cannot be treated as an isolated inner conflict.

No external LLM call or explicit row-lock statement was found in the inspected
escalation/reply-tracking path. Repeated database round trips can extend ordinary
write-lock lifetime, but no production deadlock, latency or capacity measurement
is claimed.

## Repair contract

Keep the ordinary batch path. Recovery uses at most three batch savepoint
attempts and reconciles visible duplicate winners with one read per failed batch.
It never switches to per-task savepoints or expunges already-detached inserts.
A successful recovery commits once. If contention continues beyond the budget,
roll back all local updates and raise the existing `ReplySlaTaskConflict`, which
the endpoint already maps to HTTP 409. Non-duplicate integrity errors and errors
before SAVEPOINT creation are re-raised after cleanup, not masked by recovery.

Three attempts is an explicit bounded-contention policy, not an empirically
optimal value. Under sustained races the request may return 409 where the old
code would continue individual attempts. SQL driver statement batching, implicit
pre-savepoint flushes, and ordinary INSERT row counts are separate from this
explicit savepoint/flush budget. There is no claim that all database statements
are constant in the number of input rows.

Retain primitive email IDs before outer rollback and reload selected inputs in
one owner-scoped SELECT. Preserve input order; reject missing or moved sources.
Keep completed tasks closed, reuse existing task UIDs, and return the updated
persisted task fields. This preserves #1648's response-wins contract.

This develop-based patch does not replace #1486's workspace-aware service or
scheduler. When adopting it there, preserve that branch's workspace-selection
and physical-connection lease boundaries. No frontend, schema, credential,
workflow, security-gate, or deployment changes are included.

## Verification and limits

Local runtime: Python 3.13, SQLAlchemy 2.0.50, SQLite. Tests use a real SQLAlchemy
Session and database constraints, reduced mapped models, an asynchronous method
bridge around the synchronous session, and scripted visibility of conflict
winners. They do not create competing PostgreSQL clients. The local runner
supplied with the evidence bundle uses dependency shells for unrelated imports
because the full backend dependencies and PostgreSQL are unavailable locally.

- Original develop: 7 failed, 3 passed. Failures expose invalid expunge, expired
  input access, and loss of the original integrity error.
- Diagnostic original-code projection with only invalid expunge removed: 11 and
  51 explicit flush calls for 10 and 50 inputs after two conflict waves. This is
  not a test receipt for the complete #1486 head.
- A separate RED test exposed `PendingRollbackError` after pre-savepoint flush
  failure; the guard now preserves the original integrity error after rollback.
- Final candidate: 17 passed, zero failures/skips, with warnings treated as errors.
  Includes batch limits, complete rollback, FK errors, pre-savepoint errors,
  one-query reload, source deletion/owner changes, null scope, result order,
  stable task identity, and completed-task preservation.

With the full backend development dependencies installed:

```sh
cd backend
python -m pytest -q -W error tests/test_reply_sla_transaction_budget.py
python -m pytest -q -W error tests/test_tasks_api.py tests/test_reply_tracking_service.py
```

The second command, real async PostgreSQL race/migration tests, full backend CI,
and independent review were not executed by this local receipt. Before protected
integration, require those applicable checks on the unchanged candidate head;
exercise real uniqueness races, contention exhaustion with no partial writes,
source deletion between rollback and reload, and authoritative same-ID responses.
Do not transfer #1486's historical PostgreSQL results to this commit or present
these tests as a production speedup benchmark.

## Primary references

- [SQLAlchemy 2.0: Rolling Back](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#rolling-back).
- [SQLAlchemy 2.0: Using SAVEPOINT](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint).
