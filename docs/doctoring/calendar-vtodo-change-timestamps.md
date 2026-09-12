# VTODO change-management timestamps

## Problem

`CalendarTask.created_at` existed in the Naruon calendar writeback model but was not serialized into VTODO output. The generated component therefore exposed `DTSTAMP` only and lost the calendar-store creation timestamp.

A second standards gap became visible while restoring that field: RFC 5545 requires both `CREATED` and `DTSTAMP` change-management values to be represented in UTC. `generate_ics_from_task()` accepted arbitrary `datetime` values, so a non-UTC aware timestamp could be handed directly to the serializer and a naive timestamp could depend on process-local timezone behavior if normalized implicitly.

## Contract

For Naruon-generated VTODO components:

- `CREATED` is emitted from `CalendarTask.created_at`;
- `DTSTAMP` remains sourced from `CalendarTask.updated_at`;
- both timestamps are normalized to `datetime.timezone.utc` before serialization;
- naive or otherwise offset-less values fail closed with a field-specific `ValueError` rather than being interpreted in a machine-local timezone;
- `DUE` semantics are unchanged because RFC 5545 permits additional DATE-TIME forms for that property.

The current production caller in `backend/api/calendar.py` already constructs both change-management timestamps with `datetime.datetime.now(datetime.timezone.utc)`, so the stricter boundary preserves the live writeback path while making the serializer safe for future callers.

## Evidence lineage

- Original product RED: VTODO parsing raised `KeyError` for `CREATED` on predecessor `db74bb189817345fc9dbe1db038e5e787e5d9a45` before its one-line serializer repair.
- Canonical dependency-security adoption: `443d13e1446c8d7140e889a8bcbcf4c2b616f3bd` preserves the predecessor as first-parent provenance and adopts `#1623@17a7618eda2b212b691f08fa936e042b34258fc9` without copying dependency-owner source.
- UTC-boundary RED: `e74537faa3cf39e7f628dbc5be4d6adefdbe800e` requires non-UTC aware `CREATED`/`DTSTAMP` inputs to serialize as UTC and requires naive values to be rejected.
- Causal fix: `184446b5a2c5e797e62ba5aa6dd5ce65bbc691ba` restores `CREATED` and introduces a single UTC normalization boundary used by both change-management fields.

The RED commit is source-order evidence; it is not described as a terminal hosted failure unless an immutable workflow receipt for that exact head is available.

## Alternatives considered

Leaving timezone conversion to the iCalendar library was rejected because the domain contract would remain implicit and naive values could acquire host-local meaning. Treating naive timestamps as UTC was also rejected because that silently changes the meaning of an ambiguous input. Rejecting offset-less values makes the serialization boundary deterministic and keeps UTC requirements explicit.

## Acceptance

The final exact head must prove that:

1. parsing the emitted VTODO recovers `CREATED` from the task creation instant;
2. aware timestamps with non-zero offsets serialize as UTC `Z` values for both `CREATED` and `DTSTAMP`;
3. naive `created_at` and `updated_at` values are rejected;
4. the existing status, summary escaping, and optional `DUE` behavior remains green;
5. no frontend dependency/security source is duplicated from the canonical #1623 owner.

Hosted checks and independent review are head/base-specific and must be regenerated after the final stacked topology is established.

## Reference

Desruisseaux, B. (2009). *Internet Calendaring and Scheduling Core Object Specification (iCalendar)* (RFC 5545). Internet Engineering Task Force. https://doi.org/10.17487/RFC5545

RFC 5545 §3.8.7.1 defines `CREATED` for VTODO and requires UTC; §3.8.7.2 requires `DTSTAMP` on VTODO and requires UTC. The UTC requirement is the authority for the normalization and fail-closed boundary above.
