"""Parse RFC 5545 VEVENT evidence into status-weighted calendar commitments."""

from __future__ import annotations

import datetime
from typing import Any

from icalendar import Calendar

from services.calendar_conflict_policy import (
    MAX_EXISTING_COMMITMENTS,
    CalendarCommitment,
    CalendarConflictDecision,
    CalendarPolicyValidationError,
    CommitmentStatus,
    PolicyValidationCode,
    evaluate_calendar_conflicts,
)

_ICS_STATUS_MAP: dict[str, CommitmentStatus] = {
    "CONFIRMED": "confirmed",
    "TENTATIVE": "tentative",
    "CANCELLED": "cancelled",
}
_MAX_CONVERTED_VEVENTS = MAX_EXISTING_COMMITMENTS + 1
_MAX_ICS_DOCUMENT_BYTES = 262_144
_RECURRENCE_PROPERTY_NAMES = ("RRULE", "RDATE", "EXDATE")


def parse_calendar_commitments_from_ics(ics_text: str) -> tuple[CalendarCommitment, ...]:
    """Extract VEVENT commitments from one iCalendar/ICS document.

    RFC 5545 VEVENT ``STATUS`` defaults to ``CONFIRMED`` when omitted. Date-only
    and floating date-times are rejected because their absolute instant is
    ambiguous. ``DURATION`` is accepted in place of ``DTEND``.
    """
    calendar = _parse_calendar(ics_text)
    commitments = _commitments_from_calendar(calendar)
    if not commitments:
        raise CalendarPolicyValidationError(
            "calendar_ics_vevent_required",
            "iCalendar evidence must include at least one VEVENT",
        )
    return commitments


def parse_existing_calendar_commitments_from_ics(
    ics_text: str,
) -> tuple[CalendarCommitment, ...]:
    """Extract zero or more existing VEVENT commitments from one document."""
    return _commitments_from_calendar(_parse_calendar(ics_text))


def parse_proposed_calendar_commitment_from_ics(ics_text: str) -> CalendarCommitment:
    """Extract exactly one proposed VEVENT commitment from iCalendar text."""
    proposed_commitments = parse_calendar_commitments_from_ics(ics_text)
    if len(proposed_commitments) != 1:
        raise CalendarPolicyValidationError(
            "calendar_ics_single_vevent_required",
            "proposed iCalendar evidence must contain exactly one VEVENT",
        )
    return proposed_commitments[0]


def evaluate_calendar_conflicts_from_ics(
    proposed_ics: str,
    existing_ics: str,
) -> CalendarConflictDecision:
    """Evaluate one proposed VEVENT against existing VEVENT evidence."""
    proposed_commitment = parse_proposed_calendar_commitment_from_ics(proposed_ics)
    existing_commitments = parse_existing_calendar_commitments_from_ics(existing_ics)
    if len(existing_commitments) > MAX_EXISTING_COMMITMENTS:
        raise CalendarPolicyValidationError(
            "calendar_existing_batch_exceeded",
            "existing iCalendar evidence exceeds the bounded commitment batch",
        )
    return evaluate_calendar_conflicts(proposed_commitment, existing_commitments)


def _parse_calendar(ics_text: str) -> Calendar:
    """Parse iCalendar text without leaking parser internals."""
    if len(ics_text.encode("utf-8")) > _MAX_ICS_DOCUMENT_BYTES:
        raise CalendarPolicyValidationError(
            "calendar_ics_byte_limit_exceeded",
            "iCalendar evidence exceeds the bounded document size",
        )
    try:
        calendar = Calendar.from_ical(ics_text)
    except (ValueError, TypeError, KeyError) as exc:
        raise CalendarPolicyValidationError(
            "calendar_ics_invalid",
            "iCalendar evidence is not a valid VCALENDAR document",
        ) from exc
    if not isinstance(calendar, Calendar):
        raise CalendarPolicyValidationError(
            "calendar_ics_invalid",
            "iCalendar evidence is not a valid VCALENDAR document",
        )
    return calendar


