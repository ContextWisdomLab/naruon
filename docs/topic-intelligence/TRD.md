# Technical requirements: topic intelligence

- **Status:** deletion `ACTIVE-PR`; Naruon-local policy
  `ACCEPTED-NARUON-POLICY`; runtime adapter `BLOCKED-UPSTREAM`
- **Normative language:** MUST, MUST NOT, SHOULD, and MAY express obligations for
  a future Naruon implementation.
- **Accepted local decision:** [ADR-0001](../adr/0001-topic-measurement-authority.md)
- **Proposed target decisions:**
  [ADR-0002](../adr/0002-fitted-topic-artifact-consumption.md) and
  [ADR-0003](../adr/0003-separate-topic-measurement-from-agenda-generation.md)

## Current deliverable

PR #1297 MUST remove `email_categorizer`, `meeting_agenda_generator`, their fixed
dictionaries, matching helpers used only by them, registry entries, and
behavior-locking tests. It MUST retain the existing input bound for the honest
lexical utility and describe that utility as deterministic lexical frequency and
first-occurrence metadata.

This change MUST NOT add a replacement topic handler, route, table, migration,
model fit, network dependency, embedding/LLM fallback, default label, template
agenda, or simulated success response.

## Authority and ownership

This TRD records Naruon requirements only. It does not govern an upstream
publisher, transfer scientific authority, or claim that TEPP or another producer
accepted a Naruon envelope. A Naruon adapter remains blocked until a publisher
independently publishes a versioned production fitted artifact/API/contract and
its own acceptance evidence. Every reference below to published upstream
evidence is a condition on Naruon's consumption decision, not an obligation this
TRD assigns to the publisher.

| Boundary | Naruon responsibility | Published upstream evidence Naruon requires before consumption |
| --- | --- | --- |
| Authorization | Tenant/workspace/user/source/purpose checks | Documented service authentication and authorization at upstream ingress |
| Input | Bounded, minimized, immutable authorized snapshot or evidence reference | Published input schema and frozen-preprocessing compatibility rules |
| Model | Select only an operator-approved published model policy | Published fitting, validation, versioning, promotion, and serving evidence |
| Result | Pin schema revision; validate, policy-filter, present, and audit metadata | Published posterior/abstention, uncertainty, diagnostic, and scientific-validation contract |
| Downstream action | Govern search, norm-group use, labels, or agenda generation separately | No implied Naruon product action |

Naruon MUST NOT read an upstream private database or mount a mutable model path as
an implicit contract. A versioned authenticated service, event, or artifact
boundary MUST be the only integration seam.

## Input requirements

A future request MUST include or resolve server-side:

- an opaque document snapshot/evidence ID, content digest, one bounded content or
  evidence representation, language support signal, declared purpose, and
  event/assertion/availability/knowledge-cutoff times where applicable;
- tenant/workspace/source authority derived from verified server-side identity,
  never public identity headers or caller-supplied ownership;
- an operator-approved model policy and exact contract/schema compatibility
  requirement; and
- only purpose-approved covariates, with typed observed/missing state and, when
  applicable, level, membership-set, weight, normalization, and unseen-level
  semantics.

Credentials, provider URLs, sequential internal database IDs, unrelated
messages, and unbounded conversation history MUST NOT cross the boundary.

## Fitted-artifact requirements

