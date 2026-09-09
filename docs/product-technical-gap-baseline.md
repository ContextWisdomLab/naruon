# Naruon Product and Technical Gap Baseline

**Baseline version:** 1.2
**Observed on:** 2026-08-26 (Asia/Seoul)
**Observed protected branch (current scan; row Base-SHA values remain historical):** `develop@e5e99b4e3bb081b92c602358878856536030e2ca`
**Observed product version:** `0.14.4`  
**Canonical completion issue:** [#1428](https://github.com/ContextualWisdomLab/naruon/issues/1428)

**Inventory observation:** the 106-PR open surface below is a fresh live
scan captured at `2026-08-25T15:52:01Z`, which returned 106 open PRs after
PR #1337 merged into protected `develop` at `2026-08-25T00:10:39Z` and
the later governance stack merge (#1448) and additional PR wave opened since
the previous observation. The
v0.2 baseline's 93-row snapshot from `2026-08-21T19:25:43Z` remains historical
context, as do the earlier 92-PR state after PR #1442 merged and the initial
83-PR observation in issue #1428; all counts are point-in-time evidence, not
current merge state.

**Follow-up delta observation:** a seventh live scan at
`2026-08-25T15:39:22Z` found the active exact-head work relevant to this
baseline: #1465 (`70596e26…`, tenant-archive import sanitization and duplicate
identity rejection), #1466 (`a3e6762f…`, origin-integrity port validation),
#1467 (`6816bc7f…`, utility-tool JSON boundary and Strix-trigger restoration),
#1468 (`1da167de…`, PostgreSQL smoke fixture schema alignment), #1469
(`de6d7128…`, bounded 20–64 MiB deferred attachment parse-source admission),
and #1455 (`d8757e65…`, attachment filename traversal hardening). The
governance root #1443 now has exact head `62a0d645…` after child #1448 merged
normally into its stack branch. #1448 merged at
`2026-08-25T15:31:39Z` with merge commit `62a0d645…`; its tree retains the
parent gate fix and the multiline, stale-head, and current-finding regression
cases. The merge-result Checks for that commit remain queued and are tracked
as post-merge canary evidence, not success.
The newly opened #1470 is now `aba77cf5…` (NetworkGraph edge-description
lookup cleanup); the predecessor `f8a70d37…` was discarded after a remote
commit reintroduced the dead argument and its callers. The current head also
removes the tracked 452-line `NetworkGraph.tsx.out` pre-refactor copy found by
Devin, with the 11-test focused suite, TypeScript, zero-warning ESLint, and
diff checks passing locally. Hosted Checks and independent approval remain
required.
These PRs remain open until their current-head required Checks and qualifying
independent approval satisfy the protected ruleset; this follow-up does not
reuse predecessor evidence or claim a merge. #1448 is historical after its
normal merge; #1443's current head is `62a0d645…` and must be reviewed and
checked again from that exact head.

**Live exact-head queue refresh (2026-08-25T17:51Z):** the following
post-snapshot states supersede only the matching historical SHA references
above; the full inventory remains a point-in-time record and is not silently
rewritten. #1468 is `1da167de26b442be6961622f15bb36ae9374e6c4`; its source,
backend, and frontend evidence is successful, while the retried Strix run is
queued after the earlier NVIDIA NIM provider failure. #1469 is now
`575b0c24fd9cb98106989eb101de74c5ce383db3`, after a remote follow-up removed
the unreachable document-size branch; 109 attachment/import/NewsDOM tests
pass locally, and the PR remains stacked behind #1468 because the selected
full suite exposes the base fixture defect repaired by #1468. #1470 remains
`aba77cf5b6a47985b352e8d2c2d76413579ea88a`; backend, frontend, Strix, and
metadata checks are successful, and its exact-head CodeRabbit approval is
present, but the ruleset still requires the second qualifying approval and
the exact-head OpenCode dispatch is queued. #1455 remains
`b2b4701366bc6bb2de1347b19eac9b4ed64cc614` with backend/frontend evidence
successful and Strix still running. #1429 remains
`b93caf0e00d09de0f836d8e4b869054d792e674b`; its refreshed hosted checks are
queued or in progress. #1347 remains
`f9e1751e2d5069841b279ecd2414fbbcad2e5692`; its newest metadata result is
not merge evidence and the remaining hosted checks are queued. None of these
states satisfies the two-approval protected ruleset, and none is a force-merge
candidate.

**Live exact-head queue refresh (2026-08-25T18:06Z):** a subsequent
re-fetch supersedes only the matching queue entries above. PR #1436 moved to
exact head `034d2ff4e0d120d1e7b7669b35ea8eea7d8c1221`; its frontend, backend,
and Strix checks were recreated and queued, with zero unresolved review
threads and no qualifying approval. PR #1470 remains
`aba77cf5b6a47985b352e8d2c2d76413579ea88a`; its metadata, OpenCode,
frontend, backend, Strix, and security checks are successful, but only the
exact-head CodeRabbit approval exists and the protected ruleset requires a
second qualifying approval. PR #1467 remains
`6816bc7f938fe361f2eb7a0ecee427f87170fbcb`; source/security checks are
successful, metadata is still in progress, and only CodeRabbit has approved.
PR #1466 remains `a3e6762f01666f5b4e9d202932012de23b942c59` with all
observed required checks successful but no current approval. PR #1468 remains
`1da167de26b442be6961622f15bb36ae9374e6c4`; its source checks are successful,
the retried Strix check is queued, and its metadata gate is not a merge
result. PR #1469 remains `575b0c24fd9cb98106989eb101de74c5ce383db3`; its
source checks pass while image validation and Strix are running and metadata
is failed pending current review evidence. PR #1455 remains
`b2b4701366bc6bb2de1347b19eac9b4ed64cc614` with image checks successful,
coverage and metadata pending, and Strix running. PR #1347 remains
`f9e1751e2d5069841b279ecd2414fbbcad2e5692`; its three informational review
threads are resolved, but metadata is failed and Strix/coverage are still
running. PR #1429 remains `39d796d14b93484e004c13d7e2db4cc2eee5cdb1` with
the refreshed hosted suite queued. No entry satisfies the two-approval
ruleset, and no entry is a force-merge candidate.

**Current Checks inventory:** the same live scan found 106 open PRs. Completed
failures were limited to `metadata-only gate evaluation` and `strix`; the
metadata gate reports the underlying Strix failure and, on some heads, a
current-head CodeRabbit quota/provider warning. The Naruon hosted Strix logs
for the observed #1468 run show NVIDIA NIM HTTP 429 rate limiting followed by
an unavailable direct fallback. This describes that run's provider evidence,
not the central Strix default documented in `AGENTS.md`; it is failed
infrastructure evidence rather than a clean security result or a source defect.
These PRs remain blocked and are not
force-merged; the exact head must receive a successful hosted security result.
PR #1466 has successful required Checks but remains in GitHub's protected
auto-merge queue with `REVIEW_REQUIRED` and no qualifying independent
approval, so it is also not treated as manually merged.

The latest exact-head follow-up also records: #1347 at
`e97fa1e4…` with its governance regression tests passing but hosted required
Checks queued and no qualifying approval; #1433 at `b84255e5…` with source
checks passing but Strix failed closed after NVIDIA NIM HTTP 429 retries and a
configured direct OpenAI HTTP 404 fallback; #1450 at `073408ce…` with all
other Checks successful while the metadata gate remains in progress; #1455 at
`d8757e65…` with all hosted Checks successful but no current-head approval;
and #1466 at `a3e6762f…` with all hosted Checks successful but no qualifying
independent approval. These are live queue observations, not merge evidence.
The provider failures are retained as infrastructure evidence and are not
converted into source changes or clean security claims.

**Exact-head maintenance ledger (2026-08-26):** PR #1347 now has exact head
`f9e1751e2d5069841b279ecd2414fbbcad2e5692` on this protected base. Its
governance normalization wrapper now fails closed when the review-unavailable
`jq` parser fails or emits a non-numeric count, and its early-exit cleanup trap
removes the wrapper-created comments snapshot when no PR number is available.
The exact-head local contract suite is 14 passed and the shell self-test remains
green. Hosted required Checks
were recreated and remain queued, so this is not a hosted pass or merge claim.
PR #1364 now has exact head
`3a3baa6b8dc9ea224f46395cb78c91a45be2090c` on this protected base. Its scoped
S3 document lifecycle, encrypted provider registry, compensation/orphan cleanup,
migrations, API, and LocalStack/PostgreSQL integration contract passed 195
focused local tests, Ruff, compileall, and diff checks. Hosted required Checks
and independent approval remain required; protected auto-merge is enabled but
no merge is claimed. The attachment and UI work continued on independent
branches while hosted runners were queued. PR #1419
now has exact head `2924b5598d4f527d493e1fc88cebd8fe87e1a3c4` on this protected
base, with 263 focused attachment/inline-image/email tests plus Ruff passing;
its hosted required checks were recreated for that head and remain queued, so
the normal protected squash auto-merge is enabled but not claimed as complete.
PR #1436 now has exact head
`1573be3332725bfbd05053943988d652df22a846` on the same base, with 446 frontend
tests, lint, typecheck, Next production build, Storybook build, and desktop /
mobile Storybook screenshots for source-open, low-confidence,
blocked-execution, and shared-scale states passing locally. It intentionally
remains pending because it carries a UI overlay at this document path while
PR #1429 owns the canonical commercial baseline; merge #1429 first, then
reconcile #1436 against the canonical file before enabling auto-merge. These
observations are exact-head evidence, not a release or hosted security claim.
PR #1415 now has exact head `994c6d40bb8a5a1de82e2f137300ea620bcdf933`; the
OIDC `kid` selection and strict administrator-role boundary passed 98 focused
authentication tests. PR #1417 now has exact head
`46f4b92a717361e3e4e42fcebc1d8c090a64c59b`; its PostgreSQL smoke seed now
explicitly supplies `is_read` after a real existing-schema NOT NULL failure,
and 180 focused tests pass. PR #1455 now has exact head
`b2b4701366bc6bb2de1347b19eac9b4ed64cc614`; bounded filename decoding and
Windows-separator traversal protection passed 130 focused parser/import tests.
All three have recreated hosted Checks and remain normal protected-merge
candidates; no hosted pass or merge is claimed.

