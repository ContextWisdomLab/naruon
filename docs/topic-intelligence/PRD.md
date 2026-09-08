# Product requirements: topic intelligence

- **Status:** removal `ACTIVE-PR`; local policy `ACCEPTED-NARUON-POLICY`;
  runtime integration `BLOCKED-UPSTREAM`
- **Date:** 2026-08-09
- **Related change:** PR #1297
- **Accepted local decision:** [ADR-0001](../adr/0001-topic-measurement-authority.md)
- **Proposed target decisions:**
  [ADR-0002](../adr/0002-fitted-topic-artifact-consumption.md) and
  [ADR-0003](../adr/0003-separate-topic-measurement-from-agenda-generation.md)

## Problem

Naruon exposed `email_categorizer` and `meeting_agenda_generator` through product
names that suggested topic understanding, although both used small fixed Korean
and English term tables. Deterministic output made those rules reproducible; it
did not make them a fitted topic model. The behavior hid uncertainty, confused
business labels with latent topic identity, and failed across languages and
domains.

Users need an honest boundary between lexical utilities and corpus-derived topic
measurement. They also need Naruon to withhold a topic result when the required
fitted model, contract, input support, or evidence is absent.

## Users and needs

| User | Need |
| --- | --- |
| Knowledge worker | Know whether a result is lexical metadata, an evidence-valid posterior, an abstention, or an error. |
| Workspace administrator | Ensure tenant content is purpose-bound and never sent to an unapproved model or corpus. |
| Analyst or research owner | Verify a result against a versioned model, frozen preprocessing/vocabulary, design, times, and diagnostics. |
| Operator | Detect incompatibility, integrity failure, abstention, drift, and service failure without logging message bodies. |
| Developer or reviewer | Prevent lexical, embedding, clustering, or LLM shortcuts from being mislabeled as STM. |

## Goals

1. Remove executable product behavior that implies topic inference without a
   fitted corpus-level model.
2. Preserve useful keyword extraction only under an explicit lexical contract.
3. Establish a Naruon-local, fail-closed acceptance boundary for any future
   independently published fitted-model integration.
4. Keep numeric topic identity, human labels, downstream decisions, and agenda
   generation separate.
5. Make future results verifiable against authorized source evidence and an
   immutable compatible model artifact.

## Non-goals

- Fitting a topic model inside an API request or training models inside Naruon.
- Assigning responsibilities to TEPP or claiming that TEPP accepted this PRD,
  ADR, or a Naruon-authored contract.
- Calling keyword counts, embeddings, clustering, classifiers, zero-shot output,
  or LLM labels “STM.”
- Adding a Naruon topic route, table, migration, public response, or UI before a
  real upstream contract and release evidence exist.
- Reintroducing agenda generation as a topic-measurement side effect.
- Claiming causal effects or individual attributes from group-level topic
  prevalence.

## Product requirements

