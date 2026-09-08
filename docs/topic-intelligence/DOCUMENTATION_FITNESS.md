# Documentation fitness assessment

- **Assessment date:** 2026-08-09
- **Protected-base snapshot:** `develop@5425ce4f55b2cf16b2c82a4fd661c9d0bd0660c7`
- **Candidate:** PR #1297
- **Verdict before this package:** insufficient
- **Verdict after this package:** design-sufficient for deletion review and
  future contract discovery; partial for runtime implementation; insufficient
  to claim a live STM capability

Fitness terms are `PRESENT-CURRENT`, `PRESENT-STALE`, `PARTIAL`, `MISSING`,
`NOT-APPLICABLE`, and `SUPERSEDED`. These terms assess documentation fitness,
not implementation maturity.

The maturity split is explicit: ADR-0001 is an
`ACCEPTED-NARUON-POLICY`; ADR-0002 and ADR-0003 are `Proposed` Naruon target
decisions; the target acceptance profile is `PLANNED`; and the runtime capability
remains `BLOCKED-UPSTREAM`. A proposed target or complete document package is
not an accepted runtime architecture and cannot promote the capability.

## Assessment matrix

| Artifact | Before | After | Evidence and remaining limit |
| --- | --- | --- | --- |
| Topic-specific PRD | `PRESENT-STALE` | `PRESENT-CURRENT` | Requirement IDs, users, non-goals, failure/abstention journeys, and explicit maturity are consolidated. |
| Topic-specific TRD | `PARTIAL` | `PRESENT-CURRENT` | Naruon ownership, upstream non-authority, artifact, input/result, error/abstention, provenance, security, compatibility, and gates are explicit. |
| Naruon ADR | `PARTIAL` | `PRESENT-CURRENT` | ADR-0001 records only Naruon's accepted local policy; the ADR index and package separately expose ADR-0002 and ADR-0003 as proposed targets, not upstream acceptance or runtime implementation. |
| Future adapter decisions | `MISSING` | `PARTIAL` | Proposed ADR-0002 covers conditional fitted-artifact consumption and proposed ADR-0003 covers agenda separation. Transport/authentication, artifact signing/registry, cache, retention/deletion, rate limit, sensitive-covariate, and downstream-authorization ADRs still await a real upstream boundary. |
| Architecture | `PARTIAL` | `PRESENT-CURRENT` | Current/candidate/target ownership, trust, and failure boundaries are separated; the target views are a proposed acceptance profile governed only by the accepted local policy. |
| UML | `PARTIAL` | `PRESENT-CURRENT` | Conceptual component, class, success/error/abstention, artifact-state, and deployment views are available without claiming runtime code. |
| ERD/data model | `PRESENT-STALE` | `PRESENT-CURRENT` | Contract concepts are modeled; physical Naruon persistence remains correctly `NOT-APPLICABLE`. |
| API/schema/versioning | `PARTIAL` | `PRESENT-CURRENT` | Planned Naruon adapter validation shape, closed revision rules, errors, abstention, and cross-field invariants are documented; no live transport is claimed. |
| Canonical digest inventory | `MISSING` | `PRESENT-CURRENT` | One 14-field inventory names the three envelope and eleven scientific-provenance digests, including model card, validation report, covariate snapshot, and design row; schema/API remain the machine-readable and formula authorities. |
| Security and threat model | `PARTIAL` | `PRESENT-CURRENT` | Assets, misuse cases, privacy/statistical risks, controls, residual decisions, and refresh triggers are explicit. |
| Test strategy | `PARTIAL` | `PRESENT-CURRENT` | Naruon product/integration evidence is separated from upstream scientific validation. |
| Operability | `PARTIAL` | `PRESENT-CURRENT` | Readiness, safe signals, promotion, incidents, rollback, recovery, and replay gates are documented without invented SLOs. |
| Traceability | `PARTIAL` | `PRESENT-CURRENT` | Requirements map to the Naruon decision, design/contract, code/tests, and maturity. |
| References | `PARTIAL` | `PRESENT-CURRENT` | Scientific, standards, and dated repository evidence are separated from implementation claims. |
| Machine documentation fitness | `MISSING` | `PARTIAL` | File/link/schema-maturity/source-absence checks are useful, but balanced fences are not Mermaid parsing and JSON parsing is not Draft 2020-12 metaschema or fixture validation. |

## Why the verdict is not “implementation-ready”

The package defines what Naruon would require; it does not supply the upstream
dependency or implementation evidence. In particular:

- Naruon has no independently published upstream production topic artifact,
  inference API/contract, or publisher acceptance evidence to consume.
- The planned Naruon envelope is not an upstream publisher's canonical payload
  and cannot assign obligations or ownership to TEPP or another producer.
- Transport, service authentication, artifact signing/registry, cache,
  retention/deletion, rate limit, sensitive-covariate, and downstream-
  authorization decisions are unresolved.
- No physical Naruon topic persistence, migration, retention contract, or
  resolvable replay snapshot has been approved. Digests support verification,
  not reconstruction.
- No fitted production artifact, model card, validation thresholds, interval
  calibration/coverage evidence, drift baseline, signed promotion record,
  representative capacity study, or numeric SLO exists.
- The 14 digest fields specify verification bindings only. No retained object,
  upstream adoption, scientific validity, or replay capability follows from the
  inventory itself.
- No live OpenAPI route, adapter, real-service E2E evidence, or topic UI exists.

These are intentional gates while runtime integration is `BLOCKED-UPSTREAM`,
not permission to describe the capability as implemented.

## Completeness decision

The deletion change is adequately specified when reviewers can verify all of the
following:

1. The two lexical pseudo-topic tools disappear from registry and source on the
   candidate branch.
2. The retained keyword utility remains bounded and explicitly lexical.
3. No substitute topic handler, default label, template agenda, or network/model
   dependency is introduced.
4. Protected-base, active-PR, accepted-local-policy, planned, and upstream-
   blocked claims remain distinct.
5. Error and scientific-abstention semantics do not overlap.
6. Any future integration is blocked on an independently published compatible
   fitted artifact/API/contract and scientific acceptance evidence.

The documentation is therefore sufficient for PR #1297's deletion decision and
for initiating later contract discovery. It is insufficient to authorize a
runtime adapter, persistence, downstream topic use, or product UI.

## Reassessment triggers

Re-run this assessment when any of the following occurs:

- an upstream publisher independently publishes or changes a production topic-
  measurement artifact/API/contract or its acceptance evidence;
- Naruon selects a transport, schema revision, fitted artifact, cache, audit, or
  persistence design;
- topic output is consumed by search, norm-group inference, labels, agenda
  generation, or another downstream decision;
- a UI, sensitive covariate, temporal/multilevel estimator, or causal claim is
  proposed; or
- an incident, drift result, validation result, or retention requirement changes
  the accepted Naruon boundary.

When maturity changes, update the PRD requirement row, TRD, ADR status/scope,
architecture and contract, tests/evidence, traceability, changelog, and this
fitness matrix in the same PR. A document-only status promotion without
protected-branch runtime evidence is invalid.
