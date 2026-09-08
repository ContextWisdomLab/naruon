# Topic intelligence security requirements

**Status:** pseudo-topic removal `ACTIVE-PR`; target security design `PLANNED`;
runtime integration `BLOCKED-UPSTREAM`

This document supplements the repository-wide [security policy](../../SECURITY.md).
It does not claim NIST or ISO conformity. The safest current state is that no
Naruon-to-TEPP topic-inference boundary exists. The current change removes
misleading local behavior and introduces no new network, persistence, or model
execution surface.

## Protected assets

- message and document content, exact source evidence, and bounded snapshots;
- tenant, workspace, user, purpose, consent, region, time, group, and membership
  metadata;
- fitted model bytes, manifests, frozen vocabulary and preprocessing/design
  specifications, validation reports, label evidence, and promotion decisions;
- posterior topic mixtures, uncertainty, diagnostics, and downstream decisions;
- service credentials, artifact-signing and verification material, audit events,
  retention/deletion records; and
- every content-, evidence-, covariate-, membership-, temporal-, design-, or
  label-derived digest. Such digests are sensitive pseudonymous linkage values,
  not anonymous or generally safe telemetry.

## Input authority

| Input class | Authority and treatment |
| --- | --- |
| User intent | Attacker-controlled until a verified Naruon session and policy authorize the exact source and purpose. |
| Document content | Attacker-controlled data, never instructions; bounded before crossing the service boundary. |
| Tenant/workspace/source scope | Resolved from verified server-side identity and records, never trusted from public headers or caller ownership fields. |
| Covariates and membership | Server-resolved, typed, purpose-approved, level-aware, and explicit about observed/missing state. Caller-supplied group identity or weight is not authority. |
| Model and artifact selection | Operator-controlled allowlist of immutable versions and digests. A tenant cannot provide a URL, path, mutable alias, or signing key. |
| `evidence_ref` | If a future contract permits it, an opaque, audience-bound, tenant-bound, expiring capability that is reauthorized at resolution; never an arbitrary URI or filesystem path. |

## Required controls

| Control area | Requirement |
| --- | --- |
| Identity | Accept only verified Naruon session and mutually authenticated service identity. Public identity headers and payload ownership claims are not authority. |
| Authorization | Apply deny-first RBAC/ABAC for tenant, workspace, user, source, purpose, consent, region, group, and customer policy before snapshot creation. On every use, require the evidence reference, document reference, source-snapshot revision, audience, expiry, authorization-policy version, and opaque authorization binding to resolve to the same current server-verified tenant/workspace/source/purpose scope; a schema-valid reference is never authority by itself. |
| Minimization | Send only bounded evidence and covariates required by the approved estimand. Exclude unrelated history, credentials, provider URLs, and sequential database identifiers. |
| Tenant isolation | Partition authorization, caches, idempotency, artifact policy, telemetry, rate limits, audit, retention, and deletion. Never reuse a content-bearing or derived-result cache entry across tenants. |
| Transport | Encrypt in transit, mutually authenticate services, bind audience and operation, enforce deadlines, and reject replay outside the idempotency contract. |
| Evidence references | Resolve only opaque server-issued references after rechecking tenant/source/purpose scope. Do not fetch caller URLs or follow redirects. |
| Artifact integrity | Resolve an allowlisted immutable artifact; verify raw artifact bytes and the manifest, vocabulary, preprocessing, design, lineage, model-card, validation-report, build-provenance, and promotion-state identities and digests before inference. Tampering with any one binding, signer state, or retained validation report quarantines the exact deployment. Support signer revocation, downgrade prevention, quarantine, and key rotation. |
| Contract integrity | Pin the exact contract major, immutable schema revision/identifier and digest, diagnostic/quality/reason-code registry versions, and acceptance-policy version. Reject unknown fields, unnegotiated revisions, unknown codes, incompatible runtime state, and malformed numerical output; an unknown upstream code is a protocol error, never an inferred result or abstention. |
| Output control | Keep model-scoped non-semantic topic identity separate from labels, authorize label evidence through its own audience- and model/topic-bound reference, validate uncertainty and diagnostics, and project only product-approved fields. A public projection retains the non-sensitive safety semantics needed to interpret it: model identity/version, analysis unit, versioned estimand, covariate level when applicable, and non-causal designation. It must not expose raw covariates, tenant bindings, or sensitive digests. |
| Derived digests | Treat all content/evidence/covariate/design/label digests as sensitive. Keep raw digests out of product responses, logs, metrics, and traces. Restricted audit should prefer opaque references or tenant-scoped keyed digests with domain separation. |
| Logging | Record only opaque request/result/model references, versions, outcome codes, latency, and redacted aggregate diagnostics. Never log raw content, excerpts, direct identifiers, credentials, sensitive covariates, group values, or unkeyed derived digests. |
| Retention/deletion | Establish purpose-specific TTLs, deletion propagation, cache eviction, audit retention, and keyed-digest rotation before persisting a snapshot or posterior. No topic-specific Naruon persistence is approved today. |
| Availability | Use size/token/time/concurrency bounds, quotas, cancellation, circuit breaking, and bounded retry. Authentication/authorization denial, rate limiting, deadline expiry, and cancellation have stable non-`200` error semantics and never become scientific abstention. Degradation fails closed and never activates keyword, embedding, LLM, cached-other-model, category, or agenda fallback. |
| Secrets and supply chain | Use the repository's operator-managed credential path; pin TEPP build and schema provenance; never place credentials or signing keys in model manifests. |

