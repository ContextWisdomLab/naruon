# Topic intelligence operability

**Status:** target operating design `PLANNED`; runtime integration
`BLOCKED-UPSTREAM`; no runtime runbook, dashboard, threshold, or SLO is claimed

The safest current operating state is “integration absent.” The pseudo-topic
removal introduces no external dependency. Everything below is a release gate
for a future adapter, not evidence that a TEPP topic service or fitted model is
available.

## Readiness gates

- Naruon receives and accepts an independently published production contract,
  immutable fitted-artifact manifest, validation packet, model card, promotion
  evidence, and named upstream owners. This is a Naruon consumption gate, not an
  assignment of work or ownership to TEPP.
- Naruon approves transport/service-authentication, evidence-reference,
  artifact-signing/registry, cache/idempotency, retention/deletion,
  sensitive-covariate, privacy/rate-limit, and downstream-authorization ADRs.
- Representative capacity tests establish request bytes, retained tokens,
  concurrency, queue, deadline, cancellation, retry, circuit-breaker, and quota
  limits.
- Authentication/authorization denial, rate limiting, deadline expiry, and
  cancellation have tested stable non-`200` mappings, bounded retry rules, and no
  scientific-abstention or fallback transition.
- Dashboards and alerts are verified with synthetic traffic and contain no raw
  content, labels, sensitive covariates, direct identifiers, or unkeyed derived
  digests.
- Operators drill artifact promotion, signer revocation, quarantine, rollback,
  tenant disable, deletion propagation, cache eviction, and full service disable.
- Every disabled, unavailable, timeout, schema, artifact, or policy state is
  verified to have no keyword, embedding, LLM, cached-other-model, category, or
  agenda fallback.

## Planned signals

| Signal | Safe dimensions | Excluded dimensions |
| --- | --- | --- |
| Request and result counts | contract/schema revision, model version, coarse status/error/abstention code, tenant-safe aggregate | content, label, direct user/source ID, raw request/result ID |
| Latency and deadline | operation, model version, coarse outcome | raw content size or rare tenant dimensions unless privacy-reviewed |
| Scientific diagnostics | pass/abstain code, privacy-reviewed aggregate retained-token/OOV bands, artifact version | terms, excerpts, per-user/group values, posterior vector |
| Artifact state | candidate/validated/approved/active/quarantined/retired and opaque registry reference | mutable filesystem path, model bytes, signing secret, raw manifest/content digest |
| Policy and audit | opaque restricted reference, purpose and decision code | credentials, provider URL, body, label, sensitive membership, raw derived digest |

Every content-, evidence-, covariate-, membership-, temporal-, design-, and
label-derived digest is a sensitive pseudonymous linkage value. It is excluded
from ordinary logs, metrics, traces, dashboards, and product payloads.
Restricted audit uses an opaque reference or tenant-scoped keyed digest with a
documented canonical representation, domain separator, TTL, deletion, and key
rotation.

Numeric objectives and alert thresholds remain `TBD` until a production TEPP
service and representative workload produce measurements. Placeholder 99.x%
targets would be false precision.

## Model and contract promotion

1. Register immutable candidate model bytes, manifest, schema, validation packet,
   model card, and build/signing provenance.
2. Verify exact schema ID/revision/digest and code-registry versions, raw artifact
   bytes, manifest, vocabulary, preprocessing, design, lineage, model-card,
   validation-report, build, signer, and promotion identities and digests.
3. Verify scientific, security, privacy, temporal, and extended-STM evidence for
   the exact candidate; reject any unreviewed method or covariate change.
4. Complete independent approval of the exact artifact and signer state.
5. Exercise shadow or restricted-tenant validation without using output for
   product decisions.
6. Promote by immutable reference; never mutate an artifact or reuse `latest`.
7. Monitor version-specific errors, abstention, diagnostic-code registry, drift,
   privacy, and capacity signals using safe dimensions.
8. Quarantine immediately on integrity, isolation, signer, material validity,
   harmful-label, temporal, or deletion concern.

Schema deployment is coordinated: producers must not send a new closed revision
until consumers pin and negotiate it. A revision uses an immutable schema
identifier and digest; cache identity must not collapse different revisions.

## Incident response

| Incident | Immediate action | Recovery evidence |
| --- | --- | --- |
| Artifact/validation-report/digest/signature/signer failure | Quarantine the exact deployment and signer, disable affected inference, preserve minimal restricted evidence | Root cause, key disposition, clean rebuilt artifact and validation report, every binding reverified, full revalidation and authorized promotion |
| Cross-tenant or purpose disclosure | Disable integration, invoke security/privacy response, stop downstream use, propagate deletion | Isolation fix, notification/deletion disposition, adversarial regression tests and controlled re-enable |
| Raw content or derived digest in telemetry | Stop emission and access, preserve only necessary incident evidence, rotate keyed material if applicable | Purge/retention disposition, redaction fix, historical search, rotation and regression evidence |
| Invalid posterior, interval, diagnostics, or unknown code | Reject as a protocol error and disable the exact model/schema/code-registry combination | Producer evidence, closed code-registry review, schema/numerical/scientific revalidation |
| Temporal or ecological misuse | Stop affected consumer and result presentation | Estimand/temporal correction, model-card review, consumer and copy tests |
| Elevated timeout/error/resource use | Open circuit, cancel bounded work, return unavailable | Capacity/root-cause evidence and controlled re-enable |
| Drift, poisoning, or harmful labels | Stop downstream use; retire label or quarantine model independently as applicable | Corpus/model/label review and new immutable version |
| TEPP unavailable | Return stable unavailable error | Health, authorization, schema, artifact, and compatibility verified before re-enable |

## Rollback principle

Rollback means disabling the adapter or selecting a previously approved,
compatible immutable artifact under an explicit audited policy. It never means
restoring removed keyword tables, calling an LLM, returning `General`, reusing a
posterior from another tenant/artifact/purpose, or generating an agenda template.
Topic identity remains model-version scoped; consumers must not compare or join
topics across model versions without a separately validated alignment.

## Recovery, replay, and deletion

A request is replayable only when the exact authorized snapshot, purpose,
consent, artifact, vocabulary, preprocessing, design, inference version,
analysis unit, estimand, temporal policy, and knowledge cutoff remain valid. An
idempotency key binds retries to that tuple and tenant scope. Replaying after
retention, consent, source access, tenant, model, signer, or policy invalidation
is forbidden even if bytes remain technically available.

Deletion must cover transient snapshots, queues, caches, persisted results,
restricted audit references, and derived linkage material under their approved
policies. Key rotation is not a substitute for deleting retained content, and
deleting product output does not by itself prove that TEPP-side state is gone.

## Ownership and handoff

Naruon operators own Naruon tenant policy, adapter enablement, product projection,
and incident coordination. Before Naruon consumes any external capability, its
published evidence must identify upstream ownership for service health, artifact
promotion/quarantine, scientific validation, deletion, incident escalation, and
a tested disable path. This document assigns no responsibility to TEPP. Naruon
keeps its own full-disable path, and a protocol failure at the ownership seam
fails closed rather than being assigned to the user or hidden by a fallback.
