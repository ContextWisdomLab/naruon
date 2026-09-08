# ADR-0001: Naruon-local policy for consuming structural topic measurement

**Status:** Accepted (Naruon-local consumption policy)
**Date:** 2026-08-09
**Decision owner:** Naruon maintainers
**Scope:** Naruon's product behavior and any future Naruon adapter. This ADR does not transfer product or scientific authority to TEPP, govern TEPP, or record TEPP's acceptance of a Naruon contract.

**Related records:** the complete documentation graph is indexed in
[`docs/topic-intelligence/README.md`](../topic-intelligence/README.md). Proposed
implementation decisions are split into [ADR-0002](0002-fitted-topic-artifact-consumption.md)
and [ADR-0003](0003-separate-topic-measurement-from-agenda-generation.md).

## Upstream direction evidence

[TEPP's protected-`main` architecture at commit `b8e26aae334397daa1974d4a24c9015cfd682600`](https://github.com/ContextualWisdomLab/TEPP/blob/b8e26aae334397daa1974d4a24c9015cfd682600/ARCHITECTURE.md#bounded-services-and-rust-crates) lists `topic_measurement` and states that its boundaries expose versioned integration contracts. This is direction evidence for Naruon's future-consumption policy only. It is not TEPP's acceptance of this ADR, not a transfer of authority, and not evidence of a production API or contract.

## Context

Naruon historically exposed `email_categorizer` and `meeting_agenda_generator` from small hard-coded Korean/English term tables. Those outputs were deterministic, but they were lexical rules presented through product names that implied semantic topic inference. That is not a Structural Topic Model and provides no fitted corpus-level topic identity, mixed-membership posterior, uncertainty, prevalence/content covariate effect, multilingual measurement evidence, or model-artifact provenance.

The upstream architecture is compatible with a future fitted-model integration, but Naruon has no independently published TEPP production artifact/API/contract to consume today. This ADR therefore makes a local product-truth decision: Naruon will not present lexical, embedding, zero-shot, or LLM output as Structural Topic Modeling (STM), and it will fail closed until a separately accepted upstream contract is available.

## Decision

1. Naruon's retained `keyword_extractor` remains explicitly lexical metadata only. It must never be described as a topic model or semantic classifier.
2. Naruon will not replace removed pseudo-topic tools with a larger keyword table, embedding cluster, zero-shot labeler, or LLM prompt while naming the result Structural Topic Modeling.
3. A Naruon adapter remains blocked until TEPP independently publishes a versioned production fitted-model artifact, API, or contract and its own acceptance evidence. If Naruon later chooses to consume that published contract, it must use a stable typed integration boundary and must not refit an STM per request.
4. Naruon's acceptance criteria for any future consumed inference contract include: model artifact/version and digest; immutable source/document identity; frozen preprocessing and vocabulary; OOV/retained-token diagnostics; language profile/support status; relevant prevalence/content and multilevel/cross-classified/multiple-membership covariates; event/document/availability/knowledge-cutoff time semantics when the model uses them; mixed-membership topic proportions; posterior uncertainty/diagnostics; and explicit abstention/failure status.
5. Human-readable topic labels and generated agenda/action summaries are presentation/generation artifacts. They are never the numeric topic identity and cannot change the fitted posterior.
6. If a required published model/API/artifact is unavailable, incompatible, under-supported for the document language, or cannot produce an evidence-valid posterior, Naruon fails closed. It does not fabricate `General`, empty agenda semantics, or an embedding/LLM substitute under the same contract.
7. Naruon remains useful without topic inference. Any future integration is optional and versioned; Naruon must not read an upstream service's private database directly. This ADR imposes no obligations on TEPP.

## Alternatives rejected

### Keep deterministic keyword categories

Rejected because deterministic lexical matching is not mixed-membership topic measurement and would preserve the original product-truth defect.

### Use embeddings or clustering as a drop-in STM replacement

Rejected as a semantic product substitution. Such methods may be useful in separate features, but equal semantic usefulness does not make them an STM posterior or preserve the same prevalence/content/uncertainty contract.

### Ask an LLM for topic labels at request time

Rejected as the statistical authority. LLMs may interpret or label fitted evidence behind a separate bounded contract, but request-time labels do not replace a fitted corpus-level model and its uncertainty.

### Fit a fresh topic model for every Naruon request

Rejected because new-document inference must be comparable against a stable fitted model. Per-request refits destroy topic identity, reproducibility, governance, and longitudinal comparability.

## Consequences

- PR #1297 removes the misleading pseudo-topic tools rather than shipping an unvalidated replacement.
- A Naruon adapter cannot be proposed until TEPP independently publishes a versioned production artifact/API/contract and its own acceptance evidence.
- Naruon tests must keep lexical utilities labelled lexical and must fail if removed pseudo-topic registry entries reappear without a locally accepted replacement contract.
- Any future adapter must carry model/provenance/uncertainty/diagnostic fields rather than only a label string.
- Product documentation must distinguish `implemented on protected develop`,
  `active PR`, `accepted Naruon-local policy`, `proposed target`, and
  `blocked-upstream`; this ADR neither claims that TEPP topic inference exists
  today nor that TEPP accepted Naruon's consumption policy.

## Naruon adapter acceptance criteria

A future Naruon topic-measurement adapter remains blocked unless TEPP independently publishes a versioned production artifact/API/contract and its own acceptance evidence. Once that upstream precondition exists, Naruon may evaluate an adapter against these local criteria before promoting it to protected `develop`:

- a published TEPP production artifact/inference API at a versioned contract, plus TEPP's own acceptance evidence;
- fitted-model and preprocessing/vocabulary identity validation;
- positive, negative, OOV/insufficient-text, unsupported-language and model-unavailable tests;
- posterior normalization and uncertainty/diagnostic tests;
- multilevel/multiple-membership and temporal-covariate contract tests when those inputs are part of the fitted model;
- tenant/source authorization at the Naruon boundary;
- exact-head CI/security/coverage and independent review;
- no claim that topic labels or LLM interpretations are the numeric topic identity.

## Supersession rule

Changing this Naruon-local consumption policy, changing new-document topic identity semantics, or authorizing Naruon to fit its own production topic models requires a superseding Naruon ADR plus synchronized product/technical/architecture/test/operability documentation and scientific validation evidence.