| ID | Requirement | Acceptance evidence | Maturity |
| --- | --- | --- | --- |
| `TI-REQ-001` | Remove `email_categorizer` and `meeting_agenda_generator` from the tool registry and implementation. | Registry regression tests and source absence. | `ACTIVE-PR` |
| `TI-REQ-002` | Describe retained `keyword_extractor` output as deterministic lexical frequency/first-occurrence metadata, never topic evidence. | Registry description and handler tests. | `ACTIVE-PR` |
| `TI-REQ-003` | Fail closed until an independently published, compatible fitted-model artifact/API/contract exists; never substitute a default category, synthetic posterior, keyword/embedding/LLM result, or agenda template. | Accepted ADR-0001, proposed ADR-0002, and future negative-path adapter tests. | `ACCEPTED-NARUON-POLICY`; target `PLANNED`; runtime `BLOCKED-UPSTREAM` |
| `TI-REQ-004` | A future valid result returns a mixed-membership topic vector with diagnostics and intervals whose level, method, and uncertainty scope are explicit; compatible-model abstention is a distinct vector-free state. | Independently published calibration/coverage evidence plus Naruon schema and invariant tests. | `BLOCKED-UPSTREAM` |
| `TI-REQ-005` | Any temporal, multilevel, multiple-membership, or cross-classified STM extension names its estimator, analysis unit, estimand, prevalence/content formula and contrasts, membership weights/normalization/unseen-level policy, non-causal status, and validation evidence. | Model card, design manifest, known-truth simulation, and downstream suppression tests. | `BLOCKED-UPSTREAM` |
| `TI-REQ-006` | Bind every result to all 14 fields in the [canonical digest inventory](README.md#canonical-digest-inventory), including `model_card_digest`, `validation_report_digest`, `covariate_snapshot_digest`, and `design_row_digest`. Treat digests as verification, not reconstruction; later reproducibility also requires a resolvable retained snapshot. | Fourteen-field schema/inventory parity, digest/provenance, temporal-leakage, retention, and replay tests. | `BLOCKED-UPSTREAM` |
| `TI-REQ-007` | Keep numeric topic identity separate from evidence-backed, language-aware, versioned human-readable labels. | Schema, presentation, and UI contract tests. | `BLOCKED-UPSTREAM` |
| `TI-REQ-008` | Enforce tenant, workspace, source, purpose, consent, region, retention, deletion, digest-handling, and log/metric/trace-redaction controls before inference. | Authorization, isolation, deletion, restricted-audit, and redaction tests. | `BLOCKED-UPSTREAM` |
| `TI-REQ-009` | Treat agenda generation as a separately authorized downstream decision/generation capability with its own evidence and audit contract. | Accepted separation policy in ADR-0001; proposed ADR-0003 plus separate product/technical contract, endpoint, permissions, and tests before release. | `ACCEPTED-NARUON-POLICY`; target decision and future capability `PLANNED` |
| `TI-REQ-010` | Expose a product UI only after the runtime contract, compatible artifact, uncertainty language, abstention/error states, security controls, and operational gates are real. | Release-readiness review and source-backed E2E tests. | `PLANNED` |

## User journeys

### Current candidate

1. A user or agent lists available analysis tools.
2. The two pseudo-topic tools are absent.
3. Keyword extraction, when selected, is described as lexical frequency rather
   than inferred topics.

### Future valid inference

1. An authorized user requests topic intelligence for a bounded document
   snapshot and declared purpose.
2. Naruon validates scope, minimization, language metadata, time semantics, and
   an operator-approved upstream model policy.
3. An independently published upstream interface supplies publisher-accepted
   evidence for a compatible active fitted artifact and returns either a mixed-
   membership result or a narrowly defined scientific abstention.
4. Naruon validates the pinned contract and numerical invariants before
   presenting permitted posterior, provenance, uncertainty, and label evidence.

### Future input or operational error

Unsupported language, insufficient retained tokens, excessive OOV input,
invalid temporal/covariate data, missing/incompatible model, integrity failure,
authorization denial, or timeout returns a stable error. No posterior, label, or
fallback is produced.

### Future scientific abstention

Only after a compatible active model accepts the input contract may its declared
posterior or diagnostic acceptance rule return `abstained`. The result contains
a stable reason and no topic vector or label.

## Success and release gates

- Zero registered pseudo-topic tools and zero production references to their
  handlers or fixed dictionaries on the candidate head.
- Lexical extraction remains bounded, deterministic, and honestly named.
- Every future result can be verified against exact source/artifact identities
  and digests; any replay or reproducibility claim also proves the authorized
  immutable snapshot remains resolvable under an approved retention contract.
- Topic proportions, interval coverage/calibration, diagnostics, and any
  extended-STM structures have independently published scientific-validation
  evidence before a Naruon adapter is enabled. This is a Naruon acceptance gate,
  not an assignment of duties to the publisher.
- Tenant isolation, purpose, redaction, incompatibility, integrity, timeout,
  rollback, and no-fallback tests pass with warnings treated as failures.
- Product copy distinguishes lexical terms, numeric topics, human labels,
  uncertainty, scientific abstention, and operational/input errors.

No numeric latency, availability, or scientific-quality target is invented in
this PR. Such targets require an independently published production contract,
representative corpus/workload, capacity study, model card, and approved release
evidence.
