# Provider writeback retry policy cadence

## Finding

`ProviderWritebackRetryWorker` had two distinct time concepts but represented them with one field. `interval_seconds` controlled how often the long-running worker polls for due retry rows, and `_sync()` also passed the same value as `retry_delay_seconds` to `process_due_provider_writeback_retries()`.

That coupling made an operational scheduling choice silently rewrite the domain retry policy. With the constructor defaults, initial retry persistence used the service default of 300 seconds, while a later transient retry processed by the worker used the 60-second polling interval as its backoff base. Changing the polling cadence for capacity or latency reasons therefore also changed provider retry pressure even though the caller had not selected a different retry policy.

## Reality RED and causal repair

Source-order RED `df673f778a6963c4a5cb7d129d850ec7d7d868d3` adds a focused worker-policy regression. It constructs a worker with a 7-second poll interval and a 300-second retry delay, executes the real `_sync()` boundary with controlled session/process doubles, and requires `process_due_provider_writeback_retries()` to receive the two values independently. The predecessor constructor does not expose `retry_delay_seconds`, so the contract fails before the production repair. The same RED requires negative worker retry delay to fail closed while preserving explicit zero-delay semantics.

Causal production fix `088652d57d4dcd9a17bcd9008b8c72fcb9152902` adds `retry_delay_seconds` as a distinct worker policy parameter with the existing service default of 300 seconds, validates only its semantic lower bound, stores it separately, and passes it through `_sync()`. `interval_seconds` remains solely the polling cadence used by `_run_loop()`.

No arbitrary maximum delay, attempt count, token budget, or timeout is introduced. A caller may still select `retry_delay_seconds=0` when immediate retry is an explicit product policy.

## Contract

- `interval_seconds > 0` controls only the delay between worker polling passes.
- `retry_delay_seconds >= 0` controls only the base delay used when a claimed provider writeback fails transiently and is rescheduled.
- `batch_limit > 0` bounds claim cycles per pass.
- `max_attempts > 0` bounds the total attempt policy already represented by the retry row.
- Changing worker polling frequency must not change retry backoff without an explicit retry-policy change.

This contract composes with `docs/doctoring/provider-writeback-retry-claim.md`: the worker still claims one due row at a time with `FOR UPDATE SKIP LOCKED`, holds only the active row across provider I/O, commits the result, and then claims the next row.

## Alternatives rejected

- Continue deriving retry delay from polling cadence: operational tuning becomes an undocumented domain-policy change and the default 300-second scheduling policy collapses to 60 seconds after the first worker retry.
- Hard-code 300 seconds inside `_sync()`: removes the accidental 60-second coupling but prevents an explicit product/configuration policy from being represented at the worker boundary.
- Add fixed upper bounds for polling or retry delay: no released product contract or measured capacity evidence justifies such caps.

## Acceptance boundary

The final exact head must execute the focused cadence/backoff regression together with the existing retry unit tests and real PostgreSQL concurrency acceptance. A source-order RED and static source inspection are not hosted GREEN evidence. Any source-changing child requires a fresh independent review, and the canonical dependency-security parent must be integrated or validated through the canonical stacked-PR execution path before merge.

## Traceability

The polling implementation continues to use `asyncio.sleep(interval_seconds)`. Python documents `sleep()` as suspending the current task for the supplied delay and documents zero as an optimized scheduling-yield path; that behavior supports the existing positive polling-interval invariant but does not define the provider retry-backoff policy.

Python Software Foundation. (2026). *Coroutines and tasks — Python 3.14.7 documentation: Sleeping*. Python. https://docs.python.org/3/library/asyncio-task.html#sleeping
