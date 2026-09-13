# ADR-0005: Quarantine attachments whose bytes disagree with their declared type

> Status correction (2026-09-01): references below to an open or deferred
> `Email.owner_filters()` gap are historical. The helper now requires
> `(user_id, organization_id, workspace_id)` and all production callers must
> provide an explicit workspace; no implicit workspace scope is accepted.

**Status:** Proposed (Naruon-local attachment ingestion policy; unmerged PR #1486)
**Date:** 2026-08-30
**Decision owner:** Naruon maintainers
**Scope:** Naruon's email-attachment parsing boundary
(`services/attachment_parser.py`, `db.models.Attachment`,
`POST /api/data/attachments/{attachment_uid}/reparse-intent`). This ADR does
not introduce a general-purpose file-type detection library, a virus/malware
scanner, or automatic remediation of quarantined content.

## Context

`parse_email_attachment` classifies an attachment purely from the sender-
supplied `content_type` header (falling back to the filename extension for
generic/missing values). Nothing previously verified that the attachment's
actual bytes matched that claim. A sender — malicious or simply
misconfigured — can label arbitrary binary content (an executable, an image,
an archive) with any `content_type`/extension, and Naruon would either try to
parse it as if it truly were that type, defer it for heavy recognition, or
silently record it as an unsupported binary — three outcomes, none of which
tell an operator or a future worker that the content lied about what it is.

Every other product-facing entity added recently (`TicketTask`,
`CalendarConflictJudgment`, `Document`) exposes an opaque `*_uid` id; `email_attachments`
was the one remaining entity addressable only by its internal sequential
integer id, so it could not be the target of a public, addressable retry
action.

## Decision

1. `services/attachment_parser.py` sniffs the attachment's real bytes against
   a small table of cheap, well-known magic-byte signatures (PDF, PNG, JPEG,
   GIF, ZIP). Text formats have no reliable magic bytes and are not sniffed.
2. When sniffing recognizes a signature that disagrees with the declared or
   extension-resolved type, the attachment is quarantined rather than parsed,
   deferred, or classified as a plain unsupported binary:
   `parse_status = parse_error_code = "content_type_mismatch_quarantined"`.
   The declared type stays in `content_type`; the sniffed (actual) type is
   recorded in `parse_content_type`, so comparing the two columns on a
   quarantined row shows the mismatch directly — no new column is introduced
   for this. The raw bytes are retained (base64, bounded by the same
   `MAX_ATTACHMENT_PARSE_SOURCE_BYTES` used for deferred PDF payloads) so a
   later pass has something to act on, unlike the existing failure statuses
   (`unsupported_content_type`, `parse_size_limit_exceeded`,
   `invalid_pdf_payload`) which discard content.
3. `Attachment` gains an `attachment_uid` opaque id (Alembic `0019`,
   backfilled for any pre-existing rows), following the same
   `<entity>_<uuid4 hex>` convention as `CalendarConflictJudgment.judgment_uid`
   and `TicketTask.task_uid`.
4. `POST /api/data/attachments/{attachment_uid}/reparse-intent` lets a caller
   scoped to the attachment's parent email (via the existing
   `_email_scope_filter` join, since `Attachment` carries no
   `workspace_id`/`user_id` of its own) record that a quarantined attachment
   should be re-evaluated: it transitions `parse_status` from
   `content_type_mismatch_quarantined` to `reparse_pending` and clears
   `parse_error_code`. Calling it on any other status is rejected
   (`422`). Matching the `hwp-conversion-intent`/`pdf-dom-recognition-intent`
   pattern already established for `Document`, this endpoint only records
   intent — it does not itself re-parse. A worker that consumes
   `reparse_pending` was intentionally out of scope for this slice at initial
   authorship, exactly as the NewsDOM PDF worker was a separate follow-up to
   the original deferred-PDF decision — **revised below**: that worker now
   ships in this same PR, after review (see Revisions).

## Alternatives rejected

