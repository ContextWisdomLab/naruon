# Provider writeback retry claim concurrency

## Problem

`process_due_provider_writeback_retries()` originally selected due `pending` rows with an ordered `SELECT ... LIMIT` but without a row-locking claim. Two worker transactions could therefore observe the same retry row before either committed and both could execute the same provider writeback.

A later boundary review found a separate configuration-contract defect in the same query builder. `batch_limit=0` silently produces no work, while PostgreSQL rejects a negative `LIMIT` at execution. Neither value is a valid retry-worker batch size, and allowing either pushes a configuration error into silent disablement or a recurring database error instead of rejecting it at the Naruon boundary. Source-order RED `58bf1c651b061cc8b3270ec0a34331e4c390256a` requires `_due_retry_query()` to reject both cases; causal fix `da0073d570beed05e0f530914b45fa08a787675f` raises `ValueError` before query execution.

Fresh concurrency review then found that the first `SKIP LOCKED` repair still claimed too much work at once. Exact predecessor `a8fcba66f7235ac7d8f4a7a29818246f2703e5b3` selected up to `batch_limit` rows with `FOR UPDATE SKIP LOCKED`, performed remote provider I/O for those rows serially, and committed only after the whole batch. PostgreSQL row locks are held until transaction end, so a slow provider call for the first item also kept every later selected item locked even though Naruon had not started dispatching it. A second worker therefore skipped otherwise independent due work. The duplicate-dispatch repair was correct for safety but introduced avoidable queue head-of-line blocking and an unnecessarily broad transaction lock footprint.

A subsequent independent review of exact `3ec872cd38cfcace4d885422af4668ed690ee374` found a test-harness defect exposed by the per-item loop. `FakeRetrySession.execute()` filtered only on `retry_state` and `LIMIT`; it did not enforce production's `next_retry_at <= current_time` predicate. After a transient failure rescheduled a row into the future, the fake could return that same row again in the same worker pass and exhaust it, even though PostgreSQL would no longer consider it due. This is a false-negative harness bug rather than a production retry semantic. Commit `050e5f00430c31fbae5b6fe031105e7af2c01e8f` makes the fake honor the query's bound due time and due-time ordering, and strengthens the transient-reschedule regression to require exactly one processed row and no exhaustion.

## Contract

The due-work query uses `FOR UPDATE SKIP LOCKED` with due-time ordering and a strictly positive limit. The production worker claims **one due row at a time**, performs the provider attempt while holding only that row's lock, persists the resulting terminal/rescheduled state, commits, and only then queries for the next due row. `batch_limit` bounds the number of per-item claim cycles in one worker pass; it no longer means "pre-lock this many rows before remote I/O".

Another PostgreSQL worker must skip the row currently being dispatched rather than wait for it or dispatch it concurrently, but it remains free to claim the next independently due row. Invalid nonpositive batch configuration fails closed at the application boundary instead of becoming a silent zero-work worker or a database execution error. Test doubles used for this worker must preserve the same due-time predicate and ordering; otherwise they can invent same-pass retries that the production query excludes.

This contract is deliberately narrower than exactly-once delivery. A process failure after a remote provider has accepted a write but before the local transaction commits can still require provider-level idempotency or conditional-write semantics. The current row lock therefore remains held across its provider I/O: committing a `running` state before dispatch without a durable lease/recovery contract could strand the row after a worker crash, while committing before dispatch without preserving claim ownership would reopen duplicate execution. This change removes undispatched batch-row locks without inventing a weaker crash-recovery contract.

## Reality RED and causal repair

The original real PostgreSQL acceptance proves that a second transaction skips a retry row already locked by another transaction.

A second source-order PostgreSQL RED, `7b8071fa454e557a9a1a4583f5de05dc4da1a856`, creates two ordered due rows and starts worker A with `batch_limit=2`. Worker A blocks deliberately inside the first real provider dispatch. While that provider I/O is still pending, worker B must be able to claim and process the second due row. On predecessor `a8fcba66...`, worker A's initial `LIMIT 2 FOR UPDATE SKIP LOCKED` locked both rows, so worker B observed no claimable work.

