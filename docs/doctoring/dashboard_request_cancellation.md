# Dashboard request cancellation

## Evidence and decision

PR #1570 at `a48e8ba85b6d3a4ceb78e110582b3d5bc76d0d7c` protected state
updates with a cancelled flag and request generation, but its five dashboard
GET requests shared only a 15-second timeout signal. Retrying or leaving the
dashboard made responses irrelevant without aborting those fetches. The same
file's startup-search effect already aborts its controller during cleanup.

Reuse that native pattern for the dashboard generation. Combine its controller
with the existing timeout signal, then mark the generation cancelled before
aborting in cleanup. This preserves the five API routes, signed-cookie transport,
independent source states and request-version guard. It does not change model
timeouts or claim that abort rolls back work already accepted by a server. These
are read requests, not provider writes.

When both `AbortSignal.any` and `AbortSignal.timeout` exist, use the native
combinators. If either static method is unavailable, compose the same boundary
with a generation-local `AbortController`, the request-controller abort event,
and the unchanged 15,000 ms timer. Abort clears the fallback timer and listener;
timeout uses a `TimeoutError` DOMException. This avoids inventing a repository-
wide browser floor solely for this feature while keeping modern browsers on the
native path.

Do not replace the timeout, increase its duration, add a client wrapper, or
depend on ignoring stale responses alone. A retry gets a fresh controller;
cleanup must never abort that newer generation.

## Verification and limits

The existing retry-race harness now inspects all five old signals and all five
new signals, still delivers a late old response, and checks final unmount.
A StrictMode case checks discarded-mount cancellation, active-mount survival,
absence of a spurious error alert, and final cleanup. Both tests failed before
the source repair. Afterward, those cases plus dashboard, succession (including
the existing 15,000 ms timeout test), and API-client contracts passed: 30 tests.
Mock signal assertions prove cancellation delivery, not server-side cleanup or
measured bandwidth savings. Hosted checks and protected merge remain separate.

Focused lint with zero allowed warnings and TypeScript checking passed.
Native signal smoke checks passed in installed Chromium 151.0.7922.34,
Firefox 153.0 and WebKit 26.5 for both manual abort and timeout reason.
The full suite passed 53 files / 448 tests, but retained three CalendarLayout
and four EmailDetail act diagnostics outside this repair. Their existing owner
repairs must be inherited and revalidated; this is not warning-free full-suite
evidence or permission to suppress those diagnostics.

Review `3944626310` later identified that direct use of the two static
combinators made dashboard startup depend on browser support that the repository
had never declared. MDN marks both static methods as Baseline 2024 but explicitly
notes that older devices or browsers may not support them. The WHATWG DOM Living
Standard defines `AbortSignal.any()` as propagating the first source abort reason
and `AbortSignal.timeout()` as aborting with a `TimeoutError` DOMException. The
fallback therefore preserves the relevant native contract instead of silently
changing timeout or cancellation semantics.

Source-order RED commit `d510f5a99cf69f50db3bacfb3105260e78981345`
adds a focused regression that removes those static methods and requires five
dashboard request signals to remain cancellable and to abort at the existing
15-second deadline. The predecessor implementation calls `AbortSignal.any`
unconditionally, so that scenario cannot reach the dashboard requests. Causal
fix `2e937e49ccabda6e848a824d1bc7cee4ceb3ae2c` adds the guarded composition
above. These commits establish test-first source provenance; they are not
by themselves a claim that hosted CI has executed the final exact head.

## Follow-up: malformed array members

Review [3944460600](https://github.com/ContextualWisdomLab/naruon/pull/1570#discussion_r3944460600)
described a gap still present at `b88161f0c9515b39b101fe3fa8444be3b1895022`.
The envelope checks accepted arrays containing null or invalid records. Render
filters then dereferenced those values outside the promise rejection handler,
so an unavailable source could crash the dashboard instead of offering retry.

Validate the consumed email, task and calendar shapes before their state
setters; both email endpoints share one predicate. Use native type checks and
reject the whole invalid source rather than silently filtering members, which
would misreport counts and task completion rates. Preserve valid empty arrays,
independent sibling responses, cancellation and signed-cookie transport.
No dependency or general-purpose schema framework is needed for these three
local shapes. Project folders currently consume only length and are unchanged.

The first 12 null/empty-record/number cases failed before the repair. Additional
cases cover numeric email subject, object date, array task status (no string
coercion), and string calendar capabilities. Existing successful payloads and
retry/StrictMode tests remain regression evidence. Backend contracts checked:
`EmailListItem` in `backend/api/emails.py`, `TicketTaskResponse` in
`backend/api/tasks.py`, and `WritebackSource` in `backend/api/calendar.py`.
The guards cover consumed fields, not backend semantic correctness or
schema-wide conformance.

The first production-browser run disproved the initial local-only repair:
the three HTTP 503 recovery cases passed, but all three HTTP 200/null-member
cases failed. The trace recorded `Cannot read properties of null (reading 'id')`
and the page error boundary replaced the dashboard. `EmailList` was mounted
alongside the dashboard and accepted `data.emails || []` before mapping
`email.id`; dashboard unit tests mocked that component and missed the path.
Keep that failed trace and result; do not omit the malformed-response case.

Three additional EmailList inbox/sent/search regressions failed before the
sibling repair. Move the mail predicate to `frontend/src/lib/mail-response.ts`
and apply it to both dashboard mail sources and every located `/api/search`
consumer (EmailList, WorkspaceHome startup search, MobileApiPanel, SearchLayout).
This is a now-demonstrated shared responsibility, not a speculative wrapper.
Keep task/calendar predicates local. EmailList reports a fixed user-facing
message on validation failure rather than displaying payload values or internal
validator details. Optional nullable reply counts remain accepted because the
backend emits them. Original cancellation and envelope failures stay covered.

Scoped visual follow-up: the initial successful 503 desktop capture still
shows `source-linked` under pending tasks and `충돌 토큰 있음` under calendar
sources. These are unresolved user-facing implementation-detail leaks, not
acceptance of the complete product copy. Record them with the product Gap;
do not expand this availability repair into a translation framework or redesign.

## Exact-head gate recovery on 2026-09-08

The source head `a6e6ac59a72173793a834627b8489bea79805f16` retained successful
application, image, Semgrep, Trivy, and repository CodeQL evidence. Its central
compatibility CodeQL shards remained red because the first attempt intentionally
returned `pending` after dispatch and no authenticated terminal callback reached
the consumer run. OpenCode likewise had no current-head verdict. Strix reported
`STRIX_SANDBOX_UNAVAILABLE` after two Caido `loginAsGuest` bootstrap failures;
the displayed zero count preceded the transport failure and is not a clean scan.

Central `.github` PR #2028 later repaired missing dispatch-verdict recovery, but
that merge does not rewrite old consumer evidence. Converting this PR to Draft
and back to ready produced no new runs because the current callers do not
subscribe to `ready_for_review`. Therefore, never cite the UI state transition as
revalidation. This documentation delta records the causal logs and creates a
normal synchronize event without an empty commit. Acceptance still requires new
run ids on this exact successor head, terminal security analysis, and an
independent current-head review; no stale success is inherited.

## References

MDN contributors. (2026, September 1). *AbortSignal: any() static method*.
MDN Web Docs. https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static

MDN contributors. (2026, September 1). *AbortSignal: timeout() static method*.
MDN Web Docs. https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static

WHATWG. (2026, August 25). *DOM Living Standard*. https://dom.spec.whatwg.org/
