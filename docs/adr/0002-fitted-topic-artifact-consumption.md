# ADR-0002: Consume only a versioned fitted topic artifact

**Status:** Proposed

**Date:** 2026-08-09

**Decision owner:** Naruon maintainers

**Capability maturity:** target `PLANNED`; runtime `BLOCKED-UPSTREAM`

**Scope:** a possible future Naruon consumption decision only. This ADR does not
assign an external scientific owner, impose obligations on TEPP or another
publisher, or record upstream acceptance.

**Trigger for acceptance:** an upstream publisher independently releases a
versioned production inference contract and its own acceptance evidence, and
Naruon approves that exact contract in an implementing PR.

**Related requirements:** [TI-REQ-003, TI-REQ-004, and
TI-REQ-006](../topic-intelligence/PRD.md#product-requirements)

## Context

New-document structural topic inference is meaningful only relative to a stable
fitted corpus-level model. A request-time refit, an embedding cluster, a keyword
table, or an LLM label cannot preserve topic identity, covariate design,
uncertainty, or longitudinal comparability. Naruon currently has no production
topic endpoint and no fitted topic artifact to consume.

## Proposed decision

Naruon will add no topic adapter until an independently published contract can
bind all of the following in one result:

- every exact field in the [canonical 14-field digest
  inventory](../topic-intelligence/README.md#canonical-digest-inventory), including
  the model-card, validation-report, evidence-time-manifest,
  covariate-snapshot, and design-row digests;
- immutable source/snapshot, model, artifact, contract, preprocessing,
  vocabulary, design, lineage, model-card, and validation-report identity;
- explicit language support, retained-token count, OOV rate, covariate design,
  temporal semantics, multilevel and multiple-membership inputs when fitted;
- a mixed-membership topic vector, conditional posterior uncertainty,
  convergence/numerical diagnostics, and stable quality codes; and
- an explicit `inferred` or scientifically `abstained` outcome, never a
  fabricated default topic.

This proposed decision assigns only Naruon responsibilities: tenant
authorization, input bounds, disclosure policy, request and response envelopes,
transport resilience, compatibility validation, activation, and error mapping.
Naruon would consume only scientific evidence accompanied by the publisher's
independently issued acceptance evidence; this ADR neither determines who holds
external scientific authority nor delegates Naruon's compatibility decision.
Naruon must not read an upstream private database or refit the model per request.

Preflight incompatibility is an error: invalid language, insufficient retained
tokens, excessive OOV, missing fitted covariates, or an incompatible design row
returns a stable `422` problem. No active compatible deployment is `503`.
Request/version conflicts are `409`. Only a compatible active model's posterior,
diagnostic, or policy rejection may return HTTP `200` with `status=abstained`.

## Consequences

- The proposed schema and HTTP contract are design artifacts, not live API
  claims.
- The 14-field digest inventory is a Naruon acceptance profile, not evidence of
  upstream adoption, scientific validity, retained objects, or replayability.
- Any implementation requires a superseding or acceptance edit to this ADR,
  an upstream compatibility fixture, tenant-boundary tests, scientific
  calibration evidence, and exact-head CI/security review.
- Absence, incompatibility, malformed results, or upstream failure remains a
  visible fail-closed condition.

## Alternatives rejected

- **Per-request fitting:** destroys stable topic identity and is operationally
  unbounded.
- **Keyword/embedding/LLM substitution:** may support separately named product
  features but is not the same estimand.
- **Best-effort fallback:** converts missing scientific evidence into false
  certainty.
