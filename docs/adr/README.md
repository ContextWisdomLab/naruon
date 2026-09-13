# Naruon Architecture Decision Records

This index records cross-cutting Naruon decisions that must survive beyond an
individual pull request, implementation plan, or chat. `Accepted` means only that
the Naruon decision governs its stated local scope; it does not transfer authority
to an external service or mean a future integration is implemented on protected
`develop`. `Proposed` records a discoverable target for later review and does not
govern implementation.

| ADR | Decision | Status | Capability effect |
|---|---|---|---|
| [ADR-0001](0001-topic-measurement-authority.md) | Naruon-local policy for consuming structural topic measurement, never a keyword/label heuristic | Accepted | `ACCEPTED-NARUON-POLICY`; no runtime promotion |
| [ADR-0002](0002-fitted-topic-artifact-consumption.md) | Conditionally consume only a versioned fitted topic artifact through a fail-closed adapter | Proposed | Target `PLANNED`; runtime `BLOCKED-UPSTREAM` |
| [ADR-0003](0003-separate-topic-measurement-from-agenda-generation.md) | Keep statistical measurement separate from agenda generation | Proposed | Target and future capability `PLANNED`; no implementation authorization |
| [ADR-0004](0004-status-weighted-calendar-conflicts.md) | Evaluate CalDAV VEVENT overlaps by occupying status; cancelled does not occupy | Accepted | `ACCEPTED-NARUON-POLICY`; advisory evaluate API only |
| [ADR-0005](0005-attachment-content-type-quarantine.md) | Quarantine attachments whose sniffed bytes disagree with their declared content type; address them via a new `attachment_uid` | Proposed | PR #1486 candidate; no protected-branch or release adoption evidence |

The complete topic-intelligence requirements, architecture, contract, UML,
conceptual ERD, security, test, and operability graph is indexed at
[`docs/topic-intelligence/README.md`](../topic-intelligence/README.md).
Its [canonical digest inventory](../topic-intelligence/README.md#canonical-digest-inventory)
is the single cross-document list for the planned adapter profile.

## Change rule

Create or update an ADR when a Naruon change adopts or declines an external service contract, introduces a new scientific/statistical inference contract, changes persistence or tenant authority, changes model/credential trust boundaries, or replaces a fail-closed product capability with a different production dependency. A Naruon ADR records Naruon's decision only; it cannot assign authority to, or accept a decision for, another service.

Every implementing PR must keep the corresponding source, tests, doctoring,
architecture/operability contract, and CHANGELOG maturity truthful. An active PR,
accepted local policy, or proposed target must not be described as protected-
branch implementation before it is integrated and independently verified.
