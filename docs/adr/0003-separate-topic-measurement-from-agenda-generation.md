# ADR-0003: Separate topic measurement from agenda generation

**Status:** Proposed

**Date:** 2026-08-09

**Decision owner:** Naruon maintainers

**Capability maturity:** target and future agenda capability `PLANNED`; no
implementation is authorized

**Scope:** a possible future Naruon agenda-generation decision only. This ADR
does not govern a model or generation provider, assign external ownership, or
record provider acceptance.

**Trigger for acceptance:** a separately reviewed agenda-generation product
contract and implementation PR.

**Related requirement:**
[TI-REQ-009](../topic-intelligence/PRD.md#product-requirements)

## Context

The removed `meeting_agenda_generator` mapped words directly to a fixed agenda
template. That coupled a lexical trigger, an implied topic assertion, and a
generated action artifact. Even a valid fitted topic posterior would be
descriptive evidence, not authorization to create or execute an agenda.

## Proposed decision

ADR-0001 already supplies the accepted Naruon-local separation policy. This ADR
is the proposed implementation decision for a future bounded agenda capability;
it remains a proposed target rather than accepted architecture. If Naruon
reintroduces agenda generation, the Naruon capability must:

1. consume tenant-authorized source evidence and, optionally, a versioned topic
   posterior by reference;
2. preserve every cited source and model provenance field without converting a
   display label into numeric topic identity;
3. declare the generation provider/model and return `review_required=true`;
4. treat source text, labels, and posterior metadata as untrusted data rather
   than instructions; and
5. create no calendar/task/provider write unless a separate explicit intent,
   capability, consent, and conflict check succeeds.

The generator may abstain or fail, but it must not fall back to a template and
describe that output as source-backed topic inference.

## Consequences

- A statistical posterior can inform a draft but never authorizes a write.
- Human-readable labels are presentation metadata and can be revised without
  changing the fitted topic identity.
- Agenda quality, grounding, prompt-injection resistance, and provider-write
  safety require tests independent of topic-model validation.

## Alternatives rejected

- **One endpoint for measurement and generation:** obscures error ownership and
  makes a generative failure look like scientific inference.
- **Template fallback:** recreates the misleading behavior removed by PR #1297.
- **Direct provider write:** bypasses Naruon's source, consent, capability, and
  conflict boundaries.
