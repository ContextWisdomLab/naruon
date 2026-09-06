# Async button busy-state accessibility

## Decision

Naruon exposes `aria-busy=true` only while an action control is actively processing its asynchronous operation. The existing `disabled` behavior remains responsible for preventing duplicate activation; `aria-busy` communicates the processing state to the accessibility API rather than replacing the disabled-state contract.

The bounded change applies to the project evidence-review action, repository document actions, and duplicate-thread intent action. It does not claim whole-product accessibility conformance or imply that every statically disabled control is busy.

## Evidence boundary

WAI-ARIA defines `aria-busy` as a state indicating that an element is being modified and that assistive technologies can defer exposing intermediate changes until the operation is complete. The attribute is defined for all elements in the base markup and defaults to `false`. This supports binding `aria-busy` to the same boolean state that represents the in-flight asynchronous action, while leaving ordinary unavailable controls unmarked as busy.

## Verification

Merge readiness is determined only from the unchanged current PR head after repository CI, security, coverage, review, and protected-branch requirements pass. The accessibility attribute itself is not a substitute for rendered assistive-technology testing across supported environments.

## Reference — APA 7th

World Wide Web Consortium. (2026, June 4). *Accessible Rich Internet Applications (WAI-ARIA) 1.3* (Working Draft). https://www.w3.org/TR/2026/WD-wai-aria-1.3-20260604/

## Action identity

A shared loading lock may disable sibling document actions to prevent conflicting writes, but it must not announce every sibling as the operation that is currently processing. Naruon therefore records the initiating document action separately from the shared lock. Only the initiating upload, reparse, embedding-regeneration, HWP-conversion, or WebDAV-materialization button exposes `aria-busy=true`; disabled siblings remain `aria-busy=false`.

The focused server-rendered regression exercises the real button group and fails if a shared boolean again marks every document action busy. Stable `data-document-action` identifiers exist only to bind rendered accessibility evidence to the initiating operation; they do not authorize or execute an action.

## Project review prerequisite versus submission (2026-09-07)

The residual review finding on #1352 at `eb8af38ed00be32bc4e8ec8a2a210faab80d08ea`
was still present in `ProjectsLayout`: `evidenceLoading` describes fetching the
selected evidence, whereas `correctionSubmitting` describes saving its review.
The save button must remain disabled during either operation, but only the
submission changes its busy state and label. The repair changes that one ARIA
binding; it does not change request payloads, authorization, or the shared lock.

`ProjectsLayout.accessibility.test.tsx` now renders the actual component with
independently deferred evidence GET and correction POST responses. It checks
disabled/non-busy before evidence arrives, no premature POST, enabled/non-busy
after evidence arrives, disabled/busy during submission, exactly one POST despite
a repeated click, and enabled/non-busy after success or rejection, including the
failure alert. The existing confirmation and document-action tests remain.

The initial regression failed both new cases at expected `false` versus actual
`true` while fetching evidence. After the one-line repair, an initial combined
run hit the default five-second timeout and a subsequent state assertion failed;
an isolated run also timed out. These failures are retained, and host load is an
observation, not a proven cause. A diagnostic-only 30-second invocation passed
three tests; the repository timeout was not changed. The identical default
invocation then passed all four tests across the two related files (46.67 s).
Focused ESLint with `--max-warnings=0` and `git diff --check` passed.

Run from `frontend`: `corepack pnpm exec vitest run
src/components/ProjectsLayout.accessibility.test.tsx
src/components/data-layout/DocumentRepositoryTab.busy-state.test.tsx`.
This is mocked API/DOM evidence, not browser, screen-reader, full-suite, build,
hosted, or protected-merge acceptance. Those results must be attached to the
final immutable candidate separately before delivery is claimed.

## Unsaved project memo safety repair (2026-09-07)

The separate generic memo editor called `saveProjectEvidence`, which only set
a success message. Its page test and full-product smoke script mistook that
message for persistence. This is distinct from the semantic object's review
correction POST and must not be credited as a working save feature.

The inspected contracts are `backend/api/webdav.py` (folder reads and separately
scoped materialization intents), `backend/api/projects.py` (semantic object
corrections), and `project_registration.apply_project_correction` (candidate
group/object membership). They do not establish a generic folder/backlog memo
and source-selection persistence contract. Reinterpreting the memo as an
arbitrary graph object's summary or replacing its attributes would change the
domain meaning and ownership boundary, so that workaround is not used.

The immediate repair removes the false-success handler, disables the unsupported
save, labels the local preview unsaved, and explains that a refresh loses the
draft. The existing page regression first failed on the enabled save button;
it now checks unavailable saving, no POST and no success message. Smoke evidence
labels distinguish unavailable saving from persistence and no longer claim a
saved memo. This safety repair does not complete the product requirement.