The protected-branch SHA in this header identifies the baseline's observation
point. The inventory's `Base-SHA` column is captured independently for each PR
at its scan time, so an older `develop` SHA in a row is expected snapshot
metadata rather than a second claim about the current protected branch.

**Live exact-head queue refresh (2026-08-25T18:38Z):** PR #1468 remains at
`1da167de26b442be6961622f15bb36ae9374e6c4` and its current hosted check rollup
has no failed or pending run; it still has zero qualifying approvals and zero
unresolved threads, so protected auto-merge has not occurred. PR #1469 remains
at `575b0c24fd9cb98106989eb101de74c5ce383db3`; its source checks are passing,
while the metadata gate remains failed on current review evidence and
OpenCode is queued. PR #1429 remains at
`f2143f9d997736040eb3152f59ce058dc22ea72b` with the refreshed hosted suite
queued or in progress. PR #1436 remains at
`034d2ff4e0d120d1e7b7669b35ea8eea7d8c1221` with frontend image, coverage, and
Strix work still running. PR #1470 has a successful current check rollup and
one exact-head bot approval, but still lacks the second qualifying approval.
None of these observations authorizes a bypass merge.

The owning upstream sidecar `Seongho-Bae/newsdom-api` PR #682 remains at
`585bb4e0fb719ab6a576cf46d1ef12b77872557b`. Its bounded 64 MiB source and
boundary tests are present, while its only failed hosted check is the
provider-infrastructure Strix run (NVIDIA NIM rate limiting followed by an
unavailable fallback); no source vulnerability report was produced and the
normal rerun workflow is unavailable. The provider PR therefore remains
`WAIT_AND_REMEDIATE`, not a clean security pass or a force-merge candidate.
NewsDOM issue [#707](https://github.com/Seongho-Bae/newsdom-api/issues/707)
owns the follow-up resumable-upload contract for documents above 64 MiB, so
the current synchronous fallback must not be mistaken for the target
commercial large-document UX.

The central `ContextualWisdomLab/.github` control plane has two related
current-head repairs: PR #1331 (`a1408f52…`) separates the direct-OpenAI
fallback API base from the primary provider and has all observed checks passing
except queued coverage, while PR #1333 (`5454a196…`) adds bounded provider
retry/attempt-log handling with OpenCode still queued. Both have zero
qualifying approvals and remain normal protected-merge candidates; their
changes overlap in `.github/workflows/strix.yml`, so the first protected merge
must be re-fetched before the second is restacked.

This document defines the evidence-backed boundary between what Naruon currently
ships on protected `develop`, what is present only in open pull requests, what is
still a product-plan aspiration, and what a buyer must be able to complete before
Naruon is described as a generally available commercial product.

Counts, branch SHAs, checks, reviews, and pull-request state are point-in-time
evidence. They must be re-fetched before a merge or release decision.

---

## 1. Executive decision

Naruon is no longer a small prototype. The protected branch already contains a
substantial, security-conscious **customer-owned communication and context
control plane**:

```text
customer-owned mail / calendar / contact / file systems
→ Naruon ingest, thread, search, context, evidence, task, and action control
→ explicit human approval or correction
→ conflict-aware provider writeback through an outbound connector
```

Naruon must **not** become an SMTP server, IMAP mailbox host, public MX provider,
calendar source of truth, or file source of truth. Customer providers remain
authoritative. Naruon owns scoped context, policy, recommendation, intent,
connector command state, retry/reconciliation evidence, and the user-visible
decision/action experience.

The accurate current product classification is:

> **Production-oriented pre-GA communication control plane with substantial
> protected-branch capability, an unconverged ~100-open-PR integration surface (102 at the 2026-08-25 snapshot), and an
> incomplete buyer-visible release/operations contract.**

The first sellable boundary is **GA-1: Customer-owned Mail, Calendar, Contact,
and File Control Plane**. The complete dense knowledge graph, no-ask
correct-by-exception reasoning, minimal-disclosure bridge, and third-party plugin
platform remain the north-star after GA-1 rather than prerequisites for the
first commercial release.

---

## 2. Evidence hierarchy

When sources disagree, use this order:

1. exact protected-branch code, migrations, tests, runtime contracts, and
   security boundaries;
2. exact protected-branch architecture and operations documents;
3. exact current pull-request code and current-head evidence;
4. open Issues and accepted ADRs;
5. older product plans, README limitations, and historical PR descriptions.

A plan marked `[LIVE]` is not proof if the protected implementation contradicts
it. Conversely, an old README statement that calls a protected implementation
“future work” must be corrected rather than used to hide shipped behavior.

---

## 3. Point-in-time repository snapshot

| Item | Observation |
|---|---|
| Protected branch | `develop@e5e99b4e3bb081b92c602358878856536030e2ca` |
| Product/package version | `0.14.4` |
| Open pull requests | **102** (live scan at `2026-08-25T00:26:45Z`, post-#1337 merge) |
| Open issues | **61** (live count at the same 2026-08-25 snapshot; 59 were open before this baseline program) |
| New completion issue | #1428 |
| Required backend runtime | Python 3.14 exact-head lane |
| Core runtime | Next.js frontend, FastAPI backend, PostgreSQL + pgvector |
| Default data authority | customer-owned mail, CalDAV/CardDAV, and WebDAV providers |
| Default merge posture | strict exact-head checks plus qualifying independent review |

The **102-open-PR** count is the live inventory snapshot captured on
2026-08-25 against the protected branch shown above, after PR #1337 merged.
The v0.2 baseline recorded **93 open PRs** on 2026-08-21 after PR #1448
opened, an earlier same-day snapshot recorded **92 open PRs** after
PR #1442 merged, and the initial completion issue #1428 recorded **83 open
PRs** on 2026-08-20 against `develop@c9bfba2...`; these are historical
baselines, not contradictions. Later live counts can change as PRs open,
close, or merge, so every release decision must re-fetch the REST state.

The protected branch requires exact-head backend, frontend, security, CodeQL,
dependency review, Scorecard, OSV, Trivy, Strix, source/evidence coverage,
backend/frontend/combined image validation, and OpenCode review contexts. Pending,
queued, stale, predecessor-head, skipped-required, neutral, author-only,
model-only, or local-only evidence is not passing evidence.

---

## 4. Protected-branch product truth

### 4.1 Shipped communication and workspace surface

Protected `develop` exposes buyer-recognizable product surfaces for:

- Today execution dashboard;
- Mail, thread history, search, reply, and pending-reply work;
- Calendar views, source-backed coordination, and writeback intent;
- Tasks and source-linked ticket work;
- Projects, project graph, and evidence-linked records;
- Context Search and hybrid retrieval;
- AI Hub and provider-neutral AI workflows;
- Data/document ingestion and controlled materialization;
- Security/policy/audit views;
- Settings, identity, provider, and deployment controls.

The product already distinguishes simulated local send from real delivery,
preserves `In-Reply-To` and `References`, scopes email/provider records by owner
and organization, keeps opaque public identifiers separate from sequential
surrogates, and applies deny-first RBAC/ABAC policies.

### 4.2 Source-of-truth and writeback sovereignty

Protected `develop` already enforces important commercial boundaries:

- customer mail, calendars, contacts, and files remain durable provider truth;
- browser input selects an opaque source reference but cannot assert ownership,
  region, credential, or capability;
- writeback is intent-only unless the user explicitly requests provider
  execution;
- provider execution re-reads server-authoritative source records;
- CalDAV and WebDAV updates preserve ETag/If-Match conflict semantics;
- private-network provider access uses an outbound-only connector rather than
  inbound firewall holes or public mail hosting;
- provider credentials and command payloads are excluded from browser and
  aggregate observability surfaces.

### 4.3 Durable writeback retry is implemented

The current protected source-of-truth document records behavior that the root
README still describes as future work:

- scoped `provider_writeback_retry_items` rows;
- encrypted retry command payloads;
- retry dispatch with retry enqueue disabled for the nested attempt;
- exponential backoff;
- `succeeded`, rescheduled retry, and `failed_exhausted` outcomes;
- persisted connector signal events for dispatch, timeout, transport, and
  adapter outcomes;
- organization-admin aggregate queue-depth reads without exposing payload,
  credential, runner, source, or retry identities.

This is a material product-truth correction. The remaining gap is not “create a
retry queue.” It is **finish connector packaging, identity/enrollment, complete
protocol coverage, dead-letter/reconciliation operations, and buyer-visible
support evidence**.

### 4.4 AI and scientific boundary

Naruon has grounded content segments, hybrid search, named/versioned KG
extractor seams, deterministic fallback, contextual-orchestrator routing, and
batch-embedding integration boundaries. It does **not** have a protected live
Structural Topic Model endpoint or fitted topic artifact. Deterministic keyword
metadata must not be marketed as STM or temporal event psychometrics.

TEPP may be consumed only through a separately accepted, immutable, versioned
scientific artifact/API with preprocessing, vocabulary, covariates, posterior
uncertainty, diagnostics, provenance, and abstention. Naruon owns identity,
authorization, adapter envelopes, and disclosure policy; TEPP owns the
scientific payload.

---

## 5. Product-truth and release-truth inconsistencies

| Inconsistency | Current evidence | Buyer risk | Required correction |
|---|---|---|---|
| README says durable retry/audit remains future work | protected operations document describes encrypted retry rows, retry worker, backoff, exhaustion, and aggregate visibility | buyers and contributors cannot tell what is shipped | merge a customer/operator README based on protected truth; keep unsupported behavior explicitly limited |
| Release architecture says first candidate should be `v0.1.0` | `VERSION` and backend package are `0.14.4` | release procedure may publish or validate the wrong identity | replace historical hypothesis with current release-train policy and immutable release manifest |
| Product plan marks typed Person/Event/Commitment/Plugin concepts as new/planned | current code search does not prove authoritative `graph_persons`, `graph_events`, `graph_commitments`, or `plugin_registrations` stores | UI/marketing can imply dense-KG/product-platform completion that does not exist | keep north-star language, implement typed domains through bounded PRs, and gate claims on protected code |
| The live open-PR population (93 on 2026-08-21; 102 on 2026-08-25) contains many overlapping, stacked, micro, dependency, governance, and broad integration changes | current GitHub inventory | predecessor evidence, writer collision, stale branches, and integration starvation | establish a release train, classify every PR, close duplicates, merge parent-first, and use one writer per authority cluster |
| Required independent review exists but the current human reviewer path is unresolved | #1371 | green automation cannot produce a lawful protected merge | resolve reviewer governance without weakening rulesets or self-approval |
| Connector is described through a self-hosted-runner analogy | protected code has protocol adapters and retry behavior but no complete released connector lifecycle | operators may deploy test infrastructure as production relay | deliver signed installable connector artifacts, enrollment/rotation, source health, fleet SLO, and runbooks |

---

## 6. Current pull-request surface

The current open PR count is too large to treat as one releasable integration
unit. This baseline does not claim that every one of the 102 PRs has been
line-by-line approved. It records the product-significant active lanes observed
and defines the inventory that must be completed before GA.

### 6.1 Product-significant active lanes

| PR | Lane | Baseline judgment |
|---:|---|---|
| #1364 | scoped S3 document-object backend | high-leverage GA durability lane; Draft until real PostgreSQL + S3 lifecycle, backfill, cleanup, failure, and exact-head evidence are complete |
| #1417 | shared PostgreSQL-backed email-send throttle | necessary multi-replica safety; keep isolated and merge only with current-head concurrency/security evidence |
| #1416 | provider-backed CalDAV create writeback | relevant to GA scheduling execution; preserve create vs update precondition distinction and integrate into the broader #978 contract |
| #1353 | HWP/HWPX deterministic recognition boundary | useful Korean enterprise document admission; does not complete parsing/conversion/search semantics |
| #1397 | inline-media admission/tracking-pixel classification | valid evidence-protection slice; remain Draft until the #1350 stack and independent review are coherent |
| #1419 | common image metadata | bounded local evidence extraction; no OCR/VLM claim |
| #1418 | auditable URL/contact hygiene | deterministic tool/evidence lane; ensure contact redaction is not represented as complete anonymization |
| #1317 | broad macOS/local-AI/runtime/governance integration | valuable evidence but unusually broad; must be decomposed or reconciled carefully because many active PRs overlap its surfaces |
| #1392 | customer/operator README rewrite | directly addresses product-truth debt and has reported exact-head checks; still requires independent current-head approval |
| #1300 | fail closed on unsafe global tool mutations | correct safety posture until durable tenant-scoped plugin/tool registry exists; links directly to #976 |
| #1264 | EgressWeave integration | correctly dependency-blocked on an immutable released EgressWeave package and hash lock; mutable VCS dependency is forbidden |
| #1390 / #1391 | 56- and 78-package dependency groups | excessive blast radius, including major runtime and OpenAI client changes; split by compatibility/authority and rehearse migrations before merge |
| #1426 / #1414 | review-governance gate refresh | metadata-only governance repair; must not dismiss review, weaken rulesets, or turn stale aggregate state into false success |
| #1241, #1320, #1408, #1410, #1411, #1421, #1422 | accessibility micro-lanes | useful but numerous; consolidate non-overlapping UI fixes into bounded component-level trains to reduce 17-check amplification |
| #1424, #1412, #1401 | micro performance lanes | require real benchmark or stable complexity contract; do not let automated micro-PRs displace GA integration work |
| #1455 | path-traversal attachment parser hardening | high-value Sentinel security lane; prioritize within the new wave and merge only with exact-head Strix evidence once the provider outage clears |
| #1347 | rate-limited review status governance | current head constrains repository API-scope identifiers and merges the protected base; local tests pass, while hosted Checks and independent review are still required |
| #1433 | Message-ID whitespace hardening | source/security checks pass; the observed Strix failure is provider infrastructure (NVIDIA NIM 429 and direct OpenAI 404), so retry exact-head evidence without weakening the gate |
| #1450 | stray scratch/debug cleanup | all source and security Checks passed; wait for the in-progress metadata gate and current-head independent review |
| #1465 | scoped tenant archive import hardening | portability slice now rejects duplicate identities before writes and sanitizes archive-controlled display fields; retain the bounded slice-1 query cost and require current-head hosted evidence |
| #1466 | origin-integrity URL validation | current head rejects explicit zero/out-of-range ports; keep the signed-session and SSRF contract tied to exact-head regression evidence |
| #1467 | utility-tool JSON and governance repair | deterministic URL/HTML/JSON utility surface; current head rejects non-standard JSON numbers and preserves the central Strix workflow trigger, while full smoke evidence still depends on #1468's schema fixture repair |
| #1468 | PostgreSQL smoke fixture schema alignment | small root-cause test/data-contract repair for the current `email_records.is_read` requirement; merge before dependent smoke-test PRs after exact-head hosted evidence; the observed Naruon Strix run failed at the provider boundary (NVIDIA NIM 429/OpenAI 404), not in this source change |
| #1443 | CodeRabbit approval-notice governance root | current source/test lane narrows approval-notice parsing to the exact current head and ignores pending-review prose while retaining explicit findings; the predecessor Strix provider failure is historical, while the current head requires fresh queued Checks and a qualifying independent approval |
| #1448 | stacked governance regression coverage | merged normally into #1443's stack branch at `62a0d645…`; parent gate logic plus multiline JSON, stale-head unrelated prose, mixed blocker, and explicit current-head finding fixtures passed locally; merge-result hosted Checks remain queued and are post-merge canary evidence |
| #1469 | deferred attachment parse-source admission | aligns the hidden 20 MiB parser bound with the authenticated 64 MiB import contract while keeping unsupported binaries metadata-only; current changelog states the supported 20–64 MiB range and the ADR-0006 contract remains required |
| #1470 | NetworkGraph lookup optimization | bounded frontend performance slice; current head `aba77cf5…` preserves first-instance duplicate-ID selection, removes the dead `describeEdge` input, and deletes the tracked pre-refactor `NetworkGraph.tsx.out` copy; local 11-test, TypeScript, zero-warning ESLint, and diff checks passed, while hosted Checks and independent approval remain required |
| #1456 | email-detail UX density | buyer-visible mail surface polish; hold to the responsive/accessibility evidence contract in the UI quality section before protected integration |
| #1462 | utility tool trio (URL codec, hash generator) | bounded deterministic tooling consistent with #1418/#1361; must not be represented as AI judgment or topic evidence |
| #1457–#1461 | refreshed dependency-group bumps | successor waves to the v0.2-flagged groups; the 64- and 86-package backend/CI bumps remain excessive blast radius and still require splitting and migration rehearsal |

### 6.2 Required complete inventory

Before a release candidate is cut, create a machine-readable and human-reviewed
inventory for **all** current open PRs with:

```text
pr_number
head_sha
base_ref_and_sha
draft_state
mergeability
changed_authority_cluster
stack_parent
stack_children
current_review_state
unresolved_threads
required_check_summary
product_lane
disposition
next_action
```

Allowed dispositions:

- direct GA-1 slice;
- ordered stacked child;
- dependency-blocked;
- governance-blocked;
- duplicate/superseded;
- experimental/north-star;
- unsafe or unrelated and to be closed.

The inventory must be regenerated after every parent merge or branch movement.
It must not embed provider credentials, customer data, review-body secrets, or
large copied PR bodies.

### 6.3 Merge-loop progress since v0.2

Point-in-time progress observed between the v0.2 snapshot (2026-08-21) and
this v0.3 observation (2026-08-25). None of this is merge evidence; every
claim requires a live exact-head re-fetch before any decision:

- **Merge-gate progression:** #1337 completed its gate progression (CodeRabbit exact-head approval obtained, branch updated onto the base) and merged into protected `develop` at `2026-08-25T00:10:39Z`; #1438 obtained CodeRabbit exact-head approval and branch updates and remains open pending terminal required-check states.
- **Stale-snapshot repair:** #1241, #1368, #1412, and #1320 received systemic develop-baseline restores that preserved each PR's intended delta while removing predecessor-base drift from the diff surface.
- **Thread remediation waves:** unresolved review threads progressed through repeated remediation cycles on #1264, #1332, #1347, #1349, #1361, #1380, #1339, #1376, #1412, #1452, #1454, #1449, #1457, #1436, and #1441.
- **External blocker:** Naruon hosted Strix runs have observed NVIDIA NIM provider rate-limit failures (HTTP 429) since approximately 2026-08-24, emitting zero model-reported vulnerabilities before infrastructure failure. This is an observation of the affected hosted runs, not a change to the central GitHub Models default in `AGENTS.md`; per repository policy it is failed evidence, not clean-scan evidence, and Strix-dependent gates cannot pass until the provider path recovers.

### 6.4 UI/UX quality contract and Storybook event inventory

The UI is a buyer-facing control surface, not a decorative shell. The current
design-system implementation is carried by PR #1436 and ADR-0013; it uses the
production stylesheet as the Storybook token source and records Figma file ID
`68b5XB58w8nwT2LYOOnikK`. Until that PR is protected-branch code, its stories
are current-PR evidence rather than shipped capability.

The UI/UX Pro Max checklist and Anti-Slop UI heuristics are adopted as review
inputs, not as normative standards or automatic approval. They help select one
coherent design direction, expose generic UI defaults, and force explicit
review of accessibility, touch targets, hierarchy, and state behavior. WCAG
2.2 and the repository's security/accessibility gates remain authoritative.

The latest local fixed-origin capture for #1470 used `/` at desktop (1440×900),
tablet (834×1112), and mobile (390×844). Tablet and mobile presented the
responsive shell and an explicit mail-loading state. Desktop presented the
navigation shell but no data surface while the backend was intentionally not
running; the Next development server also reported a hydration mismatch for
the search-input caret style. This is local diagnostic evidence, not hosted
release evidence, and is tracked as a separate UX/runtime gap rather than
mixed into the bounded NetworkGraph change.

| Quality axis | Required definition and applied evidence | Audit gate before GA-1 |
|---|---|---|
| Accessibility | WCAG 2.2 AA; keyboard order/focus-visible; accessible names; labels; live/status announcements; color is never the only signal; Storybook a11y test is `error` for applicable stories | axe/Vitest Storybook results, keyboard journey, screen-reader name assertions, and zero unresolved accessibility findings |
| Touch & interaction | primary pointer and keyboard paths; at least 44×44 CSS-pixel target or documented exception; 8px separation; loading/disabled/pressed feedback; no hover-only action | Storybook `play` events queried by role/label plus touch viewport browser test |
| Performance | reserved media dimensions, no avoidable layout shift, route/component splitting, virtualized long lists, and responsive feedback for async work | production build budget, responsive capture at 375/768/1024/1440, and measured CLS/input-latency evidence |
| Style selection | one documented design direction, consistent icon language, semantic tokens, deliberate radius/elevation, and no generic gradient/card/emoji defaults | ADR/Figma decision, token source review, and Anti-Slop heuristic checklist with human disposition |
| Layout & responsive | mobile-first hierarchy, no horizontal scroll, readable line length, safe-area/fixed-bar offsets, and synchronized desktop/tablet/mobile navigation | Storybook viewport stories and Playwright route/drawer assertions at each supported viewport |
| Typography & color | semantic foreground/surface/status tokens; body text and line-height contract; contrast ≥4.5:1 for normal text; wrapping/overflow for IDs and user content | token lint, contrast scan, long-content story, dark-mode story, and i18n expansion test |
| Animation | shared duration/easing tokens, causal motion, transform/opacity preference, interruptibility, and `prefers-reduced-motion` behavior | reduced-motion Storybook story and browser assertion that action remains usable during transitions |
| Forms & feedback | visible labels, field-local errors, helper text, async progress, retry/undo or next action, and server error preservation | valid/invalid/loading/success/timeout/permission stories with submit and recovery events |
| Navigation patterns | predictable back/deep links, stable route identity, focus restoration, drawer parity, and one primary action per surface | route matrix, keyboard navigation journey, refresh/deep-link test, and mobile drawer test |
| Charts & data | legends/tooltips or accessible table, empty/loading/error/partial states, textual values, and color-independent meaning | chart stories for every state, keyboard/tooltip test, screen-reader text, and deterministic snapshot/visual evidence |

Each reusable component must have a Storybook story for its meaningful states.
Each interactive story must use a `play` function and user-like queries such as
role or accessible label; `data-testid` is a last resort. Storybook render,
interaction, accessibility, and visual tests are complementary: a passing
render story does not prove keyboard, async, responsive, or data correctness.

The minimum scene/event matrix is:

| Scene | Required event or assertion | Failure prevented |
|---|---|---|
| initial/ready | render, accessible name, primary action | dead or unnamed control |
| loading/pending | click or submit, disabled state, progress/status update | duplicate request and silent wait |
| empty/no-result | filter/search/reset, next-action copy | inert workspace |
| success/recognized | inspect, open, confirm, source/provenance text | unsupported product claim |
| validation/error/timeout | invalid input, server error, retry/recovery | error only in console or lost user work |
| unauthorized/forbidden | attempted action, denial explanation, no sensitive data | privilege disclosure |
| offline/connector unavailable | degraded read path, retry/backoff affordance | false provider success |
| long content/large dataset | wrap, scroll/virtualize, pagination or summary disclosure | layout collapse and browser lock-up |
| keyboard/touch/reduced motion | tab/enter/escape, pointer/touch, reduced-motion media query | inaccessible or motion-sensitive flow |

The inventory must record component, story name, state, event, expected
customer-visible outcome, accessibility rule, token source, viewport, and test
command. A story that only renders a static screenshot is incomplete for a
button, form, navigation, chart, or asynchronous data surface.

### 6.5 Queue convergence rules

1. One active writer owns each overlapping file/authority cluster.
2. A stacked child is not promoted before its parent reaches protected
   `develop` and the child is revalidated on the new exact base.
3. Predecessor-head checks and reviews never transfer.
4. Dependency changes that cross runtime majors are separated from unrelated
   feature work.
5. Historical one-shot, repair, finalizer, and self-modifying workflow identities
   are handled through #1324; do not add another write-capable cleanup workflow.
6. Independent approval remains mandatory; #1371 is resolved by establishing a
   legitimate reviewer path, not by weakening protection.
7. A micro-optimization requires measured evidence or a stable tested complexity
   invariant, not only an assertion that `Map` is faster than array lookup.
8. A PR that claims to close an umbrella issue must prove the full umbrella
   acceptance journey, not one narrow slice.

---

## 7. Buyer-visible Gap matrix

### P0 — Release and integration control

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Release-train convergence | no buyer can assess a product with ~100 unconverged open PRs (102 at the 2026-08-25 snapshot) | strict gates exist but queue topology is fragmented | #1428, #1371, #1324 | all PRs classified; duplicates closed; parent-first integration; one immutable RC SHA |
| Product/release truth | documentation conflicts with protected behavior/version | retry is shipped; release doc says `v0.1.0`; version is `0.14.4` | #1392, this PR | README, architecture, version, changelog, release manifest, and operator guide agree |
| Independent review path | automation cannot lawfully self-approve | effective rulesets require independent post-last-push approval | #1371 | verified reviewer route and normal protected merge without bypass |

### P0 — Connector and provider action

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Installable connector | adapters in source are not an operable product | outbound-only architecture and several adapters exist | #998 | signed packages/OCI, enrollment, rotation, upgrade/rollback, supported matrix |
| Source lifecycle | configuration does not equal observed provider capability | source IDs, eligibility, consent, and revisions exist in slices | #998, #978 | create/rotate/disable/delete, capability discovery, health, stale-capability invalidation |
| Durable reconciliation | retry exhaustion alone does not tell the buyer what happened remotely | retry/backoff/exhaustion and signal events exist | #998 | idempotent command, late-success reconciliation, dead-letter action, buyer receipt |
| Shared send safety | process-local throttles fail with multiple replicas | PR proposes PostgreSQL-backed atomic bucket | #1379, #1417 | concurrency/expiry/isolation/DB-unavailable tests and protected integration |

### P0 — Data durability, portability, and customer exit

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Binary object lifecycle | large/deferred document bytes cannot remain an inline database strategy | S3-compatible implementation is Draft | #1076, #1364 | upload/read/recognize/retain/delete/backfill/orphan round trip with real integration |
| Disaster recovery | a release is not enterprise-ready without restore evidence | HA evaluation exists; production WAL/PITR policy remains incomplete | #1428 | WAL archive/PITR, failover fencing, backup and clean restore rehearsal |
| Tenant export/reimport | customers need exit and migration without losing provenance | no single demonstrated full tenant round trip | #1428 | export → clean instance import preserving source, opaque IDs, history, evidence, policy |
| Retention/legal hold/disposition | deletion and evidence preservation conflict unless modeled | partial security/key/retention work exists across repository history | #1428, #1364 | purpose-scoped retention, legal hold, verified disposition, object/DB reconciliation |
| Attachment parser admission and unsupported formats | a file above 20 MiB can pass import transport but fail later at a hidden parser limit, while unsupported binaries are not searchable | Naruon import transport and generic deferred parser admission are bounded at 64 MiB; the NewsDOM `/parse` provider contract remains 20 MiB, so PDF bytes from 20–64 MiB are admitted and retained fail-closed but are not sent to NewsDOM; unsupported types remain metadata-only | #1427, #1469, #1353, #1419, NewsDOM #682/#707 | one documented bounded admission contract, provider-side PDF limit alignment or an explicit large-PDF fallback, parser/status evidence, deferred recognition, and object-backed retention before increasing the bound again |

### P0 — Evidence-based AI and document intelligence

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Canonical evidence identity | OCR/media/attachment/model slices can disagree about the same source | source segments and several deterministic admission slices exist | #1350, #1353, #1397, #1419 | one source identity/provenance chain across email, thread, document, attachment, media, model result |
| Judgment explanation | model output without evidence/calibration is not defensible | grounded extractor seam exists; wider evidence pipeline incomplete | #1350 | evidence IDs, claim support, abstention, correction, verifier result, prompt/model/version receipt |
| Provider-neutral route | raw provider coupling spreads credentials and failure behavior | contextual-orchestrator boundary exists; EgressWeave integration is blocked on release | #1262, #1264 | released hash-locked adapter, route/fallback evidence, no raw secret in products |
| Scientific claim discipline | keyword labels can be mistaken for topic/event measurement | architecture explicitly says no live STM | TEPP dependency path | accepted immutable TEPP artifact/API or explicit feature absence; no lexical-as-STM claim |

### P1 — Typed context and scheduling differentiation

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Responsive shell hydration and unavailable state | a buyer can see a polished navigation shell but no actionable content when a data request is unavailable, and hydration drift can produce inconsistent controls | local fixed-origin capture showed tablet/mobile loading feedback, desktop blank content without the backend, and a development-server caret-style hydration mismatch; this is not a hosted release result | follow-up required; keep separate from #1470's bounded lookup optimization | deterministic server/client markup, explicit desktop unavailable/error state, backend-backed responsive Playwright evidence, and no hydration warnings |
| Stacked PR current-head review dispatch | a dependent PR can show only metadata while the central OpenCode/required checks are still being materialized on a non-default base branch | #1448 exact head `068aefdf…` received a targeted scheduler/ OpenCode dispatch and then merged normally; its merge-result checks on `62a0d645…` remain queued | #1443, #1448, ContextualWisdomLab/.github scheduler | every supported stack base receives a bounded exact-head OpenCode/Noema/required-check run, with queued/provider states observable and no false merge readiness |
| Typed Person/Event/Commitment graph | generic string graph cannot safely drive high-stakes action | planning spec marks types as new/planned | #977, #978, #1000 | normalized temporal/multi-membership identities, evidence/confidence/correction on every inferred edge |
| Status-weighted scheduling | calendar CRUD does not prevent harmful double booking | CalDAV source/writeback/retry foundation exists | #978, #988, #989, #990, #1416 | confirmed/tentative/desired + organizer/attendee + recurrence/free-busy/resource end-to-end |
| Minimal-disclosure bridge | personal context can influence work availability without exposing private reason | policy substrate exists; product bridge is planned | #979, #991 | consented consequence-only propagation, revocation, audit, regression tests |
| Correct-by-exception inference | asking users to reconstruct context defeats the product mission | extractor/search foundations exist; dense-KG resolution remains incomplete | #977, #992, #1001 | one recommendation, evidence/calibration, hold/override, correction learning, no silent irreversible action |

### P1 — Platform and ecosystem

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Plugin lifecycle | internal extension seams do not create an enterprise platform | extractor/parser seams exist; durable custom tool mutation fails closed | #976, #1300 | signed manifest/release, tenant grant, sandbox, compatibility, upgrade/rollback/uninstall |
| Stable cross-repository contracts | copying sibling code creates a distributed monolith | several adapters are planned or dependency-blocked | #976, #1262, #1350 | released SDK/API/event/OCI contracts pinned by version/digest; no direct sibling SQL |
| Buyer administration | operators need source, connector, policy, health, retention, and support controls | settings/security surfaces exist but not one completed admin lifecycle | #998, #1428 | role-specific admin console with next-action explanations and audited high-risk changes |

---

## 8. GA-1 product definition

GA-1 is complete only when a buyer can perform the following journey on one
released, immutable product version:

```text
install or access Naruon
→ authenticate through the supported enterprise identity boundary
→ install and enroll a signed outbound connector
→ register customer-owned mail/calendar/contact/file sources
→ verify observed source capabilities and health
→ synchronize source records with provenance
→ receive a source-cited judgment or action recommendation
→ inspect evidence, confidence, authorization, privacy, and provider impact
→ approve, hold, or correct the recommendation
→ execute an idempotent provider action with current revision protection
→ observe success, retry, conflict, exhaustion, or reconciliation evidence
→ restore, export, or migrate the tenant without losing provenance
```

Naruon is not GA if the demonstration substitutes mocked provider success,
process-local state, local-only credentials, predecessor-head checks, synthetic
review approval, hidden manual database edits, or an unreleased sibling branch.

---

## 9. Delivery sequence

### Wave 0 — Product truth and queue convergence

1. Merge this baseline after exact-head documentation checks and independent
   review.
2. Keep #1428 as the single completion gate.
3. Maintain the complete open-PR inventory (section 13) and classify every PR as it arrives.
4. Resolve #1371 without weakening protection.
5. Merge/close governance and stale-workflow lanes through normal protected
   integration.
6. Correct README/release/version contradictions.

### Wave 1 — GA-1 runtime and operations

1. Finish #998 connector artifact, enrollment, capability, fleet, retry, and
   reconciliation lifecycle.
2. Integrate shared send throttling (#1379/#1417).
3. Finish binary object lifecycle (#1076/#1364).
4. Complete PostgreSQL WAL/PITR/failover/restore evidence.
5. Complete OIDC/SCIM/tenant administration and privacy-safe OpenTelemetry/SLO.
6. Publish independent backend, frontend, connector, and compatibility artifacts.

### Wave 2 — Buyer differentiation

1. Implement typed temporal/multi-membership Person/Event/Commitment graph.
2. Complete status-weighted scheduling (#978/#988/#989/#990).
3. Complete evidence-based mail/document/media resolution (#1350).
4. Add tenant export/reimport and customer-exit evidence.
5. Run the full buyer journey and failure/restore variants.

### Wave 3 — North-star platform

1. Minimal-disclosure privacy bridge (#979/#991).
2. Dense-KG correct-by-exception resolution (#977/#992/#1001).
3. Signed plugin platform (#976) with one real independently released CWL
   plugin.
4. Optional TEPP and other ecosystem adapters through accepted immutable
   contracts.

---

## 10. Release and quality gate

### Product correctness

- real IMAP/SMTP and DAV interoperability fixtures;
- duplicate/replay, late response, partial failure, provider conflict, connector
  restart, network partition, and source-capability-change tests;
- recurrence, timezone, DST, organizer/attendee, free/busy, and resource
  scheduling tests;
- full tenant export/reimport and backup/restore rehearsals;
- buyer-visible provenance completeness and unsupported-claim rate gates;
- no silent confirmed-commitment break;
- no private reason crossing a context boundary without explicit authorized
  disclosure.

### Code and documentation

- production statement coverage 100% for owned production code;
- production branch coverage 100%;
- public API/module/class/function docstrings 100%;
- frontend component, interaction, action-edge, design-token, accessibility, and
  i18n tests;
- no documentation that represents planned behavior as shipped or shipped
  behavior as future work;
- ADR, PRD, TRD, architecture, data model, runbook, and standard traceability
  updated with each release-relevant decision.

### Database

- normalized ownership and provider mappings;
- descriptive two-or-more-word `snake_case` object names;
- no direct cross-service SQL;
- bitemporal/effective-dated facts where provider state, membership, consent,
  policy, or source mapping changes over time;
- tenant enforcement and hot-partition/load evidence;
- clean install, N-1 upgrade, expand/backfill/contract, rollback, and restore.

### Security and supply chain

- OAuth/OIDC threat controls aligned with the current OAuth 2.0 Security BCP;
- signed connector and release artifacts;
- digest-pinned OCI images;
- SPDX 3.0.1 SBOM;
- SLSA 1.2 provenance;
- dependency/license/vulnerability evidence;
- secret, prompt, message, event, contact, and file-content exclusion from
  ordinary telemetry;
- no mutable VCS dependency in production;
- no self-modifying or broad-token workflow used to compensate for product code.

### Operations

- liveness, startup, readiness, and drain semantics per independently deployable
  component;
- OpenTelemetry trace, metric, and log acceptance;
- low-cardinality label contract;
- SLO, error budget, burn-rate alert, dashboard, on-call, incident, and support
  bundle;
- connector offline/backpressure and safe rolling upgrade;
- backup/PITR/failover/restore and customer-exit runbooks;
- versioned support, deprecation, compatibility, and security-fix policy.

### Protected integration

- one exact current head and one exact protected base;
- all live required contexts terminal-success;
- zero actionable unresolved review threads;
- qualifying independent non-author post-last-push approval;
- no bypass, self-approval, force push, dummy commit, empty requeue, or stale
  predecessor evidence;
- immutable release source SHA and artifact digests recorded in release evidence.

---

## 11. Issues established or strengthened by this baseline

| Issue | Purpose |
|---:|---|
| [#1428](https://github.com/ContextualWisdomLab/naruon/issues/1428) | new umbrella: GA scope, release train, and buyer-visible acceptance |
| [#976](https://github.com/ContextualWisdomLab/naruon/issues/976) | strengthened: signed plugin SDK, registry, permissions, compatibility, sandbox, lifecycle |
| [#978](https://github.com/ContextualWisdomLab/naruon/issues/978) | strengthened: typed Event/Commitment model, iTIP/CalDAV scheduling, free/busy/resource, conflict and privacy contract |
| [#998](https://github.com/ContextualWisdomLab/naruon/issues/998) | strengthened: installable connector, enrollment/identity, protocol capability, reconciliation, OpenTelemetry/SLO |

Existing linked implementation and blocker issues remain authoritative for their
bounded scopes, including #1022, #1076, #1229, #1262, #1324, #1350, #1371, and
#1379.

---

## 12. Standards and research traceability

The following standards are not decorative references. They define protocol,
security, accessibility, observability, or supply-chain acceptance tests in the
issues above.

For the DiskSage boundary specifically, PROV-O supplies the provenance
relations, DCAT supplies catalog/dataset/service discovery terms, OpenLineage
supplies run and facet vocabulary, and NIST SP 800-209 supplies storage
protection and recovery controls. The implementation must keep these as
metadata relationships and receipts; a provider upload or local path alone is
not an eviction or lineage claim.

### APA 7th references

Crispin, M. (2003). *Internet Message Access Protocol—Version 4rev1* (RFC
3501). RFC Editor. https://doi.org/10.17487/RFC3501

Daboo, C. (2010). *iCalendar transport-independent interoperability protocol
(iTIP)* (RFC 5546). RFC Editor. https://doi.org/10.17487/RFC5546

Daboo, C. (2011). *vCard extensions to WebDAV (CardDAV)* (RFC 6352). RFC
Editor. https://doi.org/10.17487/RFC6352

Daboo, C., Desruisseaux, B., & Dusseault, L. M. (2007). *Calendaring extensions
to WebDAV (CalDAV)* (RFC 4791). RFC Editor. https://doi.org/10.17487/RFC4791

Daboo, C., & Desruisseaux, B. (2012). *Scheduling extensions to CalDAV* (RFC
6638). RFC Editor. https://doi.org/10.17487/RFC6638

Daboo, C., & Quillaud, A. (2012). *Collection synchronization for Web
Distributed Authoring and Versioning (WebDAV)* (RFC 6578). RFC Editor.
https://doi.org/10.17487/RFC6578

Gellens, R., & Klensin, J. (2011). *Message submission for mail* (RFC 6409).
RFC Editor. https://doi.org/10.17487/RFC6409

Jenkins, N., & Newman, C. (2019). *The JSON Meta Application Protocol (JMAP)
for Mail* (RFC 8621). RFC Editor. https://doi.org/10.17487/RFC8621

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current
practice for OAuth 2.0 security* (BCP 240; RFC 9700). RFC Editor.
https://doi.org/10.17487/RFC9700

Melnikov, A., & Leiba, B. (2021). *Internet Message Access Protocol (IMAP)
version 4rev2* (RFC 9051). RFC Editor. https://doi.org/10.17487/RFC9051

OpenSSF. (2025). *Supply-chain Levels for Software Artifacts specification,
version 1.2*. https://slsa.dev/spec/v1.2/

OpenTelemetry Authors. (2026). *OpenTelemetry specification, version 1.60.0*.
https://opentelemetry.io/docs/specs/otel/

Elkady, H. (2026). *Anti-Slop UI: A Deterministic State-Machine Architecture
for Eliminating Design Hallucinations in LLM-Generated Interfaces*. Local Over.
https://local-over.github.io/Anti-Slop-UI/research_paper.pdf

NextLevelBuilder. (2026). *UI/UX Pro Max skill* (Version 2.5.0) [Computer
software]. GitHub. https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

Storybook. (n.d.). *Accessibility testing*. Retrieved August 21, 2026, from
https://storybook.js.org/docs/writing-tests/accessibility-testing

Storybook. (n.d.). *Interaction tests*. Retrieved August 21, 2026, from
https://storybook.js.org/docs/writing-tests/interaction-testing

SPDX Workgroup. (2024). *SPDX specification, version 3.0.1*.
https://spdx.github.io/spdx-spec/

World Wide Web Consortium. (2024). *Web Content Accessibility Guidelines
(WCAG) 2.2*. https://www.w3.org/TR/WCAG22/

National Institute of Standards and Technology. (2020). *Security guidelines
for storage infrastructure* (NIST Special Publication 800-209).
https://doi.org/10.6028/NIST.SP.800-209

OpenLineage. (n.d.). *OpenLineage documentation: Object model, run cycle, and
facets*. Retrieved August 25, 2026, from https://openlineage.io/docs/

World Wide Web Consortium. (2013). *PROV-O: The PROV ontology*.
https://www.w3.org/TR/prov-o/

World Wide Web Consortium. (2024). *Data Catalog Vocabulary (DCAT) — Version
3*. https://www.w3.org/TR/vocab-dcat-3/

---

## 13. Live open-PR identity inventory

This table was generated from a live GitHub pull-request collection whose
response was captured at `2026-08-25T00:26:45Z`. It records every currently open Naruon
PR's immutable head,
base, draft state, authority cluster, stack parent reference, and provisional
disposition. Review decisions, unresolved threads, mergeability, and Checks are
volatile and must be fetched again for the exact head immediately before any
merge; GraphQL rate-limit failures are not treated as approval or success.

The 102-row inventory is a fresh refresh later than baseline v0.2's 93-row
snapshot captured at `2026-08-21T19:25:43Z`: PR #1337 merged into protected
`develop` at `2026-08-25T00:10:39Z` and PRs #1449–#1463 opened since that
observation. The v0.2 93-row snapshot, the earlier 92-row snapshot taken
after PR #1442 merged, and their exact-head observations remain historical
and are retained in baseline v0.2 and in git history for audit
traceability. The self-row reflects the head observed at scan time and may
trail this document's own commit; all review decisions, Checks, and
mergeability still require a live exact-head fetch before merge.
Base-SHA columns record the protected-branch tip each row was scanned
against (`develop@81c10564...` for rows captured before PR #1337
merged; `develop@e5e99b4e...` for rows captured after). A few older rows
retain `develop@dd8d1519...` from an earlier scan window; that value is also
historical scan provenance, not a second claim about the current protected
branch. These values are therefore not one shared base declaration.

| PR | Title | Exact head SHA | Base ref and SHA | Draft | Authority cluster | Stack parent ref | Disposition | Next action |
|---:|---|---|---|:---:|---|---|---|---|
| 1463 | 🎨 Palette: 비동기 작업 버튼의 로딩 상태 시각적 피드백 개선 | d0f51274dc86271e365aa1384e1362daf93f1d7d | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1462 | feat: 신규 유틸리티 도구 3종 추가 (URL 인코더, URL 디코더, 해시 생성기) | dba144b01be8a7e332c9fc7b390e1d9b105536c4 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1461 | chore(deps): bump the ci-python group across 1 directory with 86 updates | f012853e6123017c290a7782cc7cf8e4801e4bb7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1460 | chore(deps): bump the backend-python group across 1 directory with 64 updates | dec4329986b261607204c0711d62f3bcd782d181 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1459 | chore(deps): bump the frontend-npm group across 1 directory with 14 updates | 3edb8320b0288f2bba54ce7e28083164e0d51966 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1458 | chore(deps): bump the github-actions group across 1 directory with 3 updates | f7099f951574a01f1333cb72a5e48ac91e7f4ea5 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1457 | chore(deps): bump the docker-base-images group across 1 directory with 2 updates | 245c8f1d2177e451e9812525ef6bbd7db9be3e6e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1456 | 🎨 Palette: 이메일 상세 화면 UX 밀도 개선 | 20b1c7f4798343d6949ab57ee9ab015d928b04bf | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1455 | 🛡️ Sentinel: [HIGH] 첨부 파일 파서의 경로 탐색 취약점 수정 | 40c5b7087a92a23eba787682fe32604861a9474b | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1454 | ⚡ Bolt: Optimize NetworkGraph edge description lookups to strictly O(1) | 9cb7883cd0a41b9634f4f74e77f3595d754ab7e7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1453 | 🎨 Palette: SettingsLayout 비활성화 버튼 접근성 툴팁 개선 | eef7e8d2eb25199afeb13c6b8a24f0f73bbd0fe5 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1452 | 🎨 Palette: 비활성화 버튼 접근성(Tooltip) 개선 추가 | ad32c8d35c11a76f52e189d7a5e83fb74fb603df | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1451 | feat: 텍스트 유틸리티 도구 추가 및 테스트 보완 | a2a20e3eb14bb65fab8ee2f2f9199dd76dd71bce | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1450 | chore: remove stray scratch/debug files committed to develop | 7d1f57a83a34312bea265ae3095bc67ff4e0493e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1449 | 🎨 Palette: 데이터 저장소 버튼 액션 로딩 UX 및 접근성 개선 | 90248b26fff37f395c6918525c4eef041d683e09 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1448 | test(governance): exercise multiline CodeRabbit pending notice | 874c098548e6794217393e0338074ba2f292d080 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1443 | fix: ignore CodeRabbit approval pending notices | 41e48413cffefa8a5393d6af1d5ad16be3c5de7c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1441 | 🎨 Palette: [UX 개선] 메일 상세 고밀도 컴포넌트 추가 | ce6ff8f26e4cfdc76be7d667c7b159c57f8e0ac5 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1439 | ⚡ Bolt: 프론트엔드 O(N) Array.find() 룩업을 O(1) Map 룩업으로 성능 개선 | 68106d13175d7ff67978de66e31d385237ca53b1 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1438 | fix(governance): supersede stale review decisions safely | 5cc9ca3348575931b5d2ec35d1277436d1eece63 | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1436 | feat(frontend): add Storybook UI inventory | becc4e9e56bb30e511e812e8c66b19d094b28de0 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1434 | fix: accept DiskSage cloud-readiness schema 7 | 85e3eb43f9a7c3e87848df1307549d4efd3d29de | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1433 | fix(security): reject ambiguous Message-ID whitespace | 0d71272d6ec5420afefa98cd5ae57b91efc31007 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1432 | fix(compose): harden optional pg-llm-batch database | e3dbed9a0d4e08348f94d26de09a2fabbdcfa96b | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | llm/orchestration | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1431 | test(core): cover operator env path resolution | e058f8c6e50256194d19be617f8df54f60bd1c27 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1430 | 🎨 Palette: 키보드 내비게이션을 위한 focus-visible 스타일 추가 | 49fc3eabd8e94a95dee2af3c1254c4d46a294399 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1429 | docs: establish Naruon product completion gap baseline | 5a72475506e8ec76692abfa233f3205c645568eb | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | docs/product | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1427 | fix(data): align PDF DOM upload budget with sidecar | 29be15e4ec5e29dc1f62ac636928c9307a6f520f | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1426 | fix(governance): wait on stale aggregate review state | 5cc148e1f2f84d1afcd2d3cf3dabaade616c01d0 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1424 | ⚡ Bolt: [성능 개선] 네트워크 그래프에서 O(N) 노드 라벨 조회를 O(1) Map 조회로 대체 | 32c7edc11fd6faf8ae6918dae8b00de7c5c0b773 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1421 | 🎨 [UX] 설정 화면 장식용 아이콘에 aria-hidden 추가 | 719c1b347aae52e77ae7e40b0eb60769fd7178cb | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1420 | feat: URL 코덱 및 엄격한 JSON 포매터 추가 | bf7b741ea0b73a146ce9bcd323ca621c1562cb4e | develop@dd8d15191338b841f9e6f3a06507c6a5643b95d0 | yes | other | — | experimental/draft | validate parent and promote only after scope proof |
| 1419 | feat(attachments): index common image metadata | a0f5e03107e6ec3e85eea029bb11c8c8e784b907 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1418 | feat(tools): add auditable URL and contact hygiene | 19adb3e74c66837c5fb2d0a11a7ac030bbbfe3c4 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1417 | fix(email): enforce shared send throttling | 69fb72d30c71ab7a9c2c6e09413292a05278148d | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1416 | fix(calendar): allow provider-backed create writeback | d8b3df7d19def826a5b92abbcaec043377ceb3a4 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1415 | fix(auth): select OIDC signing key by kid | e0a1f166221790e7ba4f0df37b328ac3cb896092 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1414 | fix(governance): refresh gate after OpenCode review | df1642c473011e935ab7501f4012fb58b8d06e21 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1412 | ⚡ Bolt: [성능 개선] tools 배열 탐색을 Map 기반 O(1)로 변경 | b5032d7fb428189da86c10221d58d093d3abcc6e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1411 | 🎨 Palette: 검색어 지우기 ARIA 라벨 통일 | 6369e91f2f10ed9b6b436a41a08d89b7aedf9008 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1410 | 🎨 [OIDC 로그인/로그아웃 버튼 로딩 상태 및 접근성 개선] | fac7a5377bd7c5bc7bde89a6f0f05b3fd2c47632 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1408 | fix(a11y): expose keyboard focus on AI Hub tabs | cda57c26e75788eaa350d0faeb898349818da074 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1407 | feat(mail): fail-closed Inkspan edit handoff for recognized HWPX | 22e4909dd13623190f61eae47baf74d70fa2b83a | cursor/mail-hwpx-attachment-preview-7b5e@b83a0da03b46a447f9710b5f91d245f5b1783dfa | yes | ingest/storage | cursor/mail-hwpx-attachment-preview-7b5e | experimental/draft | validate parent and promote only after scope proof |
| 1406 | feat(mail): open recognized HWPX text from email attachments | b83a0da03b46a447f9710b5f91d245f5b1783dfa | cursor/hwpx-recognized-text-preview-b246@f21811379c1cc2435eadb41bb2746b4887947d53 | yes | ingest/storage | cursor/hwpx-recognized-text-preview-b246 | experimental/draft | validate parent and promote only after scope proof |
| 1404 | feat(data): show recognized HWPX paragraph text in attachment preview | f21811379c1cc2435eadb41bb2746b4887947d53 | feat/hwpx-section-text-recognition@0fcf4d85dd70d4f2ee9dd0296fc454f764ae5326 | yes | security/governance | feat/hwpx-section-text-recognition | experimental/draft | validate parent and promote only after scope proof |
| 1403 | fix(oidc): fail closed on malformed token-endpoint escapes | 7a0b0e443ae31a941c5a2139a2093b1af876458c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1402 | feat(email-writing): add independent criterion Judge | 3d6b3341c5dd15512d5d60cd5f8d95a1bbc6d846 | feat/llm-email-writing-candidate-task6@fa844bd035ab1f188a28c58e0ed2dc45fa31d0f3 | yes | mail/calendar | feat/llm-email-writing-candidate-task6 | experimental/draft | validate parent and promote only after scope proof |
| 1401 | ⚡ Bolt: ProjectsLayout 인라인 배열 맵핑 렌더링 최적화 | 1221fc848a086db721ef1dde0a26eb6af77fe035 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1400 | feat(email): Slice 3 buyer-visible withheld-media next actions | db7ca961de800a514cf9bee34d324f1c5cf233bb | cursor/email-media-quarantine-persist-0ad6@ff1dc18cd9de5e06649ac516b163af2db4bbde83 | yes | ingest/storage | cursor/email-media-quarantine-persist-0ad6 | experimental/draft | validate parent and promote only after scope proof |
| 1399 | feat(email): Slice 3 persist quarantined inline media | ff1dc18cd9de5e06649ac516b163af2db4bbde83 | cursor/email-media-admission-wiring-cd1a@1af546dbb01964e9a620ed341ae0dd3dab9439fd | yes | ingest/storage | cursor/email-media-admission-wiring-cd1a | experimental/draft | validate parent and promote only after scope proof |
| 1398 | feat(email): Slice 3 wire admission so only document_image continues | 1af546dbb01964e9a620ed341ae0dd3dab9439fd | cursor/email-media-admission-slice3-c9de@5a80583bcabc22609e8677864ae86f867d85fd45 | yes | ingest/storage | cursor/email-media-admission-slice3-c9de | experimental/draft | validate parent and promote only after scope proof |
| 1397 | feat(email): Slice 3 inline-media admission and tracking-pixel classification | 5a80583bcabc22609e8677864ae86f867d85fd45 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1392 | docs: make README customer and operator focused | c0ac8c01d58473680b89a225107366fec4fae986 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | docs/product | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1387 | fix(a11y): keep unavailable calendar actions discoverable | 37917799e8d27c07e29eeed87a52d5be41528330 | develop@dd8d15191338b841f9e6f3a06507c6a5643b95d0 | yes | frontend/a11y | — | experimental/draft | validate parent and promote only after scope proof |
| 1384 | feat(noema): route LLM through contextual-orchestrator | 0fd330137cdd19068fa8903dc70e1dc88f42cdc9 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | llm/orchestration | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1380 | fix(dav): land capability honesty with tomllib CI import | 658f69accc627b99e379835593c2b9e49b514d00 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1376 | fix(email): expose header-derived media pixel dimensions | aae34d0a9e7d607070bc98e7b0d03e17f607dd6c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1375 | feat(email-writing): parse contextual review candidates | fa844bd035ab1f188a28c58e0ed2dc45fa31d0f3 | feat/llm-email-writing-orchestrator-task5@9cd9b953a2dd236aebe1fcdc25e59ba3e9388505 | yes | security/governance | feat/llm-email-writing-orchestrator-task5 | experimental/draft | validate parent and promote only after scope proof |
| 1373 | feat(hwpx): recognize ordered section text with provenance | 32099709bafcee19fb32c385bbe89e0df15fe102 | feat/hwp-hwpx-attachment-recognition@70683266b93233dae62faec6cbd4df118be41383 | yes | ingest/storage | feat/hwp-hwpx-attachment-recognition | experimental/draft | validate parent and promote only after scope proof |
| 1370 | feat(supply-chain): verify locked hashes against PyPI releases | 1a6ac604e159d98631b3996eb3f74d036e4a760b | feat/dependency-lock-provenance-receipt@f6eeb69f561e94cd50ae38fb1f43faa6cd2c52d7 | no | security/governance | feat/dependency-lock-provenance-receipt | stacked-child | re-fetch exact review/check state, then fix or protected-merge |
| 1369 | feat(supply-chain): attest Python lock provenance before install | f6eeb69f561e94cd50ae38fb1f43faa6cd2c52d7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1368 | ⚡ Bolt: [성능 개선] EmailDetail 개별 메시지 컴포넌트 메모이제이션 | 5c2f048c0e9fc97545e1d6f09d1379b3ae8f8b68 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1366 | fix(threading): honor RFC 5256 References ancestry | be0237714e373052b57d73e1168087da3adfda34 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1365 | fix(containers): publish explicit split runtime targets | 43666bed6214ce724d4dc50810d9f65f3d77d3f3 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1364 | feat(storage): add scoped S3 document object backend | 3a3baa6b8dc9ea224f46395cb78c91a45be2090c | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1363 | fix(governance): audit orphaned Actions workflow identities | 48593a1cab22cca86e2dbfb7e6d5cb89cf298f3c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1361 | feat(tools): add bounded content checksum generator | 5859a8f3f5e9dddf20a43313b53d7aa6453f8cd7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1356 | feat(email-writing): add hardened contextual-orchestrator boundary | 9cd9b953a2dd236aebe1fcdc25e59ba3e9388505 | feat/llm-email-writing-context-task4@4570747ccebd57ccaab30ffc68239f0c9d2f1ca0 | yes | mail/calendar | feat/llm-email-writing-context-task4 | experimental/draft | validate parent and promote only after scope proof |
| 1355 | fix(email): preserve deterministic descending thread order | fddc883ca2911c138bd9fcc3a9bd8257e1036124 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1354 | feat(ui): add Storybook design-token contract | 84edbbf152d257cd05777bf0b007fcfec2ac1d18 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1353 | feat(attachments): recognize HWP and HWPX parser boundaries | dd501dae0fc03d813f4a65aa21318cc89d1a193c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1352 | fix(a11y): expose async button busy states | 8b7731da7063c39651aa9e3debfaa2052c476c35 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1349 | docs(product): define evidence-based workspace task contract | 559d091a9a75d8e79ab9608c04931c5a1e82e173 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | docs/product | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1347 | fix(governance): reject rate-limited review status as semantic evidence | cd973fc364efb8d150786f4c2bceec54187eb806 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1345 | fix(dav): reject ambiguous nested authorization encodings | 07954b2e4d402fa2fd1e9775c52ec6b9483de52d | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1339 | fix(host-policy): normalize dotted bracketed IPv6 safely | 44b65cac131ab5c4be25cfdebc026c4a1cf3bc35 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1333 | feat: persist DiskSage file lineage ontology | 017cdef392385571acfc5abc177882724d6026b9 | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1332 | feat(email): surface calendar writeback If-Match conflicts | d53598dc7e45b470907fd97dffb9d64e954f2731 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1329 | feat(email-writing): build authorized thread context | 4570747ccebd57ccaab30ffc68239f0c9d2f1ca0 | feat/llm-email-writing-review-evidence-task3@51fb5e8543247b1e5c790f3fdf98424c8fbed669 | yes | security/governance | feat/llm-email-writing-review-evidence-task3 | experimental/draft | validate parent and promote only after scope proof |
| 1328 | feat(email-writing): persist privacy-minimized review evidence | 51fb5e8543247b1e5c790f3fdf98424c8fbed669 | feat/llm-email-writing-contracts-task2@fb7c406ee1328a6ac42dbaf54bb6852c199d8b0a | yes | security/governance | feat/llm-email-writing-contracts-task2 | experimental/draft | validate parent and promote only after scope proof |
| 1327 | feat(email-writing): define strict review contracts | fb7c406ee1328a6ac42dbaf54bb6852c199d8b0a | feat/inkspan-email-writing-guide@bfc2df112136bb9fe358778d701e78bf9e78b685 | yes | security/governance | feat/inkspan-email-writing-guide | experimental/draft | validate parent and promote only after scope proof |
| 1322 | docs(adr): design Inkspan-based LLM email writing guidance | d943203afc0afae0c9a6190681675f4d30dcf257 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1321 | fix(auth): require issued-at in Keyverse OIDC sessions | d06eff3875543b1afa28570f9269571a63a81983 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1320 | fix(calendar): expose proposal context to screen readers | 1a9afa0cf845a49db4c2eb2372f9f36eaf4c8c4e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1317 | feat: harden live macOS runtime and governance | 25d80197ee0eb8cb2aafc7d205ac7b98ccccba0c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1302 | fix(tools): remove canned source-derived tools | 2ee0c65097c78a99849fc749a3a848440c50271c | fix/remove-unsafe-phishing-detector@646a2401de35529425163fdefa7ad5e6355c349f | yes | other | fix/remove-unsafe-phishing-detector | experimental/draft | validate parent and promote only after scope proof |
| 1301 | fix(tools): remove unsafe phishing detector | 646a2401de35529425163fdefa7ad5e6355c349f | fix/fail-closed-tool-mutations@67dbfddb01bacb604a0533ce486a550115ff0d64 | yes | other | fix/fail-closed-tool-mutations | experimental/draft | validate parent and promote only after scope proof |
| 1300 | fix(tools): fail closed on unsafe global tool mutations | 7ea4bad69cf36acb9c8fbca48d32333907cce55f | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1288 | test(email): consolidate thread identity and folder visibility coverage | b7db9a316162a70bf8e594faf4f2e73766d9dc6c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1287 | 🧪 테스트: runtime_secrets.py의 build_encryption_keyring 누락된 테스트 추가 | 4de4f5d5850baf1abc05203f204c489650ba9624 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1284 | test(pdf): cover pending document decode success | 68da2a53084751361f6332ca4f3fe82c34443964 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1280 | test(search): cover configured fusion settings | 89742939fe8b9a9a33a9018d6863050f5c7a7fc7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1279 | test(tools): consolidate webhook validation and execution coverage | c6a50e97b7742a7172d80de01159516796d4d1a0 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1277 | test(core): cover connector scope statement | aa04c9392c86c29fd39cae80149fbbd02681cff8 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1267 | perf(mail): memoize email list element mapping | 8fccadb727ac54a81422642022ccc2b31723bab9 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1264 | integration: route LLM egress through EgressWeave | 5a46a85f75dfae94dd8c1f8df0b88150b40ab3c8 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | llm/orchestration | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1257 | chore(deps): update connector websockets to 17.0.1 | 4613ff5a1a85e4882af1a3a4abd0e56b3b574187 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1245 | fix(email-detail): make responsive evidence actions functional | 796b34c5a1322f09c6f00b8cf24591ae04b89b6b | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | yes | frontend/a11y | — | experimental/draft | validate parent and promote only after scope proof |
| 1244 | chore(deps): update hash-locked aiohttp to 3.14.3 | c1d4c7fd2b98e464d3ff7e92f26d92a6c0f1e6e8 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1241 | fix(a11y): show keyboard focus on OIDC actions | fb7e63dee1d72365db595edb1bc49e097202e707 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1206 | fix(security,api): opaque prompt IDs and CardDAV single-decode | d7ae4768b7c30be7bac19fb9425d40a66e8fda05 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1195 | feat(email): deterministic dedupe provenance — gate strong fingerprints on genuine Date (naruon#1086) | c7aedc6a6a09bc91156e9c62e44f18cf8b4d3846 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |

The inventory is intentionally identity-first:

It represents the 2026-08-25 102-row refresh described above, which supersedes
the v0.2 post-#1442 93-row snapshot as current evidence while that snapshot
remains historical context: no review body, credential,
customer data, or copied provider payload is stored in this document. A parent
merge or head movement invalidates the affected row and requires regeneration.

### Exact-head check observations

The following failures were also read from the live Checks API during this
snapshot and are retained as RCA pointers, not as reusable merge evidence:

| PR | Exact head | Check/run evidence | Observed cause or disposition |
|---:|---|---|---|
| #1347 | `3f6932026fbef281a373d792518058e4aaf5178f` | Strix run `32440010004`, job `96648648553` | provider/model infrastructure returned NVIDIA NIM 404 and no complete Strix report; rerun after the central fail-closed workflow repair, without weakening the gate |
| #1442 | `94e10a6188a1b96ac162fa659ae4025bc00895bd` | metadata gate `96719432050`; merged `2026-08-21T09:18:28Z` | historical pre-merge observation only; the post-merge 93-row inventory excludes this PR |
| #1443 | `62a0d645b619bcd2eac8f0db87460c5c1990d128` | new parent-head Checks queued; predecessor Strix job `97705801302` | child #1448 merged normally into this stack branch, invalidating all predecessor-head evidence. The prior provider failure was NVIDIA NIM HTTP 429 with unavailable fallback/direct OpenAI 404; current head requires fresh Checks and qualifying approval |
| #1448 | `068aefdfa48122bc73cb85a1dc23614bb09ebc04` → merge `62a0d645b619bcd2eac8f0db87460c5c1990d128` | merge-result Checks queued; Devin passed on PR head | normal stack merge at `2026-08-25T15:31:39Z`; local governance and parent synchronization tests passed. Delayed merge-result Checks are being tracked and are not represented as successful hosted evidence |

Queued or pending Checks are not treated as source failures, and completed
predecessor-head evidence is never reused.

---

## 14. Claim boundary

This baseline is a product and technical decision record, not a certification,
security attestation, market valuation, or claim that Naruon is already GA.

The existence of 100% coverage gates, many PRs, or detailed documentation does
not itself demonstrate commercial completeness. GA is demonstrated only by the
end-to-end buyer journey, current exact-head protected integration, released
artifacts, provider interoperability, recovery/customer-exit evidence, and
operational support contract defined here.
