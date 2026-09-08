# ADR-0004: Status-weighted calendar conflicts from iCalendar evidence

**Status:** Accepted (Naruon-local scheduling policy)
**Date:** 2026-08-17
**Decision owner:** Naruon maintainers
**Scope:** Naruon's conflict-decision product behavior for customer-owned CalDAV
evidence. This ADR does not make Naruon a calendar host and does not authorize
provider mutation, RSVP send, or automatic reschedule.

## Context

Naruon is a web client over customer-owned CalDAV. Buyers cannot trust the
calendar unless overlapping VEVENTs are classified by their RFC 5545 `STATUS`
instead of treating every interval as equally busy. The product statuses
`confirmed`, `tentative`, and `desired` remain a Naruon priority axis. RFC 5545
also defines `STATUS:CANCELLED`, which must not occupy a slot after the event
is withdrawn.

## Decision

1. Occupying commitments rank `confirmed > tentative > desired`. Equal or
   higher-priority overlap is `blocked`. Lower-priority-only overlap is
   `review_required`. No occupying overlap is `available`.
2. `STATUS:CANCELLED` is valid evidence and does not occupy `[DTSTART, DTEND)`.
   A cancelled existing event therefore allows a new booking; a cancelled
   proposal does not claim the interval.
3. iCalendar/ICS evidence is accepted as text. The evaluator parses
   `VEVENT` `UID`, timezone-aware `DTSTART`, `DTEND` or `DURATION`, and
   `STATUS`. Missing `STATUS` defaults to `CONFIRMED`. Date-only and floating
   date-times fail closed.
4. The decision is advisory. It does not write CalDAV, change ETags, or
   displace an existing event. Customer copy names the next action.
5. Unknown statuses fail closed. The same opaque `UID` is excluded as a
   self-update, not as a conflict.

## Alternatives rejected

### Treat cancelled as an unsupported status

Rejected because RFC 5545 already names `CANCELLED`. Rejecting it prevents
buyers from booking a freed slot and forces a false double-booking.

### Rank cancelled as the lowest occupying priority

Rejected because a cancelled VEVENT no longer claims the interval. Ranking it
below `desired` would still emit `review_required` and block silent reuse of a
freed hour.

### Infer conflicts only from JSON commitments

Rejected as the product path. Customer calendars arrive as `.ics`. The JSON
commitment envelope remains for tests and later structured sources; it is not
a substitute for VEVENT evidence.

## Consequences

- `POST /api/calendar/conflicts/evaluate` accepts either structured commitments
  or `proposed_ics` / `existing_ics`.
- Calendar coordination selects a signed writeback source. Known VEVENT pairs
  remain test fixtures, not production coordination evidence. Writeback remains
  a separate ETag/If-Match intent path.
- Tests must keep known `.ics` pairs as the source of conflict-versus-allow
  evidence.

## References (APA 7th)

Daboo, C. (Ed.). (2009). *iCalendar transport-independent interoperability
protocol (iTIP)* (RFC 5546). RFC Editor. https://doi.org/10.17487/RFC5546

Allen, J. F. (1983). Maintaining knowledge about temporal intervals.
*Communications of the ACM, 26*(11), 832–843.
https://doi.org/10.1145/182.358434
Allen’s interval algebra names the qualitative relations between time
intervals, including overlap, which is the comparison this policy applies to
half-open calendar commitments. The ACM publication is not redistributed here.

Desruisseaux, B. (Ed.). (2009). *Internet calendaring and scheduling core
object specification (iCalendar)* (RFC 5545). RFC Editor.
https://doi.org/10.17487/RFC5545
