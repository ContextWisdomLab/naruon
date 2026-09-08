# Topic intelligence test strategy

**Status:** pseudo-topic removal tests `ACTIVE-PR`; target integration-test design
`PLANNED`; runtime integration evidence `BLOCKED-UPSTREAM`

## Test ownership

Naruon verifies product/API correctness, authorization, tenant isolation,
integration safety, contract enforcement, and honest presentation. Before
consumption, Naruon requires independently published upstream evidence covering
model estimation, new-document inference, conditional uncertainty, temporal and
extended-STM behavior, artifact reproducibility, and implementation parity.
Naruon may consume signed validation evidence; it must not duplicate a toy
estimator and claim that it proves upstream scientific validity. This requirement
governs Naruon's acceptance decision and assigns no obligation to TEPP.

## Current removal evidence

| Contract | Test or evidence |
| --- | --- |
| Pseudo-topic tools absent | `test_registry_omits_lexical_pseudo_topic_tools` |
| Lexical utility described honestly | `test_keyword_extractor_is_disclosed_as_lexical_term_frequency` |
| Lexical determinism, language, and empty input | Existing `keyword_extractor_handler` tests |
| Analysis input bound retained | Existing oversized-analysis-text tests |
| Documentation authority graph and planned schema | `test_topic_intelligence_documentation.py` |

All Python checks run with warnings promoted to failures. Ruff, balanced
documentation checks, and `git diff --check` are required. These checks prove
the deletion and documentation contract only; they do not prove STM behavior.

## Future Naruon contract tests

- exact accepted/rejected contract majors, immutable schema IDs/revisions and
  schema digests; unknown fields and unnegotiated revisions fail closed;
- inferred versus abstained result shapes, stable error classes, malformed
  diagnostics, exact accepted diagnostic-code registry versions, unknown-code
  rejection as a protocol error, and top-level/diagnostic status agreement;
- topic proportion range and sum tolerance; model-scoped non-semantic topic IDs;
  rank uniqueness and ordering; equality among fitted, declared, observed, and
  serialized component counts; credible-interval ordering and containment; and
  declared interval level, method, and uncertainty scope;
- exact model, manifest, artifact, vocabulary, preprocessing, design, lineage,
  model-card, evidence-time, covariate-snapshot, and design-row binding;
- canonical empty covariate/design representation and domain-separated digest
  behavior when the model uses no covariates;
- model unavailable, trusted-request conflict, deployment incompatibility,
  artifact integrity failure, unsupported language, insufficient tokens,
  excessive OOV, temporal/covariate invalidity, diagnostic abstention,
  authentication/authorization denial, rate limiting, deadline expiry,
  cancellation, bounded retry, and idempotency mismatch, each with its stable
  non-`200` mapping and retry rule where applicable;
- no keyword, embedding, LLM, cached-other-artifact, category, or agenda fallback
  on every failure, cancellation, disabled, quarantine, and rollback path;
- verified identity and tenant/workspace/user/source scope, purpose, consent,
  region, role, group, and customer-policy deny precedence;
- cross-tenant request/result/cache/idempotency/rate-limit/audit isolation;
- opaque evidence-reference audience, tenant, workspace, source, purpose, expiry,
  replay, reauthorization, redirect, SSRF, and file-path rejection behavior;
  mismatched document/evidence snapshot revisions or authorization bindings fail
  before any upstream call;
- analysis-unit, estimand, non-causal designation, covariate level, membership
  structure/normalization conditional combinations, missingness and unseen-level
  policy, minimum-cell/sparse-group suppression, public projection of required
  non-sensitive semantics, and prohibition on individual-attribute claims from
  group effects;
- immutable temporal-policy identity; asserted date-time format; nullable-time
  missingness; and ordering tests including evidence unavailable at the knowledge
  cutoff;
- safe label rendering, rejection of semantic labels as topic IDs, component/topic
  referential integrity, and independent label-evidence audience/authorization;
- one-at-a-time tampering of payload, source-snapshot, schema, raw artifact,
  manifest, vocabulary, preprocessing, design, lineage, model-card,
  validation-report, evidence-time, covariate-snapshot, design-row, signature,
  signer-state, build-provenance, and promotion-state bindings; and