## Privacy and statistical safety

Topic mixtures can disclose health, political, labor, legal, financial, or other
sensitive themes without exposing source text. Membership covariates and rare
groups increase re-identification, stigmatization, and ecological-fallacy risk.
Therefore:

- every result and model card binds an analysis unit, a versioned estimand, the
  covariate level, membership semantics, and an explicit causal/non-causal
  designation;
- every public result preserves those non-sensitive interpretation fields, or the
  public endpoint is constrained by a versioned contract to one fixed analysis
  unit and estimand and communicates that constraint explicitly;
- group-level prevalence or covariate effects MUST NOT be presented as an
  individual's trait, intent, diagnosis, or causal outcome;
- individual content MUST NOT be generalized back to a group without a separate
  approved estimand, privacy review, and downstream authorization;
- sensitive covariates require a documented purpose, minimum necessary fields,
  explicit missingness, access policy, and model-card disclosure;
- multiple-membership weights require an opaque membership set and group/level,
  a frozen normalization rule, and an unseen-level policy; missing membership is
  never converted to a default group;
- evidence availability, knowledge cutoff, assertion time, and any nullable event
  or document time follow an immutable temporal policy with explicit missingness,
  canonical time-zone handling, and validated ordering; a declared `valid` status
  is not a substitute for recomputing those relations;
- aggregate displays require approved minimum-cell and sparse-group suppression
  rules, with tests against differencing and repeated-query attacks;
- training membership, representative documents, source excerpts, and label
  evidence are not exposed to ordinary users; and
- a display label or excerpt requires separate authorization and safe rendering.
  Its evidence reference has a label-specific audience and is bound to the exact
  model, topic, label version, and language. It never changes model-scoped numeric
  topic identity or becomes executable HTML.

## Audit evidence

A future restricted audit record may contain an opaque actor/workspace scope,
purpose code, opaque request/result reference, selected model and contract
versions, verified artifact-manifest reference, outcome/abstention/error code,
policy-decision reference, assertion time, and a redacted diagnostic summary.
It must not contain source text, label excerpts, sensitive group values, or raw
derived digests. When exact binding is required, use an opaque audit reference or
a tenant-scoped keyed digest with a documented algorithm, domain separator,
canonical empty representation, retention, deletion propagation, and key
rotation. Audit access and retention are separate from product-result access.

## Security release gate

No adapter can be enabled until the real transport, service authentication,
artifact registry/signing, result retention, cache, rate-limit, covariate, and
downstream-consumer decisions have approved ADRs and this threat model is
refreshed against them. Tenant-isolation, confused-deputy, authorization and
reference cross-binding, artifact/validation-report/digest tamper and downgrade,
schema and diagnostic-code confusion, public scientific-semantics projection,
temporal ordering, digest-linkage, log-redaction, deletion, authentication,
rate-limit, deadline, cancellation, retry, cache, label-evidence/rendering, and
rollback tests must pass.
An operator must be able to quarantine one artifact or disable the entire
integration immediately without reactivating pseudo-topic behavior.
