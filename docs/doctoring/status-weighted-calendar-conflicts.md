# Status-weighted calendar conflict policy

## Shipped boundary in this slice

Naruon evaluates a proposed calendar commitment against a bounded set of existing commitments and returns one of three deterministic outcomes: `available`, `blocked`, or `review_required`. The decision is advisory evidence only. It does not mutate, cancel, reschedule, accept, or decline any provider event.

The public endpoint is `POST /api/calendar/conflicts/evaluate`. It is mounted behind Naruon's existing private API authentication dependency. Inputs are either structured commitments (`commitment_id`, timezone-aware `start_at`/`end_at`, status) or iCalendar/ICS `proposed_ics` / `existing_ics` VEVENT documents. Occupying statuses are `confirmed`, `tentative`, and `desired`. RFC 5545 `STATUS:CANCELLED` is accepted and does not occupy the interval. Existing evidence is capped at 500 commitments per request. The Calendar coordination view selects a signed, source-backed writeback source for the authenticated user/workspace and does not present canned ICS pairs as production coordination evidence. Known `.ics` pairs remain test fixtures only.

## Standards traceability

RFC 5545 defines `VEVENT` `DTSTART` as inclusive and `DTEND` as non-inclusive, and requires `DTEND` to be later than `DTSTART`. Naruon therefore evaluates conflicts as half-open intervals `[start_at, end_at)`: an event ending exactly when another begins is not a collision. The implementation compares timezone-aware instants, so equivalent instants represented with different UTC offsets still collide.

RFC 5546 defines iTIP scheduling methods such as `REQUEST` and `REPLY`, including attendee participation status (`PARTSTAT`). It provides the interoperability basis for later RSVP/writeback integration, but it does **not** define Naruon's three-level scheduling priority. `confirmed > tentative > desired` is an explicit Naruon product policy required by roadmap issue #988, not a standards claim.

## Decision policy

- No occupying overlap, including overlap with only `STATUS:CANCELLED` events: `available`; the customer can proceed.
- Any equal- or higher-priority occupying overlap: `blocked`; the customer must choose another time or explicitly resolve that conflict first.
- Only lower-priority occupying overlaps: `review_required`; Naruon surfaces the lower-priority conflicts and requires explicit review instead of silently displacing them.
- An existing commitment with the same opaque identifier as the proposal is treated as the current representation of that event, not as a self-conflict.
- Conflict evidence is sorted by UTC start instant and then opaque identifier so provider response ordering cannot change the decision payload.

This policy deliberately prevents a convenience feature from silently breaking an existing confirmed commitment. A later RSVP slice may consume the same deterministic policy, but this slice does not claim RSVP mutation support.

## Security, privacy, and operability

The decision path is deterministic and uses no LLM judgment. It accepts only scheduling evidence needed for the decision; it does not require email bodies, participant names, provider credentials, or calendar descriptions. The endpoint rejects naive timestamps, invalid/non-positive intervals, unsupported statuses, oversized evidence batches, extra request fields, and a missing proposed source through the transport/service validation layers. A missing proposal returns `calendar_proposed_source_missing` as HTTP 422; the handler does not use `assert`, so optimized bytecode cannot strip the guard. Customer-facing results include a concrete next action rather than a generic warning.

No database objects or migrations are introduced. No provider is contacted. Rollback must disable or remove the frontend integration first (`frontend/src/components/calendar/types.ts`, `constants.ts`, `helpers.ts`, and `CalendarCoordinationView` wiring in `CalendarLayout`), then remove the backend route registration, ICS parser, and policy module. Existing calendar data is unaffected because the slice is read-only for provider and database state.

## Verification evidence required before merge

The exact unchanged PR head must prove known `.ics` pairs (cancelled allows, tentative review, confirmed blocks, adjacent allow), realistic overlap, adjacency, timezone-offset equivalence, deterministic ordering, self-update, invalid interval, unsupported status, API validation, authentication, and bounded-batch behavior. Repository-required CI, security, coverage, supply-chain, package, and independent current-head review gates remain authoritative; predecessor or queued evidence is non-passing. The policy decision is recorded in [ADR-0004](../adr/0004-status-weighted-calendar-conflicts.md).

## References (APA 7th)

Daboo, C. (Ed.). (2009). *iCalendar transport-independent interoperability protocol (iTIP)* (RFC 5546). RFC Editor. https://doi.org/10.17487/RFC5546

Desruisseaux, B. (Ed.). (2009). *Internet calendaring and scheduling core object specification (iCalendar)* (RFC 5545). RFC Editor. https://doi.org/10.17487/RFC5545