The remaining product Gap requires a Naruon-owned versioned memo/source contract,
stable project identity including non-graph projects, tenant/workspace and source
authorization, audited writes, conflict handling, and reload/readback persistence
with real PostgreSQL and actual-browser evidence. Failed-source readiness and
zero-value metric rendering are separate unresolved findings. Parent `1b465`'s
build and error-screen inspection do not validate this new runtime delta; new-head
full/build/visual evidence remains required before delivery.

## Project source readiness safety repair

Four source requests (folders, tasks, semantic candidates and session) feed the
same project screen. Previously, a rejected request cleared arrays and the
render path converted them into a waiting queue and zero-valued milestones.
The first regression failed for each request: three displayed the fallback as
empty data, while the failed session did not show an error at all.

The screen now renders loading/error states before exposing derived project
metrics, rejects an unavailable session, and retries the same source batch from
an explicit action. A normal empty response still renders the empty workspace.
Tests distinguish pending sources, each failed request followed by recovery,
successful empty data, real component bindings and existing review submission.
The initial API client returns JSON without member validation. The project
ingress now checks folder/task/candidate members, nullable fields, task enums,
finite scores and integer counts before storing the batch. These checks match
`ProjectFolderResponse`, `TicketTaskResponse` and `ProjectCandidateResponse`,
including nullable citation paths and candidate timestamps. This is not a
whole-product schema audit or a server authorization change.
Independent degraded source panels and durable memo persistence remain product
work; no current-head full/build/hosted acceptance is inferred from focused tests.

The first malformed-response regression produced eight failures (invalid top
levels, null members and a non-text candidate title), with the no-claims
anonymous response correctly rejected. The next two-file invocation never ran
test bodies: two fork workers failed to start after 124.84 seconds. That remains
failed evidence, not a product pass or a proven host root cause. The fixed-lock
environment is pnpm 11.5.3 / Vitest 4.1.10; one later diagnostic keeps the same
default timeout and `--maxWorkers=1` without changing repository configuration.
That diagnostic terminated with exit 1 after 111.46 seconds: 18 of 21 tests
passed, two existing positive flows exceeded the default 5000 ms timeout, and
the contradictory session-response regression failed because no error state
was shown. All three existing busy-state tests passed. No worker-start error
occurred in this diagnostic. These results neither prove the cause of the two
timeouts nor complete the required positive-flow evidence; no further blind
rerun or timeout increase was performed. Focused ESLint exited 0 separately.

A contradictory `authenticated: false` response carrying a non-null user claim
is also a required regression. `ApiClient.getServerSessionClaims` ignored that
flag until local commit `e11a8e9754f826f2bcac6da9b820a9d54ea10e37` added an
explicit-true guard at the shared client. The actual `/auth/session` serializer returns anonymous claims
when unauthenticated, so this is malformed-response rejection work, not evidence
of a server issuing an authenticated identity to an anonymous caller. The shared
client repair was coordinated with its owner and kept in a separate two-file
commit. Eight flag regressions first failed. After repair, the API-client suite
passed all 25 tests (including true/network/malformed cases); the combined
working-tree run with pending project-readiness changes passed 46 tests across
three files in 20.37 seconds. Both earlier positive-flow timeout cases passed
in that run, without proving their earlier cause or repairing full-suite failures.
Focused API ESLint and diff checks passed. This is local evidence, not protected
integration, complete system verification, or a backend authorization change.

### Durable memo implementation prerequisites (proposed, not implemented)

`ProjectFolder` in `backend/db/models.py` has an opaque folder UID and user/org
ownership, but no workspace field; its read service filters only user/org.
Graph objects already carry workspace identity, while the fallback task queue
is a UI-derived object. A single unscoped memo key or graph correction cannot
represent all three safely.

First establish authoritative workspace ownership for existing folder records
and a stable, server-resolved project reference. Do not assign historical rows
to the caller's current workspace or infer ownership from a display title.
`_candidate_groups` currently uses a persisted explicit candidate UID when one
exists, otherwise `_synthetic_project_uid` derives an automatic UID from scope
and source identity. Adding an explicit candidate can therefore change the
project UID. A memo contract must preserve identity/alias continuity across that
transition rather than silently creating a different project or orphaning notes.
Then add the product-owned memo resource with a unique scoped project reference,
version number, note and authorized source reference; use a conditional write
against the expected version and record the audit event in the same transaction.
Reads must enforce the same owner/org/workspace boundary. The UI's source-kind
dropdown is not an authorized source identity and needs an actual source selector.
Reopening and refreshing must recover committed content; conflicting writes must
preserve the local draft and expose a reload/resolve action. Real PostgreSQL
scope/conflict/rollback tests and actual-browser save/readback complete the proof.
The disabled-save safety repair is only an intermediate step toward this feature.
