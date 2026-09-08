# Planned topic-inference API contract

- **Capability maturity:** `BLOCKED-UPSTREAM`
- **Document status:** `PRESENT-CURRENT`
- **Contract version:** `topic-inference-result-v1`
- **Contract revision:** `2026-08-09.1`

There is no shipped topic-inference endpoint in Naruon today. This document
defines the Naruon-side contract that may be implemented only after TEPP
independently publishes a compatible production fitted-model artifact and
inference boundary with its own acceptance evidence.

## Contract layers

Three representations must not be conflated:

1. **Authenticated Naruon API.** A browser or API client submits opaque source
   references. Naruon reauthorizes and resolves server-authoritative evidence.
2. **Internal Naruon adapter envelope.** Naruon binds an immutable snapshot,
   schema/deployment pins, sensitive canonical digests, error mapping, and
   scientific acceptance policy. The result schema in this package applies to
   this internal envelope.
3. **Expected upstream scientific payload.** Naruon expects the independently
   accepted producer to own fitted-model inference evidence nested under
   `tepp_payload`. TEPP is only the expected producer if it separately publishes
   a compatible production contract and accepts that responsibility; this local
   schema does not assign it or claim adoption.

The authenticated API returns a redacted projection of the internal envelope.
Sensitive digests, tenant/workspace bindings, covariate values, design rows, and
raw evidence locations must not cross the public boundary.

## Planned endpoint

`POST /api/topic-intelligence/inferences`

The route is private and signed-session authenticated. Its final implementation
must scope every lookup by the authenticated owner, organization, and workspace.
Elevated platform roles do not automatically become the mailbox/document owner.

### Request

```json
{
  "document_ref": "doc_Q7mWQVp1jJHq5J3e",
  "evidence_ref": "ev_q9BH7d4eMG3A2x6n",
  "request_revision": "reqrev_01",
  "idempotency_key": "a-client-generated-bounded-opaque-value",
  "expected_snapshot_revision": "snaprev_184",
  "language": "ko-KR",
  "purpose": "topic_assistance"
}
```

| Field | Rule |
|---|---|
| `document_ref` | Opaque source identifier. It is not a database primary key, provider message ID, URL, or path. |
| `evidence_ref` | Opaque, audience-bound, snapshot-bound, tenant/workspace-bound, expiring capability reference. Naruon reauthorizes it at use time and never dereferences client-controlled URLs or paths. |
| `request_revision` | Bounded opaque revision used for optimistic request compatibility. Reusing it for different canonical content is a conflict. |
| `idempotency_key` | Bounded opaque client token. Naruon stores/compares only a protected tenant-keyed representation; reuse with a different canonical request returns `409`. |
| `expected_snapshot_revision` | Optional optimistic pin. The route compares it with the newly authorized server snapshot; mismatch returns `409`. |
| `language` | Required BCP 47 tag selected or confirmed by the caller. A homemade keyword/script detector must not silently override it. Model support is checked during preflight. |
| `purpose` | Must equal an allowlisted, consented purpose. Revision `2026-08-09.1` defines only `topic_assistance`. |

The public request never contains raw email/document content, topic labels,
tenant identifiers, model display names, covariate values, membership labels,
or upstream endpoints. Naruon derives the canonical internal request from the
reauthorized snapshot and active deployment.

### Successful public projection

HTTP `200` has exactly two semantic states:

- `inferred`: an accepted mixed-membership posterior is available;
- `abstained`: compatible input and model reached inference, but the attempted
  posterior or a declared diagnostic/acceptance rule declined publication.

```json
{
  "request_id": "tir_3FQn1v8H2zK6cP4m",
  "status": "inferred",
  "model_id": "opaque-versioned-model-id",
  "model_version": "opaque-versioned-model-ref",
  "analysis_context": {
    "analysis_unit": "document",
    "estimand_id": "document_topic_mixture",
    "causal_design": "non_causal",
    "covariate_level": "analysis_unit"
  },
  "credible_level": 0.95,
  "interval_method": "upstream-declared-method",
  "uncertainty_scope": "conditional_on_fitted_artifact",
  "topics": [
    {
      "topic_id": 17,
      "rank": 1,
      "proportion": 0.62,
      "credible_interval": {"lower": 0.51, "upper": 0.72}
    },
    {
      "topic_id": 4,
      "rank": 2,
      "proportion": 0.38,
      "credible_interval": {"lower": 0.28, "upper": 0.49}
    }
  ],
  "diagnostic_status": "accepted",
  "completed_at": "2026-08-09T12:00:00Z"
}
```