Unit RED `c9fc20b13a11d3513841d181bd067f553410b1cb` separately requires a commit after the first dispatch outcome before the second item is dispatched. Causal production fix `5ddb10cf5113d20d3b5a0916ee80ffd823275034` changes `process_due_provider_writeback_retries()` to execute `_due_retry_query(current_time, 1)` repeatedly up to the configured positive `batch_limit`, committing each claimed item before requesting the next one.

That production change surfaced a pre-existing fake-session mismatch: the transient-reschedule regression could reselect a future row because the fake ignored the due-time predicate. Independent review identified the mismatch on `3ec872cd...`; `050e5f00430c31fbae5b6fe031105e7af2c01e8f` repairs the harness only. The production worker and SQL query are unchanged by that commit. The strengthened regression now explicitly requires `processed == 1`, `rescheduled == 1`, `failed_exhausted == 0`, and one commit after a transient failure scheduled 60 seconds into the future.

The two-session PostgreSQL test uses independently scoped `AsyncSession` transactions and a bounded wait. It verifies the behavioral property rather than only inspecting SQLAlchemy's `_for_update_arg`. The unit test keeps the transaction boundary visible even when PostgreSQL is unavailable locally. PostgreSQL-backed tests may skip when PostgreSQL is genuinely unavailable in a local unit-test environment; a skipped result is not promoted as concurrency evidence. The migrated PostgreSQL CI lifecycle remains the required hosted acceptance environment.

## Rejected alternatives

- Keep `LIMIT batch_limit` on the locking query and one final commit: prevents duplicate live claims, but unnecessarily locks work Naruon has not started and serializes otherwise independent consumers behind provider latency.
- Commit all selected rows before dispatch: releases the locks protecting undispatched rows and allows another worker to execute the same retry work.
- Persist `running`, commit, then perform provider I/O without a lease/claim expiry or recovery protocol: narrows lock duration but can leave a row permanently stranded if the worker fails after the claim commit. A lease/idempotency design can supersede the current transaction boundary later, but it must include explicit crash recovery and owner-token semantics rather than being inferred from `retry_state` alone.
- Silence the failing transient-reschedule unit test by setting `batch_limit=1`: hides the fake-session semantic mismatch and stops testing the multi-claim worker loop. The harness must model the production due predicate instead.

## Owner topology

The original direct-`develop` retry repair inherited unrelated frontend dependency-security failures. Canonical #1623 owns that dependency tree. The retry branch adopts `#1623@17a7618eda2b212b691f08fa936e042b34258fc9` by ordinary history and restores only retry-owned source/tests. No dependency, lockfile, workflow, or security-owner source is copied into this lane.

## References

PostgreSQL Global Development Group. (2026). *PostgreSQL 18 documentation: Explicit locking*. PostgreSQL. https://www.postgresql.org/docs/18/explicit-locking.html

PostgreSQL Global Development Group. (2026). *PostgreSQL 18 documentation: SELECT — The locking clause*. PostgreSQL. https://www.postgresql.org/docs/18/sql-select.html

PostgreSQL documents row-level locks as lasting until transaction end and documents `SKIP LOCKED` as an appropriate queue-like-table technique when multiple consumers intentionally skip rows another transaction already owns. PostgreSQL's executor rejects a negative `LIMIT` (`LIMIT must not be negative`); `LIMIT 0` is valid but returns no rows. Naruon therefore rejects both nonpositive values before database execution and scopes each live claim to the one row whose provider attempt is actually in progress.

## Acceptance boundary

Merge requires the final exact base/head to show both real PostgreSQL concurrency contracts, the nonpositive-limit regression, and the corrected transient-reschedule harness executing successfully. The ordinary repository/security gates appropriate to that exact head must be terminal-success, zero valid unresolved review findings must remain, qualifying independent approval must bind to the final source/test/doc head, and the canonical dependency-security owner must be integrated first. No direct-develop or predecessor-head receipt transfers after retargeting or later source/test changes.