### Reject mismatched attachments outright at ingestion

Rejected: a genuinely legitimate attachment can carry a wrong `content_type`
header for reasons having nothing to do with intent (a misconfigured mail
client, a lossy import path). Outright rejection would silently drop customer
data the same way an unbounded parse failure would; quarantining preserves the
evidence and gives an explicit, auditable path back to normal handling.

### Add a dedicated `quarantine_status` column

Rejected: every other status-like concept in this codebase
(`Attachment.parse_status`, `Document.document_status`,
`CalendarConflictJudgment.status_code`) is a plain string column with no
separate state table or DB enum. Quarantine is one more value of the existing
`parse_status`/`parse_error_code` columns, not a new state dimension.

### Store the sniffed type in a new column

Rejected: `parse_content_type` already means "the MIME type this attachment
was or would be handled as." Repurposing it for the sniffed type on a
quarantined row keeps that meaning intact (it is still "what this attachment
actually is") while `content_type` keeps its existing meaning ("what the
sender declared"), without adding new schema surface for a single derived
field.

### Synchronously re-parse from the reparse-intent endpoint

Rejected for scope and consistency: no endpoint in this file performs heavy
synchronous work from an `-intent` route today — `hwp-conversion-intent` and
`pdf-dom-recognition-intent` both just flip a status and leave the actual
work to a background worker. Doing real work here would also require
deciding, synchronously, whether the reparse should trust the sender's
original claim or the sniffed type — a decision better made by a dedicated
worker pass than inline in a request handler.

### Use a general-purpose file-type detection library (e.g. `python-magic`)

Rejected for this slice per the Ponytail-adjacent discipline this org applies
before adding a dependency: the org has only ever needed to distinguish a
handful of binary families (currently just PDF, and this ADR's image/zip
additions) from what a sender declares. A half-dozen fixed magic-byte
prefixes checked in Python cover that need with no new dependency, no native
extension, and no supply-chain surface. If a much broader sniffing need
arises later (arbitrary container/archive formats, deep content inspection),
that is the point to re-evaluate a dedicated library against this policy.

## Consequences

- A sender cannot get Naruon to treat disguised binary content as its false
  label by declaring a convenient `content_type` — the actual bytes decide
  when a recognized signature is present.
- Operators/future tooling can address a specific attachment directly via
  `attachment_uid` for the first time; nothing else changes about how
  attachments are listed or displayed in aggregate.
- `reparse_pending` is consumed by `services/attachment_reparse_worker.py`
  (see Revisions below) — a `reparse-intent` call now leads to an actual
  re-evaluation on the next sweep, not an indefinite queue with no consumer.
- **Fixed (see Revisions below): `_get_scoped_attachment` and every other
  attachment/email query in `api/data.py` now scope by `workspace_id` too.**
  `Email` gained a `workspace_id` column (Alembic `0020_email_workspace_scope`),
  and `_email_scope_filter` enforces it unconditionally, matching the pattern
  `_owner_scope_statement` already used for `Document`/`WebdavAccount`/
  `ProjectFolder`. A session with the same `user_id`/`organization_id` but a
  different signed `workspace_id` claim can no longer read or mutate another
  workspace's attachments through this file's queries.
- **Known, still-open, narrower-scoped limitation, tracked as a dedicated
  follow-up:** `Email.owner_filters(user_id, organization_id)` — the
  classmethod backing mail list/search/ontology/threading/Noema-agent email
  reads across `api/emails.py`, `api/search.py`, `api/ontology.py`,
  `services/noema_agent.py`, `services/threading_service.py`, and
  `services/hybrid_retrieval/retrieval_channels.py` — has the identical
  missing-`workspace_id` gap `_email_scope_filter` had, and was deliberately
  left unfixed here: closing it means auditing and updating every one of
  those call sites, a whole-app multi-tenancy change well outside scope for
  a PR whose stated purpose is a calendar-conflict-check tool. Recorded here
  rather than silently worked around; the fix belongs in its own dedicated PR.

## Research grounding

The content-graph follow-up is grounded in Edge et al.'s GraphRAG work, which
separates graph-based indexing from later graph-guided answer construction and
reports benefits for query-focused summarization over large private corpora.
That supports preserving the same document topology when content enters the
index through reparse as when it enters through initial import; this ADR does
not claim that Naruon implements the paper's entity extraction or community
summarization pipeline.

- Darren Edge, Ha Trinh, Newman Cheng, Joshua Bradley, Alex Chao, Apurva Mody,
  Steven Truitt, and Jonathan Larson. 2024. “From Local to Global: A Graph RAG
  Approach to Query-Focused Summarization.” arXiv:2404.16130.
  https://arxiv.org/abs/2404.16130

No paper PDF is copied into this repository: the stable source citation is
linked instead, avoiding an unsupported redistribution assumption.

## Revisions

### 2026-09-05: Status and sibling lease evidence correction

The former Accepted label preceded protected-branch adoption. This file is
absent from the verified `develop` head
`042b0c70531b229af3acbd0421a2f23098d848b3`; PR #1486 remains Draft.
All implementation and test statements below describe proposal history, not
protected-main, released, or deployed behavior. No valid delta is withdrawn.
The separate reply-SLA scheduler still had the physical-connection lease and
expired-record defects described below for the attachment workers. Its own
real PostgreSQL RED/GREEN, cancellation and manual-write conflict evidence is
recorded in [the scheduler decision supplement](../doctoring/reply_sla_physical_lease.md).
Worker evidence must not be transferred between implementations.

Two real gaps were found and fixed after initial review, both narrowing rather
than reversing the original decision:

- **OOXML/ODF/EPUB/JAR false positives.** DOCX, XLSX, PPTX, and other ZIP-based
  container formats sniff as `application/zip` by construction — that is not a
  disguise, it is what those formats are. `_is_genuine_content_type_mismatch`
  now excludes a ZIP sniff whose declared type is itself a known ZIP-container
  family (checked by MIME-type substring, not an exhaustive list, so sibling
  OOXML/ODF variants are covered without enumerating every one). A ZIP sniffed
  under any other declared type (e.g. `application/pdf`) is still quarantined.
- **Oversized mismatches were quarantined with no retained bytes, but
  reparse-intent still accepted them.** A quarantined row whose payload exceeds
  `MAX_ATTACHMENT_PARSE_SOURCE_BYTES` now gets the existing
  `parse_size_limit_exceeded` status instead of
  `content_type_mismatch_quarantined` — the same non-retryable terminal state
  every other oversized attachment in this parser already gets — so
  reparse-intent (which only accepts the quarantine status) can never be
  requested for a row it has nothing left to act on.
- **The reparse-intent follow-up worker, deliberately deferred at first, now
  ships.** `services/attachment_reparse_worker.py` (`AttachmentReparseWorker`,
  wired into `main.py`'s lifespan next to `NewsdomRecognitionWorker`, same
  jittered-loop + PostgreSQL advisory-lock-lease + starvation-free-cursor
  shape) sweeps `reparse_pending` rows and replays
  `parse_email_attachment` against the retained bytes and the attachment's
  original declared `content_type` — deliberately *not* the sniffed type,
  so the worker carries no bespoke "which type do I trust" logic of its own;
  it only re-asks the same classification pipeline the same question, and
  automatically benefits from any future fix to that pipeline (exactly as
  the OOXML fix above already would have, had it existed first). A retained
  payload that fails to decode (not valid base64) moves to a new terminal
  `reparse_payload_invalid` status rather than being swept forever.
- **Two correctness gaps in the worker itself, found on review of the above.**
  (1) The sweep cursor advanced to the batch's last row before any item in it
  was actually processed, so a row whose processing raised an exception (and
  therefore kept its `reparse_pending` status) fell below the cursor and would
  never be reselected until the whole forward queue drained to empty — silent,
  indefinite starvation under continuous reparse-intent traffic. The cursor
  now caps at the row just before the first failure in a batch, keeping that
  row in range for the next sweep. (2) The PostgreSQL advisory lease was
  acquired and released through the same `AsyncSession` used for each item's
  `commit()`/`rollback()`; since `AsyncSession.commit()` returns its
  connection to the pool on every call, the lease's release could run on a
  *different* physical backend connection than the one that acquired it —
  advisory locks are scoped to the acquiring backend session, so a mismatched
  unlock is a silent no-op that leaves the lease stuck until that connection
  is later recycled or closed, silently halting every replica's sweep. The
  lease is now acquired and released on one dedicated connection held open
  for the whole sweep instead.
- **`services/newsdom_worker.py` carried the same two gaps, now fixed to
  match.** It shared `AttachmentReparseWorker`'s acquire/release-through-the-
  per-item-session lease shape and its pre-processing cursor advance, on
  both its attachment and document sweeps. `NewsdomRecognitionWorker` now
  acquires/releases the advisory lock on one dedicated connection opened for
  the whole sweep (`_engine_uses_postgresql()` / `_try_acquire_sweep_lease`
  / `_release_sweep_lease` now take a connection, not a session), and each
  sweep caps its cursor at the point of the first failure instead of the
  batch's last row. The document cursor is a string primary key
  (`Document.document_id`, no `id - 1` to fall back on), so that sweep
  tracks the last row actually confirmed resolved before a failure rather
  than subtracting from the failed row's id — equivalent to the integer
  case for a contiguous key, and correct for a non-contiguous one. Both
  sweeps also re-fetch each row fresh by id before processing (mirroring
  `AttachmentReparseWorker`), since `AsyncSession.rollback()` after an
  earlier item's failure expires every object already loaded in that
  session, and a stale, expired bulk-loaded instance's attribute read would
  raise instead of just isolating that earlier failure.
- **Closed the cross-workspace gap this ADR's own Consequences section
  recorded above, for this file's queries.** `Email` gained a `workspace_id`
  column (Alembic `0020_email_workspace_scope`: add nullable, backfill every
  existing row with `workspace-<organization_id>` — the same convention
  already used by `services/email_import_service.py` and
  `services/project_graph/`, since `Email.organization_id` is `NOT NULL` and
  there is no FK from `Email` to any table that independently carries a real
  `workspace_id` — then set `NOT NULL`). `_email_scope_filter` now applies
  `Email.workspace_id == auth_context.workspace_id` unconditionally, mirroring
  `_owner_scope_statement`'s existing pattern for `Document`/`WebdavAccount`/
  `ProjectFolder`, so every caller of `_get_scoped_attachment` and the
  quality-surface stats helpers picks up the workspace predicate for free
  (they already unpack `*email_scope` into `.where()`). The three production
  call sites that construct new `Email` rows
  (`services/email_import_service.py`, `services/imap_worker.py`,
  `import_fixtures.py`) now populate `workspace_id` the same way. New test:
  `tests/test_data_api.py::test_data_attachment_reparse_intent_is_scoped_to_workspace`
  (same-user/same-org, different-workspace denial — the exact case this ADR
  flagged as unclosed). `Email.owner_filters()` — the separate classmethod
  backing mail list/search/ontology/threading/Noema-agent reads — has the
  identical gap and remains a deliberately separate, tracked follow-up (see
  Consequences above); it was not touched here.
- **CodeRabbit raised the `workspace-<organization_id>` backfill's trust
  boundary; its follow-up correctly rebutted this ADR's first response, and
  the underlying gap is now fixed at the authentication layer.** Its
  concern: if a real signed session's `workspace` claim ever diverges from
  the `workspace-<organization_id>` formula, the migration's backfill (and
  every new row this PR's production call sites write) could misattribute
  rows or make them unreachable. This ADR's first answer claimed that was
  provably impossible for the HMAC session path, reasoning from this repo's
  data-write call sites (no code here ever *writes* a non-conventional
  `workspace_id`). That reasoning missed the actual attack surface:
  `AUTH_SESSION_HMAC_SECRET`-signed sessions are *minted* by an external
  control-plane token issuer (`iss=naruon-control-plane` per
  `docs/operations/auth-key-management.md`) that has no code in this
  repository at all, so nothing here can "prove" what `workspace` value it
  puts in a token. CodeRabbit traced `_auth_context_from_session_payload`
  (`api/auth.py`) directly and showed it requires the `org` and `workspace`
  claims to each be present, but never checks the relationship between
  them — so a session signed with a correct `org` and an arbitrary
  `workspace` value was accepted as-is, for both the HMAC and OIDC paths,
  in production today. Fixed: `_auth_context_from_session_payload` now
  rejects (`401`) any session whose `workspace` claim is not exactly
  `workspace-<organization_id>`, closing the gap at the one place every
  session (HMAC and OIDC alike) is constructed, rather than in the OIDC
  decoder alone or in this migration's backfill formula. This makes
  `auth_context.workspace_id` an actually-enforced invariant instead of an
  assumed convention for every workspace_id-scoped table
  (`Email`, `Document`, `WebdavAccount`, `ProjectFolder`,
  `CalendarConflictJudgment`, `CarddavAccount`), not just this PR's own
  `Email` change. New test:
  `tests/test_auth_real.py::test_build_auth_context_rejects_workspace_claim_not_derived_from_org`.
  Two existing tests asserted specifically on a *different* concern
  (`api/security.py`'s `_require_authoritative_workspace_scope`, which
  unconditionally bars `session_verifier=="hmac"` from `/api/security/access-surface`
  regardless of the workspace claim's value, and a data-quality-surface test
  that only cared the workspace filter clause was present) but happened to
  use a `workspace` value inconsistent with their own `org` claim; both were
  updated to use an org-consistent workspace claim so each isolates the one
  behavior it's actually testing.
- **Devin flagged that `services/email_import_service.py`'s
  `_build_email_object` re-derives `workspace_id` from `organization_id`
  instead of accepting the caller's already-verified
  `auth_context.workspace_id`, reachable at `import_email_files`'s HTTP
  route — confirmed accurate as an architecture observation, and now
  provably inconsequential rather than merely "not currently
  exploitable."** With the authentication-layer fix above,
  `auth_context.workspace_id` is guaranteed equal to the derived value for
  every session that reaches this code, for both the HMAC and OIDC paths —
  not just "for every request path exercised today" as this ADR previously
  (incorrectly) claimed. Threading the real `workspace_id` through
  `import_email_files` → `import_email_uploads` → `_import_single_eml` →
  `_build_email_object` (`imap_worker.py`'s background-poll path has no
  `AuthContext` at all — there is no signed workspace to thread through
  there, so it must keep deriving) remains a reasonable DRY improvement,
  but it is a multi-call-site plumbing change with zero behavioral effect
  now, not a fix for this one's narrower scope.
- **Correction: the "three production call sites" claim above missed a
  fourth `Email`-inserting path, and Devin found it.** `backend/scripts/
  import_fixtures.py::process_zip_file` builds its own bulk-insert
  `batch_values` dict independently of `backend/import_fixtures.py`'s
  `email_obj = Email(...)` construction (already fixed) — a genuinely
  separate script, not the same call site under a confusing shared
  filename. Since `Email.workspace_id` is `NOT NULL`, every nonempty
  archive import through this path failed at commit. Fixed the same way
  (`workspace-<organization_id>` convention, included in both the insert
  values and the `on_conflict_do_update` set). New test:
  `tests/test_import_fixtures.py::test_process_zip_file_batch_insert_includes_workspace_id`
  (the existing `test_process_zip_file` only ever exercised the empty-zip
  path, which never reaches the insert — why this was missed originally).
  Devin also re-flagged `noema_agent.py`'s `tool_search_mail`/
  `tool_read_mail`/`tool_content_graph_query` reading through
  `Email.owner_filters()` without `workspace_id` — traced via `git blame`
  to `b6cb4e6f` (2026-07-13, over a month before this PR): confirmed as
  the identical, already-tracked `Email.owner_filters()` gap two
  paragraphs above, not new exposure from this PR, so left deferred per
  the same narrow-scope decision.

- **Correction (Devin Review, `6df8f44a`/`62b74a05` round): the "Fixed:
  `_auth_context_from_session_payload` now rejects (`401`) any session whose
  `workspace` claim is not exactly `workspace-<organization_id>`" entry above
  no longer describes current code — flag it as historical, not current
  behavior.** Commit `b778fb69` ("fix: enforce workspace-safe Noema
  identity") removed that exact-match rejection entirely: workspace
  membership is now treated purely as the independently signed opaque claim
  the verified session authority produces, never derived from or validated
  against `organization_id`. The rationale is the same class of correction
  CodeRabbit pushed on this PR's `Email` legacy-backfill thread — assuming
  every real deployment mints `workspace` as `workspace-<organization_id>`
  was itself the wrong premise; a genuinely independent external token
  issuer is free to mint an opaque value that doesn't derive from `org` at
  all, and rejecting such a session outright would be a false-positive
  authentication failure, not a security improvement. The referenced test
  was renamed accordingly:
  `tests/test_auth_real.py::test_build_auth_context_rejects_workspace_claim_not_derived_from_org`
  is now
  `test_build_auth_context_accepts_independently_signed_workspace_membership`,
  and asserts the opposite outcome (a session with `org="org-acme"`,
  `workspace="workspace-project-blue"` is accepted, not rejected). The two
  existing tests noted above (`api/security.py`'s
  `_require_authoritative_workspace_scope` test and the data-quality-surface
  test) are unaffected by this reversal — their own updates only fixed an
  org-inconsistent workspace value, not this specific rejection behavior.
  This ADR's downstream claims about `auth_context.workspace_id` being "an
  actually-enforced invariant" for every `workspace_id`-scoped table are
  narrowed by this reversal to: the claim is *present and well-formed*, not
  that it's provably derived from or consistent with `organization_id`.

- **Attachment reparse never indexed a successfully re-recognized
  attachment's content into the content graph, unlike the initial import
  path — flagged as informational by Devin Review on this PR ("confirm this
  is intended"), confirmed real but out of scope for this PR, and closed
  here as the tracked follow-up.**
  `services/email_import_service.py::_append_email_content_graph` already
  builds a `ContentNodeRecord`/`ContentSegmentRecord` graph for an
  attachment that parses cleanly on first import, but
  `attachment_reparse_worker.py::apply_reparsed_result` only ever updated
  the `Attachment` row's own columns — a previously-quarantined attachment
  that later reparses to `"parsed"` stayed invisible to content-graph-backed
  search/AI-hub features even after successful recognition, despite
  `AttachmentParseResult` carrying the same `parse_content` field the import
  path indexes. Fixed by calling a new
  `_append_reparsed_attachment_content_graph` from `apply_reparsed_result`
  whenever the reparse result lands on `"parsed"`. It reuses the same
  `services.content_graph.parse_content` helper the import path already
  calls, plus a newly shared `content_graph_source_record_uid` (moved out of
  `email_import_service.py`, where it was a private function, into
  `services/content_graph/parser.py` as a public helper both call sites
  import) — not a second indexing path, the same one with a second caller.
  Since a persisted attachment's original position among its email's
  siblings is not reliably reproducible after import, the reparse path keys
  `source_record_uid` on the attachment's permanent `attachment_uid` alone
  instead of the import path's message-id + list-position convention, and
  sets the new records' `email_id` directly from the attachment's
  already-loaded `email_id` column rather than through a transient `Email`
  relationship append (the attachment here is already a persisted row,
  unlike at import time, so there is no transient parent to defer FK
  resolution through). New tests:
  `test_reparse_that_lands_on_parsed_indexes_the_content_graph`,
  `test_reparse_that_lands_on_parsed_with_blank_content_does_not_index_content_graph`,
  `test_reparse_that_does_not_land_on_parsed_does_not_index_content_graph`.
  Verification: full backend suite 1908 passed / 40 skipped, ruff clean.

- **CodeRabbit's full review of the content-graph-indexing follow-up above
  found two real correctness gaps in it, both fixed here.** (1) The reparse
  embedding refresh regenerated `attachment.embedding` from
  `attachment.content` rather than the resolved parse source text.
  `apply_reparsed_result` only overwrites `attachment.content` when
  `result.content` (a markup-stripped *display* string) is non-empty; a
  `"parsed"` result whose display text strips to empty while its raw
  `result.parse_content` does not (e.g. an attachment that is only markup,
  no visible text nodes) left `attachment.content` at its stale,
  still-base64-encoded retained value, so the embedding was generated from
  base64 noise instead of the actual reparsed text — while the content graph
  indexed the correct text, since `_append_reparsed_attachment_content_graph`
  already resolved `result.parse_content or result.content` itself, matching
  `email_import_service._extract_and_generate_embeddings`'s identical
  resolution at import time. `process_reparse_pending_attachment` now
  returns a `ReparseOutcome(parse_status, embedding_source_text)` instead of
  a bare status string, carrying that same resolved text through to the
  embedding refresh explicitly rather than re-deriving it (unreliably) from
  the attachment row. New test:
  `test_reparse_that_lands_on_parsed_with_markup_only_content_still_embeds_parse_content`.
  (2) `0011_email_read_state.py`'s `downgrade()` dropped `emails.is_read`
  unconditionally whenever the column and legacy `emails` table were both
  present — including a same-named `is_read` column that predated this
  revision entirely, which this revision's own `NOT EXISTS`-guarded
  `upgrade()` therefore never touched, destroying that unrelated column and
  its data on downgrade. `upgrade()` now tags the column it creates with a
  `COMMENT ON COLUMN` provenance marker
  (`_IS_READ_PROVENANCE_MARKER = "0011_email_read_state:added"`);
  `downgrade()` drops the column only when that exact marker is present via
  `col_description`, so it drops what this revision added and nothing else.
  New real-Postgres test:
  `test_legacy_email_read_state_downgrade_preserves_a_preexisting_column`
  (pre-seeds a legacy `emails.is_read` column with data, runs upgrade then
  downgrade, asserts both the column and its data survive). Also renamed
  `email_import_service._generate_source_embedding` to the public
  `generate_source_embedding` (CodeRabbit nitpick): it is a third
  cross-module dependency `attachment_reparse_worker.py` imports, alongside
  `content_graph_source_record_uid` and `append_knowledge_graph_edges`, so
  the module boundary stays consistent when every cross-module helper is
  public. Verification: full backend suite 1911 passed / 43 skipped
  (`DATABASE_URL` unset, matching CI), and every test touched by this fix
  passes in isolation against a real PostgreSQL 16 + pgvector database; ruff
  clean. Running the full suite against that same real database in one
  process reproduces one pre-existing, already-reported cross-file
  test-ordering failure (`test_0001_initial_upgrade_succeeds_against_a_
  fresh_database` drops and recreates `email_records` mid-suite) —
  orthogonal to this fix, not caused by it.

## References (APA 7th)

Freed, N., & Borenstein, N. (1996). *Multipurpose Internet Mail Extensions
(MIME) Part Two: Media Types* (RFC 2046). RFC Editor.
https://doi.org/10.17487/RFC2046
RFC 2046 is the standard this ADR's "declared type" (the `Content-Type`
header on a MIME body part) refers to; it does not itself specify or require
content-sniffing, which is the gap this ADR addresses.
