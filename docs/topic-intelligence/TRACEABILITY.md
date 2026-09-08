# Topic intelligence requirements traceability

- **Document status:** `PRESENT-CURRENT`
- **Assessment date:** 2026-08-09
- **Contract revision:** `2026-08-09.1`

This matrix connects the product requirements to decisions, planned contracts,
verification, and release evidence. A documentation link proves only that a
requirement is specified. It is not evidence that a runtime capability, TEPP
production contract, fitted artifact, scientific validation, or UI exists.

Capability maturity uses only:
`IMPLEMENTED-ON-PROTECTED-DEVELOP`, `ACTIVE-PR`,
`ACCEPTED-NARUON-POLICY`, `PLANNED`, `BLOCKED-UPSTREAM`, and `OUT-OF-SCOPE`.

## Requirement matrix

| ID | Requirement summary | Decision and contract coverage | Verification or release evidence | Current maturity |
|---|---|---|---|---|
| `TI-REQ-001` | Remove `email_categorizer` and `meeting_agenda_generator`. | [ADR-0001](../adr/0001-topic-measurement-authority.md); [PRD](PRD.md); `backend/api/tools.py` candidate diff | `backend/tests/test_tools_api.py::test_registry_omits_lexical_pseudo_topic_tools`; source-symbol absence; [PR #1297](https://github.com/ContextualWisdomLab/naruon/pull/1297) exact-head checks | `ACTIVE-PR` |
| `TI-REQ-002` | Retain `keyword_extractor` only as lexical frequency/first-occurrence metadata. | [ADR-0001](../adr/0001-topic-measurement-authority.md); [PRD](PRD.md); [Architecture](ARCHITECTURE.md) no-fallback boundary | `backend/tests/test_tools_api.py::test_keyword_extractor_is_disclosed_as_lexical_term_frequency`; bounded-input handler tests | `ACTIVE-PR` |
| `TI-REQ-003` | Fail closed until a compatible independently published fitted-model contract exists; no default or substitute method. | [ADR-0001](../adr/0001-topic-measurement-authority.md); [TRD](TRD.md); [API errors](API_CONTRACT.md#http-and-abstention-semantics); [UML state model](UML.md#result-state-model) | Current registry omissions; future no-deployment, incompatible-input, upstream-fault, and no-fallback adapter tests | `ACCEPTED-NARUON-POLICY`; runtime `BLOCKED-UPSTREAM` |
| `TI-REQ-004` | Return a complete mixed-membership vector with numeric identity, explicit interval level/method/scope and diagnostics; narrowly define vector-free abstention. | [Architecture scientific invariants](ARCHITECTURE.md#scientific-invariants); [API result semantics](API_CONTRACT.md#successful-public-projection); schema `$defs.inferenceResult`, `$defs.posteriorComponent`, `$defs.diagnosticBundle` | Future schema fixtures, fitted/declared/observed/actual count equality, unique numeric-ID/rank, sum/interval-containment, code-registry, calibration/coverage, and status/diagnostic cross-checks | `BLOCKED-UPSTREAM` |
| `TI-REQ-005` | Fully specify temporal, multilevel, multiple-membership, and cross-classified extensions and keep claims non-causal. | [TRD fitted-artifact requirements](TRD.md#fitted-artifact-requirements); [Architecture scientific invariants](ARCHITECTURE.md#scientific-invariants); schema `$defs.scientificProvenance` and `$defs.designContract`; [Data model](DATA_MODEL.md#covariate-and-temporal-evidence) | Future model card/design manifest, known-truth simulation, estimator/formula/contrast tests, membership-weight normalization, unseen-level, temporal-leakage, and downstream-suppression tests | `BLOCKED-UPSTREAM` |
| `TI-REQ-006` | Bind the result to schema/source/payload/artifact/manifest/vocabulary/preprocessing/design/lineage/model-card/validation-report/evidence-time/covariate/design-row provenance; digest verifies but does not reconstruct. | [Architecture canonical provenance](ARCHITECTURE.md#canonical-provenance-and-reproduction); [API digest contract](API_CONTRACT.md#digest-contract); schema `$defs.requestIdentity` and `$defs.scientificProvenance`; [Data model](DATA_MODEL.md) | Future RFC 8785 known-answer/domain-separation, complete inventory, digest mismatch, immutable-artifact, snapshot/scope-binding, retained-snapshot replay, and deletion/retention tests | `BLOCKED-UPSTREAM` |
| `TI-REQ-007` | Keep numeric topic identity separate from versioned evidence-backed labels. | [ADR-0001](../adr/0001-topic-measurement-authority.md); [UML contract structure](UML.md#contract-structure); schema `$defs.posteriorComponent`, `$defs.presentation`, and `$defs.presentationLabel` | Future label/topic join tests, label-version/evidence tests, absent-label tests, and tests proving labels cannot alter numeric posterior fields | `BLOCKED-UPSTREAM` |
| `TI-REQ-008` | Enforce tenant/workspace/source/purpose/consent/region/retention/deletion/digest/redaction controls. | [Security](SECURITY.md); [Threat model](THREAT_MODEL.md); [API evidence rules](API_CONTRACT.md#evidence-reference-rules); schema `$defs.opaqueEvidenceRef`; [Data privacy classification](DATA_MODEL.md#privacy-classification) | Future cross-tenant/workspace denial, expiry/audience/snapshot binding, reauthorization, region/purpose/consent, deletion, cache isolation, restricted-audit, and no-log/metric/trace leakage tests | `BLOCKED-UPSTREAM` |
| `TI-REQ-009` | Keep agenda generation in a separately authorized downstream contract. | [ADR-0001](../adr/0001-topic-measurement-authority.md); [Architecture ownership](ARCHITECTURE.md#authority-and-ownership); [PRD non-goals](PRD.md#non-goals) | A separate future ADR/PRD/TRD/API/threat model plus source authorization, abstention suppression, evidence, audit, and E2E tests | `ACCEPTED-NARUON-POLICY`; future capability `PLANNED` |
| `TI-REQ-010` | Add UI only after the real runtime, uncertainty, abstention/error, security, and operational evidence exists. | [PRD success gates](PRD.md#success-and-release-gates); [Operability](OPERABILITY.md); [API public projection](API_CONTRACT.md#successful-public-projection) | Future source-backed E2E tests for loading, inferred, abstained, each error family, permission denial, rollback, accessibility, redaction, and no-fallback copy | `PLANNED` |

## Contract-to-test map

The names below are proposed acceptance tests, not current test functions unless
an existing path is explicitly named.

| Contract obligation | Proposed verification | Expected evidence owner |
|---|---|---|
| Immutable schema ID/revision and out-of-band digest pin | `test_topic_schema_id_revision_and_digest_pin`; RFC 8785 canonical known-answer fixture | Naruon adapter |
| Closed envelope and required scientific payload | `test_topic_result_schema_rejects_unknown_or_missing_fields` | Naruon adapter |
| Expected producer is conditional, not assigned ownership | Assert `x-owner=NARUON`, absence of `x-upstream-owner`, and conditional `x-expected-upstream-producer=TEPP` copy | Naruon architecture review |
| `inferred` status consistency | `test_inferred_requires_components_and_accepted_diagnostics` | Naruon adapter |
| `abstained` status consistency | `test_abstained_requires_empty_vector_and_posterior_policy_reason` | Naruon adapter |
| Numeric topic IDs/ranks and complete component count | `test_topic_components_use_numeric_identity`; `test_fitted_declared_observed_and_actual_counts_match` | Naruon adapter |
| Proportions sum to one within pinned tolerance | `test_topic_proportions_and_reported_sum_match` | Naruon adapter plus upstream numerical evidence |
| Interval containment and explicit uncertainty semantics | `test_topic_estimates_lie_inside_declared_intervals`; calibration/coverage report | Naruon adapter and independently published expected-upstream scientific evidence |
| Unsupported language/token/OOV/temporal/covariate input is an error | Parameterized route tests asserting `422` and stable RFC 9457 `error_code` | Naruon adapter |
| No active deployment/artifact/integrity is unavailable | Parameterized route tests asserting `503` and no substitute fallback | Naruon adapter/operator |
| Snapshot/revision/schema/idempotency conflict | Parameterized route tests asserting `409` | Naruon adapter |
| Invalid upstream schema/digest/cross-field result | `test_invalid_upstream_payload_is_502_not_abstention` | Naruon adapter |
| Unknown diagnostic/reason registry or code | `test_unknown_diagnostic_code_fails_closed_as_502`; exact registry-version fixtures | Naruon adapter and expected upstream producer |
| Snapshot/scope binding | Mismatched snapshot and scope refs plus current tenant/workspace/purpose/consent/region reauthorization tests | Naruon authorization boundary |
| Temporal assertion and ordering | RFC 3339 format-assertion, nullable-field policy, and availability-at-knowledge-cutoff tests | Naruon adapter and expected upstream evidence |
| Covariate/membership coupling | Typed level/missingness fixtures and invalid structure/normalization combinations | Naruon adapter and expected upstream evidence |
| No keyword/embedding/LLM/default-label/agenda fallback | `test_every_topic_failure_path_has_no_substitute_result` | Naruon adapter |
| Canonical no-covariate representation | Known-answer hashes for `{"covariates":[],"memberships":[]}` and `{"columns":[],"values":[]}` under their fixed domains | Naruon adapter and contract fixture producer |
| Retained evidence is required for replay | `test_digest_without_resolvable_snapshot_cannot_replay` | Naruon retention boundary |
| Evidence reference binding | Expired, wrong audience/snapshot/tenant/workspace/purpose tests plus reauthorization-on-use assertion | Naruon authorization boundary |
| Sensitive digest handling | Log/metric/trace/public response capture tests and restricted-audit opaque-reference test | Naruon security/observability |
| Multilevel/membership/design contract | Known-truth recovery, weight normalization, unseen-level rejection, formula/contrast and temporal-leakage fixtures | Independently published expected-upstream evidence plus Naruon compatibility validator |
| Labels remain presentation-only | Mutation and serialization tests proving labels cannot change component identity/posterior | Naruon adapter/UI |

## Error-code traceability

| Family | HTTP | Stable codes | Requirement |
|---|---:|---|---|
| Trusted request conflict | `409` | `topic_source_snapshot_conflict`, `topic_request_revision_conflict`, `topic_idempotency_conflict`, `topic_schema_revision_conflict` | `TI-REQ-003`, `TI-REQ-006`, `TI-REQ-008` |
| Authentication/authorization policy | `401`, `403` | `topic_authentication_required`, `topic_evidence_forbidden`, `topic_purpose_forbidden`, `topic_consent_required`, `topic_region_forbidden` | `TI-REQ-008` |
| Naruon request deadline | `408` | `topic_deadline_exceeded` | `TI-REQ-003`, `TI-REQ-008` |
| Input/model preflight | `422` | `topic_input_invalid`, `topic_language_unsupported`, `topic_input_insufficient_tokens`, `topic_input_out_of_vocabulary`, `topic_temporal_context_invalid`, `topic_covariate_contract_invalid` | `TI-REQ-003`, `TI-REQ-005`, `TI-REQ-008` |
| Deployment/artifact availability | `503` | `topic_deployment_unavailable`, `topic_model_artifact_unavailable`, `topic_model_artifact_integrity_failed` | `TI-REQ-003`, `TI-REQ-006` |
| Upstream execution/protocol | `502` | `topic_upstream_inference_failed`, `topic_upstream_protocol_error` | `TI-REQ-003`, `TI-REQ-004`, `TI-REQ-006` |
| Quota/rate policy | `429` | `topic_rate_limited` | `TI-REQ-008` |
| Upstream deadline | `504` | `topic_upstream_timeout` | `TI-REQ-003`, `TI-REQ-008` |
| Client cancellation | no deliverable response | internal redacted outcome `topic_request_cancelled` | `TI-REQ-003`, `TI-REQ-008` |
| Adapter defect | `500` | `topic_adapter_internal_error` | `TI-REQ-003`, `TI-REQ-008` |
| Scientific publication decline | `200` | `status=abstained` plus `posterior_*` policy reason | `TI-REQ-004` |

Authorization failures use Naruon's existing authenticated API security contract
and intentionally do not reveal whether a document, evidence reference, tenant,
workspace, or deployment exists.

## Current evidence versus blockers

| Claim | Evidence available on 2026-08-09 | Missing before runtime/UI release |
|---|---|---|
| Pseudo-topic behavior is removed | Candidate source/tests and PR #1297 | Merge and exact protected-`develop` verification |
| Lexical keyword extraction is honestly scoped | Candidate description and handler tests | Merge and protected-branch verification |
| Naruon has a local no-fallback policy | Accepted ADR-0001, AGENTS rule, PRD/TRD/architecture package | Runtime adapter negative-path tests after upstream capability exists |
| A planned Naruon envelope is specified | Revisioned JSON Schema, API/architecture/UML/data-model documents | Independently published compatible expected-upstream production contract and joint fixture review; TEPP only if it accepts that role |
| A fitted model can serve Naruon | No | Published artifact/deployment/API, model card, scientific validation, signatures/integrity, capacity and operability evidence |
| Topic results are scientifically valid | No | Representative and known-truth validation, interval calibration/coverage, diagnostics, temporal/membership validation, model promotion evidence |
| Multi-tenant handling is production safe | No topic runtime exists | Implemented authorization, evidence-reference, isolation, consent/region/retention/deletion/redaction tests |
| Topic UI is releasable | No | Real runtime, safe public projection, E2E states, accessibility, security and operational release gates |

## Release evidence bundle

Promotion from `BLOCKED-UPSTREAM` requires one exact-revision evidence bundle:

1. independently published expected-upstream production contract, fitted
   artifact, manifest, model card, scientific-validation report, and acceptance
   evidence; TEPP occupies that role only if it separately publishes and accepts
   the compatible responsibility;
2. Naruon ADR review of that exact upstream revision, including any differences
   from this planned acceptance profile;
3. schema fixtures and all cross-field/error/abstention tests above;
4. tenant/workspace/source/purpose/consent/region/retention/deletion/evidence-
   reference and sensitive-digest security evidence;
5. activation, revocation, rollback, drift, latency, availability, rate-limit,
   capacity, incident, and deletion operability evidence;
6. exact-head CI, security scans, warning-free full tests, and independent code
   review; and
7. only after items 1–6, source-backed UI and E2E evidence.

If any item is unavailable, the product remains useful without topic inference
and the topic capability stays disabled. Documentation completeness must never
be used as a substitute for upstream or runtime evidence.