Human-readable labels, if later exposed, use a separate `presentation` object
with their own version and evidence references. They do not replace `topic_id`
or alter posterior values.

An abstention has no usable topic components:

```json
{
  "request_id": "tir_B7p4K2m9Q5x1V8nD",
  "status": "abstained",
  "model_id": "opaque-versioned-model-id",
  "model_version": "opaque-versioned-model-ref",
  "analysis_context": {
    "analysis_unit": "document",
    "estimand_id": "document_topic_mixture",
    "causal_design": "non_causal",
    "covariate_level": "analysis_unit"
  },
  "credible_level": 0.95,
  "interval_method": "upstream-declared-method",
  "uncertainty_scope": "conditional_on_fitted_artifact",
  "topics": [],
  "diagnostic_status": "rejected",
  "abstention_reasons": ["posterior_uncertainty_exceeds_policy"],
  "completed_at": "2026-08-09T12:00:00Z"
}
```

The response must carry `Cache-Control: no-store`. The UI must render an
abstention as unavailable evidence, not as a zero-probability topic, successful
classification, or reason to invoke agenda generation.

`model_id`, `model_version`, and `analysis_context` are required safe semantic
context, not optional UI decoration. Consumers join numeric topic IDs only within
that model identity and must display/use the analysis unit, estimand, coarse
covariate level, and `non_causal` designation so group-level effects cannot be
presented as an individual's trait or causal outcome. No group value, membership
identifier, raw covariate, or sensitive digest is exposed.

## Internal adapter envelope

The internal response validates against
[`topic-inference-result-v1.schema.json`](schema/topic-inference-result-v1.schema.json),
whose immutable identifier is:

`https://naruon.net/schemas/topic-intelligence/topic-inference-result-v1/2026-08-09.1`

