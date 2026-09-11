# Provider writeback retry claim concurrency

## Problem

`process_due_provider_writeback_retries()` previously selected due `pending` rows with an ordered `SELECT ... LIMIT` but without a row-locking claim. Two worker transactions could therefore observe the same retry row before either committed and both could execute the same provider writeback.

A later boundary review found a separate configuration-contract defect in the same query builder. `batch_limit=0` silently produces no work, while PostgreSQL rejects a negative `LIMIT` at execution. Neither value is a valid retry-worker batch size, and allowing either pushes a configuration error into silent disablement or a recurring database error instead of rejecting it at the Naruon boundary. Source-order RED `58bf1c651b061cc8b3270ec0a34331e4c390256a` requires `_due_retry_query()` to reject both cases; causal fix `da0073d570beed05e0f530914b45fa08a787675f` raises `ValueError` before query execution.

## Contract

The due-work query uses `FOR UPDATE SKIP LOCKED` with due-time ordering and a strictly positive batch limit. The lock is held by the worker transaction while it processes the selected item; another PostgreSQL worker must skip that row rather than wait for it or dispatch it concurrently. Invalid nonpositive batch configuration fails closed at the application boundary instead of becoming a silent zero-work worker or a database execution error.

This contract is deliberately narrower than exactly-once delivery. A process failure after a remote provider has accepted a write but before the local transaction commits can still require provider-level idempotency or conditional-write semantics. This change prevents concurrent live workers from claiming the same row; it does not claim to solve crash-after-side-effect replay.

## Reality acceptance

A structural SQLAlchemy assertion is useful but insufficient by itself because it only proves that the statement object carries `skip_locked=True`. `backend/tests/test_provider_writeback_retry_postgres.py` therefore exercises two independent SQLAlchemy sessions against real PostgreSQL. The first transaction locks the earliest due retry row through the production `_due_retry_query()`. While that lock remains open, the second transaction executes the same production query under a bounded wait and must not receive the locked retry item. The test cleans up only its generated retry row.

The unit contract separately verifies that the configured positive limit is retained and that zero/negative limits are rejected before query execution. The PostgreSQL-backed test may skip when PostgreSQL is genuinely unavailable in a local unit-test environment. The migrated PostgreSQL CI lifecycle is the acceptance environment; a skipped local result is not promoted as concurrency evidence.

## Owner topology

The original direct-`develop` retry repair inherited unrelated frontend dependency-security failures. Canonical #1623 owns that dependency tree. The retry branch adopts `#1623@17a7618eda2b212b691f08fa936e042b34258fc9` by ordinary history and restores only retry-owned source/tests. No dependency, lockfile, workflow, or security-owner source is copied into this lane.

## Reference

PostgreSQL Global Development Group. (2026). *PostgreSQL 18 documentation: SELECT — The locking clause*. PostgreSQL. https://www.postgresql.org/docs/18/sql-select.html

PostgreSQL documents `SKIP LOCKED` as skipping rows that cannot be locked immediately and specifically identifies queue-like tables with multiple consumers as an appropriate use because the resulting view is intentionally inconsistent for general-purpose reads. PostgreSQL's executor rejects a negative LIMIT (`LIMIT must not be negative`); `LIMIT 0` is valid but returns no rows. Naruon therefore treats both values as invalid retry-worker configuration and rejects them before database execution.

## Acceptance boundary

Merge requires the final exact base/head to show the real PostgreSQL concurrency test and the nonpositive-limit regression executing successfully, the ordinary repository/security gates appropriate to that head to be terminal-success, zero valid unresolved review findings, qualifying independent approval, and prerequisite-first integration of the canonical dependency-security owner. No direct-develop predecessor receipt transfers after retargeting.
