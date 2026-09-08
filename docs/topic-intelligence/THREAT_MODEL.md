# Threat model: topic intelligence

- **Status:** design-time model `PLANNED`; runtime integration `BLOCKED-UPSTREAM`
- **Scope:** the future Naruon-to-TEPP topic-intelligence boundary
- **Review trigger:** a real TEPP transport, artifact store, persistence design,
  covariate, downstream consumer, or UI

## Overview

Naruon is a tenant-scoped email/PIM hub. A future topic-intelligence path may
authorize a bounded document snapshot, send it to a separately deployed TEPP
measurement service, validate a fitted-model result, and expose a policy-filtered
posterior or explicit abstention. That runtime path does not exist today. The
current pseudo-topic removal reduces attack surface and introduces no new
network or persistence boundary.

This model is intentionally narrower than the repository-wide security policy.
It covers confidentiality, tenant isolation, scientific integrity, statistical
misuse, provenance, model supply chain, and availability at the planned boundary.
TEPP training internals remain out of scope until TEPP implements and publishes
their production contracts, but Naruon release gates still require evidence
about those controls.

## Threat model, trust boundaries, and assumptions

### Actors

- an ordinary or malicious tenant user, including a tenant administrator;
- an attacker controlling imported email/document content;
- a compromised Naruon or TEPP service or service credential;
- a compromised artifact publisher, registry, signer, or verification key;
- an insider with model, corpus, label-evidence, or audit access; and
- a network attacker capable of observing, replaying, or tampering with traffic.

### Trust boundaries

| Boundary | Data crossing | Security invariant |
| --- | --- | --- |
| Browser/client to Naruon | Opaque source selection and processing intent | Verified signed session; server-resolved tenant/workspace/source/purpose; document/evidence/snapshot/audience/expiry/policy bindings cross-checked on every use; deny before snapshot creation. |
| Naruon records to snapshot | Minimized content, times, and approved covariates | Re-read ownership and policy; enforce bounds; content remains attacker-controlled data. |
| Naruon to TEPP | Bounded content or opaque evidence capability, model policy, provenance, idempotency | Mutual authentication, audience binding, encryption, schema and deadline bounds, no arbitrary URL/path. |
| Artifact registry to TEPP | Immutable manifest, model, vocabulary, preprocessing/design, validation evidence | Allowlist, signature/digest verification, signer revocation, downgrade protection, quarantine. |
| TEPP to Naruon | Posterior or abstention, diagnostics, model and provenance binding | Exact schema and code-registry revisions/digests, request/result binding, numerical and scientific invariant checks, unknown-code rejection, no fallback. |
| Result to product/audit | Policy-filtered output and restricted metadata | Preserve model-scoped topic identity, analysis unit, estimand, covariate level when applicable, and non-causal status; separate permissions and retention; no source text or raw derived digest in ordinary telemetry. |

Attacker-controlled inputs include document bytes, language-like content,
prompt-like strings, repeated query patterns, oversized/OOV documents, and user
intent. Operator-controlled inputs include allowed service endpoints, model and
schema versions, verification keys, promotion state, quotas, and feature-disable
controls. Developer-controlled inputs include code, contract fixtures, migrations,
and release configuration; they are not trusted merely because they are local.

## Attack surface, mitigations, and attacker stories