- fixtures captured from the exact production TEPP implementation. Mocks alone
  are not release evidence.

## Future independently published scientific evidence

Naruon's acceptance decision requires an independently published validation
packet that includes:

- known-truth corpus simulation with label switching resolved explicitly before
  topic-wise comparison;
- topic-proportion bias and RMSE plus interval coverage/calibration for the
  declared interval level, method, and uncertainty scope;
- disclosure that new-document intervals are conditional on the frozen fitted
  artifact unless broader model/training uncertainty is separately implemented
  and validated;
- prevalence and content covariate recovery with explicit missingness;
- multilevel, multiple-membership, cross-classified, or longitudinal recovery
  only for a documented upstream extended-STM estimator, analysis unit, estimand,
  formula/contrasts, weight normalization, and unseen-level policy;
- temporal train/validation splits and knowledge-cutoff leakage checks using
  evidence availability rather than only event time;
- preprocessing, vocabulary, artifact, design, and new-document inference
  reproducibility from immutable manifests;
- unsupported-language, low-token, OOV, degenerate-document, adversarial input,
  covariate, and temporal rejection, separately from posterior/diagnostic
  abstention;
- convergence and diagnostic rejection plus immutable promotion thresholds;
- determinism within declared tolerance and CPU/GPU/alternate-runtime parity;
  and
- corpus drift and label-evidence review without silently changing numeric topic
  identity across model versions.

Scientific thresholds must come from representative data and be recorded in the
model card. This document intentionally invents no quality target.

## Security and privacy adversarial tests

- attempt cross-tenant source, result, cache, idempotency, and deletion access;
- tamper independently with the schema, payload and snapshot digests, raw artifact,
  manifest, vocabulary, preprocessing, design, lineage, model-card,
  validation-report, evidence-time, covariate/design-row, signature, signer state,
  build provenance, and promotion state;
- request a mutable alias, older artifact, revoked signer, arbitrary endpoint,
  provider URL, redirecting evidence reference, local/private address, or file
  path;
- submit oversized, multilingual, prompt-like, low-token, high-OOV, crafted
  membership, non-finite weight, missingness, and future-availability inputs;
- inspect logs, metrics, traces, problem details, audit, fixtures, and snapshots
  for raw content, excerpts, direct identifiers, credentials, sensitive group
  values, or any unkeyed content/evidence/covariate/design/label digest;
- prove tenant-keyed digests use canonical bytes and domain separation, cannot be
  compared across tenants, rotate safely, and disappear under deletion policy;
- measure repeated-query membership/model inference risk and confirm rate/query
  controls and aggregate suppression resist differencing; and
- quarantine/disable the integration during in-flight work and prove no fallback
  or stale result reaches a consumer.

## Test data

Use synthetic or appropriately licensed and de-identified corpora for CI.
Production message bodies, tenant identifiers, secrets, sensitive membership
attributes, and production-derived digests must not enter fixtures, snapshots,
logs, or external evaluation services. Multilingual and code-switching fixtures
are allowed only after the artifact declares support. Redistributable research
PDFs may be committed; otherwise cite and summarize the official source.

## Release matrix

| Gate | Removal PR | Future adapter | Future UI/downstream consumer |
| --- | --- | --- | --- |
| Focused unit and contract tests | Required | Required | Required |
| Full warnings-as-errors suite | Required | Required | Required |
| Independently published scientific validation packet | Not applicable | Required | Required |
| Tenant/security/privacy/threat tests | No new runtime boundary | Required | Required |
| Exact real-service contract E2E | Not applicable | Required | Required |
| Real PostgreSQL smoke path if persistence is added | Not applicable | Required when applicable | Required when applicable |
| Load, capacity, and numeric SLO evidence | Not applicable | Required before enablement | Required |
| Artifact quarantine, service disable, and recovery drill | No integration | Required | Required |

An unavailable external reviewer or pending GitHub check is a wait state, not
permission to weaken evidence. Merge remains subject to the repository's
current-head branch-protection and review contract.