Naruon MUST accept a published fitted artifact only when it is immutable and
content-addressed. Naruon MUST require the integrity-protected evidence bundle to
contain and match every field in the [canonical 14-field digest
inventory](README.md#canonical-digest-inventory), including
`model_card_digest`, `validation_report_digest`,
`covariate_snapshot_digest`, and `design_row_digest`. Beyond those canonical
bindings, the published evidence must identify at least:

- model ID/version, training-corpus lineage, training cutoff, and knowledge
  policy;
- preprocessing implementation/version, token-retention rules, supported
  languages, and frozen vocabulary;
- topic count and numeric identities, prevalence/content designs, covariate and
  missing-value schemas;
- inference implementation/version, numerical backend, diagnostics, validation
  report, model-card identity, and promotion state; and
- separately versioned label evidence, never used as numeric topic identity.

Naruon MUST reject any digest, schema, language, vocabulary, design, runtime, or
signature mismatch. Naruon MUST NOT silently choose an older or “closest” model
unless a separately accepted, audited compatibility policy names it.

Standard STM references do not establish temporal, multilevel, multiple-
membership, or cross-classified estimation automatically. To satisfy Naruon's
acceptance criteria, Naruon MUST accept a published model claiming any extension
only when its artifact, model card, and validation evidence name the estimator,
analysis unit, estimand, prevalence/content formula and contrasts, opaque level
and membership semantics, weight normalization, unseen-level policy, non-causal
status unless a causal design is independently established, and known-truth
validation for the extension.

## Result requirements

An `inferred` result MUST contain non-negative topic proportions that sum to one
within a versioned tolerance; unique numeric topic IDs; inference implementation
and numerical backend; diagnostic status, stable convergence code, explicit
numerical status, and bounded stable quality codes; and exact request, model,
analysis-unit, estimand, purpose, and knowledge-cutoff provenance. It MUST carry
all 14 canonical digest fields, rather than a shortened or aliased subset, so the
schema, source snapshot, complete scientific payload, artifact, manifest,
vocabulary, preprocessing, design, lineage, model card, validation report,
evidence-time manifest, covariate snapshot, and design row are each bound.

Each credible interval MUST state its level, method, and uncertainty scope. The
default scope is conditional on the frozen fitted artifact. Product copy MUST NOT
imply that it covers model selection, training-corpus, label, or all parameter-
estimation uncertainty unless the published model card and calibration evidence
support that broader claim.

Labels MAY be absent. If present, each label MUST carry a label identity,
version, language, and evidence reference/digest separate from
`(model_id, model_version, topic_id)`. Consumers MUST join on numeric topic
identity and model version, not display text.

## Error and abstention requirements

The future adapter MUST distinguish:

- model/service unavailable;
- unsupported contract or schema revision;
- request/idempotency/model-policy conflict;
- deployment, preprocessing, vocabulary, design, or runtime incompatibility;
- artifact/manifest integrity failure;
- unsupported language, insufficient retained tokens, excessive OOV input, or
  invalid temporal/covariate input;
- authorization/purpose/consent/region denial; and
- timeout or cancellation.

Those conditions are errors and MUST produce no posterior, label, or agenda.
HTTP bindings SHOULD use RFC 9457 problem details with a stable Naruon-defined
`error_code` extension and redacted public detail.

`abstained` is a successful scientific state only after a compatible active
model accepts the input contract but a declared posterior or diagnostic
acceptance rule declines. It MUST contain a stable reason and MUST NOT contain a
topic vector or label.

Every error and abstention path MUST preserve the no-fallback boundary. Naruon
MUST NOT change the measurement method to keywords, embeddings, clustering,
zero-shot/LLM labels, a cached result from another artifact, a default category,
or a template agenda.

## Verification, replay, and retention

All 14 fields in the canonical digest inventory verify that available bytes and
definitions match approved evidence; they do not reconstruct missing content.
Every content-, evidence-,
covariate-, membership-, temporal-, design-, and label-derived digest is
sensitive pseudonymous linkage data. A later claim of replay or
reproducibility MUST additionally prove that the exact authorized snapshot or
evidence reference, model artifact, manifest, vocabulary, preprocessing, design,
lineage, model card, validation report, evidence-time manifest, covariate
snapshot, design row, inference version, purpose, consent, retention, and
knowledge-cutoff context remain resolvable and valid.

An idempotency key MUST bind retries to that tuple. Replay after consent,
retention, tenant, source, model, or policy invalidation is forbidden even if
the original bytes remain technically accessible.

## Security and privacy requirements

- Enforce deny-first RBAC/ABAC, tenant isolation, purpose limitation, consent,
  region, retention, and deletion before snapshot materialization.
- Mutually authenticate and authorize the service boundary and protect content
  and metadata in transit.
- Resolve only allowlisted immutable artifact references and verify integrity
  before inference.
- Exclude raw content, plain content digests, excerpts, credentials, direct user
  identifiers, and sensitive covariate values from ordinary logs, metrics,
  traces, and public errors.
- Treat plain content digests as sensitive pseudonymous linkage values. A
  restricted audit store SHOULD prefer opaque references or tenant-scoped keyed
  digests with bounded retention, rotation, and deletion propagation.
- Partition caches, artifact policy, idempotency, telemetry, and deletion work by
  tenant and purpose.

## Compatibility and implementation gates

The future adapter MUST use an explicit contract major and exact closed schema
revision. Unknown fields are rejected. An additive field may stay in one major
only after a new closed revision is published, pinned, deployed to consumers,
and explicitly negotiated before the producer sends it. Changed meaning, topic
identity, required fields, or preprocessing semantics requires a new major or
artifact version.

Runtime work remains blocked until all of the following are true:

1. An upstream publisher independently publishes a production fitted-model
   artifact/API/contract and its own acceptance evidence.
2. Naruon reviews that exact contract against ADR-0001 and updates this package
   without treating the current planned envelope as upstream authority.
3. Upstream scientific evidence covers estimation, calibration/coverage,
   diagnostics, model card, promotion, and any extended-STM claims.
4. Naruon accepts separate transport/authentication, artifact-signing/registry,
   retention/deletion, cache, rate-limit, sensitive-covariate, and downstream-
   authorization decisions.
5. Contract fixtures from the exact upstream implementation pass Naruon schema,
   invariant, failure, abstention, isolation, redaction, timeout, rollback, and
   real-service E2E tests with warnings treated as failures.
6. Representative load establishes numeric limits and SLOs.
7. A UI is considered only after all preceding gates are real.