| ID | Threat | Example impact | Required mitigation | Residual disposition |
| --- | --- | --- | --- | --- |
| `TI-T01` | Identity or scope spoofing | A caller references another tenant's source or model policy. | Verified session/service identity; server-side scope re-read; deny-first RBAC/ABAC. | Reassess with real auth protocol. |
| `TI-T02` | Artifact, validation-evidence, digest, downgrade, or signer compromise | A poisoned or stale model or substituted validation report is served as approved. | Verify raw artifact bytes and every manifest, vocabulary, preprocessing, design, lineage, model-card, validation-report, build, signer, and promotion binding; signer revocation, monotonic policy, quarantine, and rollback. | Signing/registry ADR required. |
| `TI-T03` | Repudiation | An operator cannot prove which model, purpose, and policy produced a result. | Append-only restricted audit with opaque refs, versions, artifact-manifest ref, policy decision, and times. | Durable audit design is planned. |
| `TI-T04` | Content or posterior disclosure | Logs, labels, caches, responses, or evidence reveal sensitive themes or cross-tenant data. | Minimization, output projection, tenant-partitioned caches, separate label/evidence permission, deletion tests. | Corpus-specific sensitivity review required. |
| `TI-T05` | Digest linkage or dictionary attack | A raw content, covariate, membership, evidence, design, or label digest links records or reveals a low-entropy value. | Exclude raw derived digests from product/telemetry; use restricted opaque refs or tenant-keyed, domain-separated digests with TTL and rotation. | Canonicalization/key design required. |
| `TI-T06` | Denial of service | Oversized/OOV documents, expensive inference, or retry storms exhaust capacity. | Input/token/concurrency limits, quotas, deadlines, cancellation, bounded retry, circuit breaker, and stable rate/deadline/cancellation errors that cannot become abstention. | Numeric limits require load evidence. |
| `TI-T07` | Privilege escalation | A member invokes an admin-only model/purpose or selects an arbitrary artifact/endpoint. | Server-owned policy allowlist, role and purpose checks, no caller URL/path or mutable alias. | Policy mapping is planned. |
| `TI-T08` | Training or label poisoning | Malicious corpus data shifts topics, labels, or downstream decisions. | Corpus provenance, quality checks, held-out and known-truth validation, independent promotion, label evidence review, rollback. | Naruon requires concrete independently published upstream controls and evidence before consumption. |
| `TI-T09` | Membership or model inference | Repeated queries reveal corpus membership or reconstruct model properties. | Per-principal/tenant query controls, coarse diagnostics, no exemplars, abuse monitoring, empirical privacy tests before exposure. | Privacy test method is unresolved. |
| `TI-T10` | Semantic or diagnostic-code confusion | A keyword, embedding, LLM label, old model, truncated vector, unknown quality code, or another tenant's cache is accepted as an STM posterior. | Strict model-scoped non-semantic topic identity, exact fitted/result/observed component counts, versioned closed diagnostic-code registries, artifact and request binding, label separation, partitioned cache, compatibility tests, no fallback. | Guarded by ADR and contract tests. |
| `TI-T11` | Ecological fallacy or stigmatization | A group prevalence estimate becomes an asserted individual trait or individual content stigmatizes a group. | Public and internal results preserve analysis unit/estimand/covariate level/non-causal status; model-card review, minimum-cell/sparse-group suppression, product-copy and downstream tests. | Human governance remains required. |
| `TI-T12` | Temporal leakage | A model or covariate uses evidence unavailable at the asserted knowledge cutoff. | Immutable temporal-policy identity/digest, evidence-time/covariate/design-row binding, explicit missingness and canonical time parsing, availability-at-cutoff ordering recomputed by Naruon, time-sliced validation. | Naruon requires independently published upstream temporal-validation evidence before consumption. |
| `TI-T13` | Confused deputy or unsafe evidence reference | An external service uses Naruon's authority to fetch unrelated content, follows an attacker URL, or Naruon accepts an unbound result. | Push bounded content or use opaque audience/tenant/workspace/source/purpose/snapshot-bound expiring capabilities; cross-check document and snapshot revisions, reauthorize resolution, no redirects, exact request/result binding. | Reassess with transport. |
| `TI-T14` | Covariate or membership manipulation | A caller supplies a privileged group, fabricated missingness, or weights that change the estimate. | Server-resolved typed covariates; frozen formula/contrast, normalization and unseen-level policy; finite/range checks. | Extended-STM contract is planned. |
| `TI-T15` | Label/evidence injection | Prompt-like corpus text manipulates a generated label, a semantic label is smuggled in as topic identity, or active markup reaches a UI. | Model-scoped non-semantic topic IDs; label-specific evidence reference and audience bound to model/topic/version/language; component referential checks; constrained output, escaping/sanitization, provenance and human review. | UI/label pipeline does not exist. |
| `TI-T16` | Incomplete deletion or cross-purpose replay | Revoked content remains in snapshots, caches, audit, or an idempotent replay. | Purpose TTL, deletion propagation, cache eviction, consent/policy recheck before replay, keyed-digest rotation. | Retention ADR required. |

Representative abuse cases include crafted multilingual/OOV documents intended
to force a convenient default label, repeated near-duplicate queries intended to
extract corpus membership, a deprecated artifact requested through a mutable
alias, and timeouts intended to activate a cheaper keyword path. Every case must
end in denial, a stable error, or an explicit model-governed abstention. None may
change the measurement method.

Out of scope for the current removal are attacks requiring a deployed TEPP
endpoint, model registry, topic store, or topic UI because none exists. They are
still release blockers for the future integration, not evidence that the threat
is impossible.

## Severity calibration

- **Critical:** cross-tenant source/posterior disclosure at scale; compromise of
  an artifact-signing root that silently promotes attacker-controlled models;
  service identity compromise that grants unrestricted tenant corpus access.
- **High:** unauthorized inference of sensitive themes; persistent raw content
  or low-entropy derived digests in broadly accessible logs; poisoning that
  materially alters product decisions; bypass of purpose, consent, or region
  policy; arbitrary evidence-reference network/file access.
- **Medium:** tenant-local resource exhaustion with bounded recovery; harmful or
  misleading labels that do not alter numeric identity; incomplete redaction in
  a restricted operator surface; reproducibility or temporal defects that block
  scientific use but do not expose another tenant.
- **Low:** documentation-only inconsistency while the runtime remains disabled,
  or a non-sensitive diagnostic formatting defect with no policy, integrity,
  availability, or disclosure impact.

Repository policy requires remediation of Medium-and-higher validated findings.
Severity must be reassessed against the real transport, data volume, privileges,
and downstream decisions.

## Security decisions still required

Before implementation, approve ADRs for service authentication, transport and
evidence-reference semantics, artifact signing/registry and signer revocation,
cache/idempotency partitioning, result/audit retention and deletion, sensitive
covariates, privacy testing, rate limits, and downstream-consumer authorization.
The conceptual schema silently decides none of these.
