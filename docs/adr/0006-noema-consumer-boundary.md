# ADR-0006: Consume Noema and model orchestration through owner contracts

**Status:** Proposed

**Date:** 2026-09-04

**Decision owner:** Naruon maintainers

**Scope:** Naruon's workspace-agent integration boundary

## Context

Naruon owns workspace-agent tools, tenant and workspace authorization, and the
mail, calendar, task, and knowledge-graph domain rules those tools invoke. The
same product name also appears in `ContextualWisdomLab/noema`, whose protected
`main` currently defines Noema as an evidence-producing credential and
maintenance control plane for governed GitHub automation.

The repositories compose, but neither may infer a shared runtime from a shared
name. Noema's protected contract says provider discovery and routing belong to
`ContextualWisdomLab/contextual-orchestrator`; model-backed Noema jobs consume
its published gateway contract and reject direct-provider fallback. A proposed
`noema-core` package exists only on draft Noema PR #536. It is not a released
dependency and does not prove a Naruon adoption contract.

Naruon PRs #1384 and #1486 remain draft, independently active consumer lanes.
They must not copy an owner's source, consume an owner's branch, or transfer
review and check evidence between heads.

Contextual Orchestrator PR #1004 is the active owner repair for structured
output recovery across distinct eligible candidates. It remains an open
candidate, so Naruon may use its contract as dependency planning evidence but
must not treat its branch implementation as released runtime behavior.

At exact organization governance revision
`ContextualWisdomLab/.github@769691526f8c73cf714de8fe8ba51ae6cfa2901a`,
`docs/CWL-MASTER-CONTEXT.md` assigns the Naruon workspace agent and quarantine
sandbox to Noema. This conflicts with Noema's current protected description and
the separate quarantine owner repository, so owner-level reconciliation is a
prerequisite rather than a consumer assumption.

## Decision

1. Naruon retains ownership of workspace-agent prompts, tools, domain policy,
   tenant/workspace authorization, audit behavior, and user-facing outcomes.
2. Provider-neutral model discovery and routing are consumed only through a
   released `contextual-orchestrator` API and tenant/workspace-authorized
   credential boundary. Naruon does not silently fall back to a direct provider.
3. Noema credential, GitHub review, and maintenance capabilities are consumed
   only through Noema's released contracts. Naruon does not import Noema owner
   source or read its database.
4. The proposed `noema-core` package is not adopted until its owner PR merges,
   an immutable release is published, and Naruon verifies a versioned contract.
   Shared construction code alone does not move Naruon domain logic into Noema.
5. Quarantine execution remains owned by
   `ContextualWisdomLab/quarantine-sandbox-runtime`; this ADR does not assign
   it to Naruon or fold it into workspace-agent code. Naruon may adopt only an
   immutable released contract, and none exists yet.
6. Naruon adopts none of these owner capabilities until the pinned organization
   master context, protected owner descriptions, and released contracts agree.

## Consequences

- PR #1384 is the Naruon routing lane and must fail closed when the released
  orchestrator contract is unavailable.
- PR #1486 may add Naruon-owned calendar policy as a workspace-agent tool, but
  it cannot establish a second model-routing authority.
- Noema PR #536 is upstream proposed evidence only. A later Naruon adoption PR
  must pin a released version and add contract tests at the consumer boundary.
- Contextual Orchestrator PR #1004 must merge and publish an immutable contract
  before Naruon claims malformed structured-output recovery through that path.
- Earlier PR #1527 remains historical investigation evidence; this ADR replaces
  its contradictory separate-runtime/shared-runtime conclusions with the live
  owner/consumer boundary.

## Supersession record

This record carries forward PR #1527's valid observations that the existing
Naruon agent and GitHub review gate serve different domain workflows, that PRs
#1384 and #1486 overlap, and that draft owner code is not a released consumer
contract. It rejects #1527's later shared-runtime conclusion because that
conclusion treated an organization planning statement as deployed owner truth.

The replacement is independently traceable: it does not depend on the
predecessor's absent product-goal directive, does not claim that edited text is
a verbatim copy, and pins every cross-repository architecture claim below to a
repository, exact commit, artifact, and verification date. PR #1527 therefore
remains open as predecessor lineage until this successor is protected-merged
and its exact merge result is verified.

## Alternatives considered

### Treat all Noema-named code as one bounded context

Rejected. The protected owner contract describes a GitHub automation control
plane, while Naruon owns workspace-agent domain behavior. A common name is not
a versioned interoperability contract.

### Permanently separate every implementation detail

Rejected. This would also forbid legitimate consumption of released owner
contracts. Reuse is allowed at published API/package boundaries after release
and conformance evidence exist.

### Consume draft owner branches directly

Rejected. Draft heads are mutable, carry no immutable release identity, and
cannot transfer their checks or approvals to a consumer.

## Evidence and references

- `ContextualWisdomLab/noema`, protected `main` README at exact commit
  `e1ac9d50f6c646f04be8c137c8acdc7200182fcd`, verified 2026-09-04.
- `ContextualWisdomLab/noema` PR #536, draft proposal for `noema-core`, exact
  head `5531a5327d822028c4be59e290b4d101b34d49db`, verified 2026-09-04.
- `ContextualWisdomLab/naruon` PRs #1384, #1486, and #1527, verified 2026-09-04.
- `ContextualWisdomLab/contextual-orchestrator` PR #1004, exact head
  `6a992538b6efcc34b957f72fc599bb33ac40c152`, verified 2026-09-04.
- `ContextualWisdomLab/quarantine-sandbox-runtime`, default `develop` at exact
  commit `60a85c7633e03b425b67159ec6822c8178cf87ea`, with zero GitHub Releases,
  verified 2026-09-04. This identifies the owner but does not authorize
  consumer adoption.
- `ContextualWisdomLab/.github`, `docs/CWL-MASTER-CONTEXT.md` at exact commit
  `769691526f8c73cf714de8fe8ba51ae6cfa2901a`, verified 2026-09-04. It calls
  Noema the shared Naruon/GitHub runtime and quarantine sandbox; that unresolved
  statement must be reconciled by the organization/owner path before adoption.
- Evans, E. (2003). *Domain-driven design: Tackling complexity in the heart of
  software*. Addison-Wesley.
- Vernon, V. (2013). *Implementing domain-driven design*. Addison-Wesley.
- Parnas, D. L. (1972). On the criteria to be used in decomposing systems into
  modules. *Communications of the ACM, 15*(12), 1053–1058.
  https://doi.org/10.1145/361598.361623. Parnas shows that modules should hide
  changeable design decisions behind stable interfaces. That supports keeping
  Naruon domain policy behind its own boundary and consuming owner capabilities
  through released contracts. The publisher record does not grant general
  repository redistribution, so this PR links and summarizes the paper instead
  of committing a PDF.