def _commitments_from_calendar(calendar: Calendar) -> tuple[CalendarCommitment, ...]:
    """Convert VEVENTs until the bounded batch plus one overflow item."""
    commitments: list[CalendarCommitment] = []
    for component in calendar.walk("VEVENT"):
        if len(commitments) >= _MAX_CONVERTED_VEVENTS:
            break
        commitments.append(_commitment_from_vevent(component))
    return tuple(commitments)


def _reject_recurrence_properties(component: Any) -> None:
    """Fail closed when RRULE, RDATE, or EXDATE would hide later instances."""
    if any(property_name in component for property_name in _RECURRENCE_PROPERTY_NAMES):
        raise CalendarPolicyValidationError(
            "calendar_ics_recurrence_unsupported",
            "iCalendar evidence must not include RRULE, RDATE, or EXDATE",
        )


def _commitment_from_vevent(component: Any) -> CalendarCommitment:
    """Convert one VEVENT into a timezone-aware policy commitment."""
    _reject_recurrence_properties(component)
    commitment_id = _text_property(component, "UID")
    if commitment_id is None or not commitment_id.strip():
        raise CalendarPolicyValidationError(
            "calendar_ics_uid_required",
            "VEVENT evidence must include a non-blank UID",
        )
    start_at = _aware_datetime_property(component, "DTSTART", "calendar_ics_dtstart_required")
    end_at = _vevent_end_at(component, start_at)
    return CalendarCommitment(
        commitment_id=commitment_id.strip(),
        start_at=start_at,
        end_at=end_at,
        status=_vevent_status(component),
    )


def _vevent_status(component: Any) -> CommitmentStatus:
    """Map RFC 5545 VEVENT STATUS, defaulting to confirmed when omitted."""
    raw_status = _text_property(component, "STATUS")
    if raw_status is None or not raw_status.strip():
        return "confirmed"
    mapped = _ICS_STATUS_MAP.get(raw_status.strip().upper())
    if mapped is None:
        raise CalendarPolicyValidationError(
            "calendar_status_unsupported",
            f"Unsupported commitment status: {raw_status}",
        )
    return mapped


def _vevent_end_at(
    component: Any,
    start_at: datetime.datetime,
) -> datetime.datetime:
    """Resolve exclusive end from DTEND or DURATION, never both."""
    has_end = "DTEND" in component
    has_duration = "DURATION" in component
    if has_end and has_duration:
        raise CalendarPolicyValidationError(
            "calendar_ics_interval_required",
            "VEVENT evidence must not include both DTEND and DURATION",
        )
    if has_end:
        return _aware_datetime_property(
            component,
            "DTEND",
            "calendar_ics_interval_required",
        )
    if has_duration:
        duration = component.decoded("DURATION")
        if not isinstance(duration, datetime.timedelta) or duration <= datetime.timedelta(0):
            raise CalendarPolicyValidationError(
                "calendar_ics_interval_required",
                "VEVENT DURATION must be a positive interval",
            )
        return start_at + duration
    raise CalendarPolicyValidationError(
        "calendar_ics_interval_required",
        "VEVENT evidence must include DTEND or DURATION",
    )


def _aware_datetime_property(
    component: Any,
    property_name: str,
    missing_error_code: PolicyValidationCode,
) -> datetime.datetime:
    """Read a timezone-aware date-time property or fail closed."""
    if property_name not in component:
        raise CalendarPolicyValidationError(
            missing_error_code,
            f"VEVENT evidence must include {property_name}",
        )
    value = component.decoded(property_name)
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        raise CalendarPolicyValidationError(
            "calendar_ics_datetime_required",
            "VEVENT date-times must be DATE-TIME values, not DATE",
        )
    if not isinstance(value, datetime.datetime):
        raise CalendarPolicyValidationError(
            "calendar_ics_datetime_required",
            "VEVENT date-times must be DATE-TIME values, not DATE",
        )
    return value


def _text_property(component: Any, property_name: str) -> str | None:
    """Return a decoded iCalendar text property, or None when absent."""
    if property_name not in component:
        return None
    value = component.decoded(property_name)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    return str(value)
