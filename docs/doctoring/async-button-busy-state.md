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
