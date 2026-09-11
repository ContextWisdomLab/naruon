# Provider writeback retry claim concurrency

## Problem

`process_due_provider_writeback_retries()` previously selected due `pending` rows with an ordered `SELECT ... LIMIT` but without a row-locking claim. Two worker transactions could therefore observe the same retry row before either committed and both could execute the same provider writeback.

## Contract

The due-work query now uses `FOR UPDATE SKIP LOCKED` with the existing due-time ordering and batch limit. The lock is held by the worker transaction while it processes the selected item; another PostgreSQL worker must skip that row rather than wait for it or dispatch it concurrently.

This contract is deliberately narrower than exactly-once delivery. A process failure after a remote provider has accepted a write but before the local transaction commits can still require provider-level idempotency or conditional-write semantics. This change prevents concurrent live workers from claiming the same row; it does not claim to solve crash-after-side-effect replay.

## Reality acceptance

A structural SQLAlchemy assertion is useful but insufficient by itself because it only proves that the statement object carries `skip_locked=True`. `backend/tests/test_provider_writeback_retry_postgres.py` therefore exercises two independent SQLAlchemy sessions against real PostgreSQL. The first transaction locks the earliest due retry row through the production `_due_retry_query()`. While that lock remains open, the second transaction executes the same production query under a bounded wait and must not receive the locked retry item. The test cleans up only its generated retry row.

The PostgreSQL-backed test may skip when PostgreSQL is genuinely unavailable in a local unit-test environment. The migrated PostgreSQL CI lifecycle is the acceptance environment; a skipped local result is not promoted as concurrency evidence.

## Owner topology

The original direct-`develop` retry repair inherited unrelated frontend dependency-security failures. Canonical #1623 owns that dependency tree. The retry branch adopts `#1623@17a7618eda2b212b691f08fa936e042b34258fc9` by ordinary history and restores only retry-owned source/tests. No dependency, lockfile, workflow, or security-owner source is copied into this lane.

## Reference

PostgreSQL Global Development Group. (2026). *PostgreSQL 18 documentation: SELECT — The locking clause*. PostgreSQL. https://www.postgresql.org/docs/18/sql-select.html

PostgreSQL documents `SKIP LOCKED` as skipping rows that cannot be locked immediately and specifically identifies queue-like tables with multiple consumers as an appropriate use because the resulting view is intentionally inconsistent for general-purpose reads.

## Acceptance boundary

Merge requires the final exact base/head to show the real PostgreSQL concurrency test executing successfully, the ordinary repository/security gates appropriate to that head to be terminal-success, zero valid unresolved review findings, qualifying independent approval, and prerequisite-first integration of the canonical dependency-security owner. No direct-develop predecessor receipt transfers after retargeting.