The adapter configuration pins both that `$id` and the `schema_digest`
construction defined in [Digest contract](#digest-contract). A response repeats
the ID, revision, and complete canonical-digest record. The schema intentionally
does not embed its own expected digest value because that value is distributed
out of band with the adapter configuration.

The envelope is Naruon-owned and requires:

- opaque request, document, snapshot, expiring evidence-reference identity, and
  matching server-created snapshot/scope bindings;
- schema revision/digest and adapter version;
- source-snapshot and nested scientific-payload digests;
- the independently accepted expected-upstream scientific payload nested under
  `tepp_payload`, including all scientific provenance, design, posterior,
  uncertainty, and diagnostics fields; and
- optional versioned presentation labels outside the scientific payload.

The envelope and its digests are internal validation data. The public projection
above deliberately omits them.

## HTTP and abstention semantics

| HTTP | `error_code` or status | When it applies | Retry rule |
|---:|---|---|---|
| `200` | `inferred` | Compatible request, active verified deployment, valid payload, and accepted posterior/diagnostics | Normal result |
| `200` | `abstained` | Compatible request/model reached inference, but posterior uncertainty, diagnostics, or pinned publication policy rejected release | Do not retry unchanged input/model/policy |
| `401` | `topic_authentication_required` | No valid signed session or service identity is present | Authenticate; do not reveal resource existence |
| `403` | `topic_evidence_forbidden` | Evidence authorization fails for the current owner/tenant/workspace | Do not retry without a new authorization decision |
| `403` | `topic_purpose_forbidden`, `topic_consent_required`, `topic_region_forbidden` | Purpose, consent, or region policy denies processing | Policy/consent remediation; no upstream call |
| `409` | `topic_source_snapshot_conflict` | Expected and current authorized snapshot revisions differ | Refresh source state |
| `409` | `topic_request_revision_conflict` | A trusted request revision is incompatible with the canonical request | Create a new revision after refresh |
| `409` | `topic_idempotency_conflict` | An idempotency key was previously bound to different canonical request material | Use a new key only for a genuinely new operation |
| `409` | `topic_schema_revision_conflict` | Client/adapter revision pin conflicts with the active immutable contract | Negotiate a supported revision; never coerce |
| `408` | `topic_deadline_exceeded` | Naruon's bounded request budget expires before an upstream timeout can be classified | Retry only within bounded client policy |
| `422` | `topic_input_invalid` | Bounded shape or source snapshot cannot satisfy the inference request | Correct the request/source |
| `422` | `topic_language_unsupported` | Active fitted artifact does not support the declared language/profile | Select a compatible model only through deployment policy |
| `422` | `topic_input_insufficient_tokens` | Frozen preprocessing retains fewer tokens than the active threshold | More evidence is required |
| `422` | `topic_input_out_of_vocabulary` | OOV count/ratio violates the active artifact policy | Use compatible source evidence/model; no fallback |
| `422` | `topic_temporal_context_invalid` | Event, availability, assertion, or knowledge-cutoff evidence violates the temporal policy | Correct authoritative time evidence |
| `422` | `topic_covariate_contract_invalid` | Required covariate, level, membership weight, or design row is missing/incompatible | Correct authoritative covariate evidence |
| `429` | `topic_rate_limited` | Tenant/workspace quota, concurrency, or repeated-query policy denies work | Honor `Retry-After`; do not change measurement method |
| `503` | `topic_deployment_unavailable` | No verified active deployment exists | Retry only after operator activation |
| `503` | `topic_model_artifact_unavailable` | Pinned artifact or required retained manifest cannot be resolved | Operator/upstream remediation |
| `503` | `topic_model_artifact_integrity_failed` | Artifact/provenance digest validation fails | Quarantine deployment; do not retry blindly |
| `502` | `topic_upstream_inference_failed` | Compatible request reached the upstream boundary but transport/runtime failed | Retry according to bounded service policy |
| `502` | `topic_upstream_protocol_error` | Upstream response fails schema, digest, asserted date-time format, known code-registry, or cross-field validation | Quarantine/review; never turn into abstention |
| `504` | `topic_upstream_timeout` | The bounded expected-upstream deadline expires and work is cancelled | Retry only within bounded service policy |
| `500` | `topic_adapter_internal_error` | Unexpected Naruon defect after safe classification | Incident handling; no internal detail in response |

A client disconnect or explicit cancellation may make an HTTP response
impossible. The adapter must cancel bounded work, emit no result, and record only
the internal stable outcome `topic_request_cancelled` in approved redacted
telemetry. It must not serialize a partial posterior or retry after cancellation.

Authentication/authorization/purpose/consent/region denial, rate limiting,
unsupported language, token/OOV insufficiency, temporal/covariate incompatibility,
missing deployment/artifact, integrity failure, trusted conflicts, timeout,
cancellation, and upstream protocol failures must never return HTTP `200` or
`status=abstained`.
These error conditions must never return HTTP `200` or `status=abstained`.

## RFC 9457 problem details

Every non-`200` response uses `application/problem+json` and a stable RFC 9457
problem type. `error_code` is a required Naruon extension; clients branch on the
code, not on localized `title` or `detail` text.

```json
{
  "type": "https://naruon.net/problems/topic-language-unsupported",
  "title": "Topic inference language is unsupported",
  "status": 422,
  "detail": "The active fitted model cannot infer this language profile.",
  "instance": "/api/topic-intelligence/inferences/tir_3FQn1v8H2zK6cP4m",
  "error_code": "topic_language_unsupported",
  "request_id": "tir_3FQn1v8H2zK6cP4m",
  "retryable": false
}
```

Problem responses must not include raw source content, topic candidates,
canonical digests, tenant/workspace IDs, covariates, membership identities,
upstream URLs, stack traces, provider errors, or arbitrary evidence references.

## Scientific payload requirements

The nested `tepp_payload` contains no presentation label. It must provide:

- fitted model ID/version/topic count;
- artifact, manifest, vocabulary, preprocessing, design, lineage, model-card,
  validation-report, evidence-time manifest, covariate snapshot, and design-row
  canonical digests;
- estimator, analysis unit, estimand, prevalence/content formulas, contrasts,
  versioned covariate schema, typed covariate level/missingness policy,
  membership structure/normalization, unseen-level policy, validation profile,
  temporal policy version, explicit document/event/assertion/availability/
  knowledge-cutoff time values, the pinned temporal missingness rule, an asserted
  availability-at-cutoff result, and `causal_design=non_causal`;
- inference method, implementation/version, numerical backend, credible level,
  interval method, and
  `uncertainty_scope=conditional_on_fitted_artifact`;
- non-negative integer topic IDs, ranks, proportions, and per-topic intervals for
  accepted results;
- input diagnostics for language, original/retained/OOV tokens and their pinned
  thresholds, temporal context, and covariates;
- posterior diagnostics with an immutable diagnostic-code registry version,
  convergence and its stable known code, numerical status, bounded stable known
  quality codes, iteration count, finite values, interval
  validity, observed component count, posterior sum, and normalization tolerance;
  and
- an acceptance-policy version, immutable reason-code registry version, boolean
  decision, and stable known reason codes.

The adapter recomputes and cross-checks unique topic IDs/ranks; for `inferred`,
equality of fitted, declared, observed, and actual component counts; sum,
interval containment, finite values, method copies, status, and diagnostic
consistency. It also checks request/evidence snapshot and scope-binding equality,
current tenant/workspace/purpose/consent/region authorization, input thresholds,
membership-structure/normalization coupling, typed covariate level/missingness,
RFC 3339 format assertion, and `availability_time <= knowledge_cutoff_time`.
Unknown code registry versions or codes and any failed cross-check are `502`
protocol errors. Schema validation alone is insufficient.

## Digest contract

The complete internal inventory is the schema, source snapshot, scientific
payload, artifact descriptor, artifact manifest, vocabulary, preprocessing,
design, lineage, model card, validation report, evidence-time manifest,
covariate snapshot, and design row. Each of those exactly 14 canonical digest
fields, including `schema_digest`, is a `canonicalDigest` record whose `value`
is:

`SHA-256(UTF8(domain) || 0x00 || UTF8(RFC8785(value)))`

with lowercase hexadecimal output. `schema_digest` has one construction:
`domain` is exactly `naruon.topic-inference.schema.v1`, and the formula's
`value` input is the complete parsed JSON value of the immutable schema resource
identified by the pinned `$id`, including its annotations and definitions.
Whitespace, JSON member order, source-file encoding, and other raw-file
serialization details are therefore not separate schema-digest inputs. The
adapter's out-of-band pin stores the resulting canonical-digest record, and the
response repeats that record.

All 14 contract fields bind canonical JSON values. In particular,
`artifact_digest` binds the fitted-artifact **descriptor**, not the raw fitted
artifact bytes. An independently published artifact manifest may additionally
contain a distinct optional raw-byte hash record, but that record must declare
its algorithm and the exact byte serialization or package it covers. It is
manifest content protected through `manifest_digest`; it is neither
`artifact_digest`, a substitute for any canonical field, nor a fifteenth field
in the inventory. Without that distinct record, the contract makes no raw
artifact-byte integrity claim. RFC 8785 does not normalize Unicode, so
normalization belongs only to the pinned preprocessing contract.

The no-covariate canonical representations are fixed:

- `{"covariates":[],"memberships":[]}` under
  `naruon.topic-inference.covariate-snapshot.v1`;
- `{"columns":[],"values":[]}` under
  `tepp.topic-measurement.design-row.v1`.

A canonical digest verifies equality with the exact retained canonical JSON
value; it does not prove that a descriptor is truthful or complete and cannot
reconstruct or retrieve the described material. Reproduction requires the
authorized source snapshot and every pinned model, vocabulary, preprocessing,
design, lineage, temporal, covariate, and design-row object to remain resolvable
under retention policy. Raw artifact-byte equality additionally requires the
separate manifest-owned byte hash described above.

All content-, evidence-, covariate-, membership-, temporal-, design-, and
label-derived digests are sensitive pseudonymous linkage data. They are never
public and never appear in ordinary logs, metrics, traces, or audit events. A
restricted audit record may be referenced only by a tenant-keyed opaque handle.

## Evidence reference rules

An `evidence_ref`:

- is opaque and contains no source/provider identifier, URL, or path;
- is bound to one audience, tenant, workspace, document snapshot, and purpose;
- has an expiry and is rejected when expired;
- is reauthorized on every use instead of treated as a bearer shortcut;
- cannot be exchanged across organizations or workspaces; and
- resolves only through a server-side registry that returns the retained
  immutable snapshot or fails closed.

The internal `evidence_ref.snapshot_revision` must equal
`request.source_snapshot_revision`, and its `scope_binding_ref` must equal the
request binding. Resolution must reproduce the current authenticated tenant,
workspace, purpose, consent, region, and authorization binding; equality of the
opaque strings alone is insufficient.

## Compatibility and change control

Revision `2026-08-09.1` is immutable. Backward-compatible clarifications require
a new revision and schema digest; semantic changes to topic identity,
uncertainty, abstention, provenance, error mapping, or ownership require a new
contract version and a superseding Naruon ADR. Naruon must not silently coerce a
expected-upstream payload from an unrecognized revision.

No route can move from `BLOCKED-UPSTREAM` to implemented until the requirements
and evidence in [Traceability](TRACEABILITY.md) and the operability/security
gates are satisfied on the exact candidate revision.
