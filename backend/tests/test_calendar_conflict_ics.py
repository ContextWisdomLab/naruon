"""Known iCalendar VEVENT pairs must decide conflict vs allow by STATUS."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.calendar_conflict_ics import (
    evaluate_calendar_conflicts_from_ics,
    parse_calendar_commitments_from_ics,
)
from services.calendar_conflict_policy import CalendarPolicyValidationError

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "calendar"


def _ics(name: str) -> str:
    """Load one synthetic iCalendar/ICS VEVENT fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("proposed_name", "existing_name", "decision_code", "reason_code"),
    [
        (
            "proposed-confirmed-1000z.ics",
            "existing-cancelled-1000z.ics",
            "available",
            "no_overlapping_commitment",
        ),
        (
            "proposed-confirmed-1000z.ics",
            "existing-confirmed-adjacent-1100z.ics",
            "available",
            "no_overlapping_commitment",
        ),
        (
            "proposed-confirmed-1000z.ics",
            "existing-tentative-1030z.ics",
            "review_required",
            "lower_priority_conflict_requires_explicit_resolution",
        ),
        (
            "proposed-tentative-1000z.ics",
            "existing-confirmed-1000z.ics",
            "blocked",
            "equal_or_higher_priority_conflict",
        ),
        (
            "proposed-confirmed-1000z.ics",
            "existing-confirmed-1000z.ics",
            "blocked",
            "equal_or_higher_priority_conflict",
        ),
    ],
)
def test_known_ics_pairs_decide_conflict_or_allow(
    proposed_name: str,
    existing_name: str,
    decision_code: str,
    reason_code: str,
) -> None:
    """RFC 5545 STATUS on overlapping VEVENTs must yield a deterministic product decision."""
    result = evaluate_calendar_conflicts_from_ics(
        proposed_ics=_ics(proposed_name),
        existing_ics=_ics(existing_name),
    )

    assert result.decision_code == decision_code
    assert result.reason_code == reason_code
    if decision_code == "available":
        assert result.conflicts == ()
        assert "Proceed" in result.recommended_action
    else:
        assert result.conflicts
        assert result.recommended_action


def test_cancelled_vevent_is_parsed_but_does_not_occupy_the_slot() -> None:
    """STATUS:CANCELLED is valid iCalendar evidence and must not block a confirmed proposal."""
    commitments = parse_calendar_commitments_from_ics(_ics("existing-cancelled-1000z.ics"))

    assert len(commitments) == 1
    assert commitments[0].commitment_id == "existing-cancelled-1000z"
    assert commitments[0].status == "cancelled"

    result = evaluate_calendar_conflicts_from_ics(
        proposed_ics=_ics("proposed-confirmed-1000z.ics"),
        existing_ics=_ics("existing-cancelled-1000z.ics"),
    )
    assert result.decision_code == "available"
    assert result.conflicts == ()


def test_ics_parser_rejects_calendar_without_vevent() -> None:
    """A VCALENDAR that carries no VEVENT cannot be treated as scheduling evidence."""
    with pytest.raises(CalendarPolicyValidationError) as exc_info:
        parse_calendar_commitments_from_ics(
            "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"
        )

    assert exc_info.value.error_code == "calendar_ics_vevent_required"


def test_ics_parser_rejects_oversized_document_before_parse() -> None:
    """Direct service callers must hit the byte bound before Calendar.from_ical."""
    oversized_ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        + ("X-PAD:" + ("A" * 1024) + "\n") * 260
        + "END:VCALENDAR\n"
    )

    assert len(oversized_ics.encode("utf-8")) > 262_144
    with pytest.raises(CalendarPolicyValidationError) as exc_info:
        parse_calendar_commitments_from_ics(oversized_ics)

    assert exc_info.value.error_code == "calendar_ics_byte_limit_exceeded"


def test_existing_ics_stops_conversion_and_rejects_batch_over_500() -> None:
    """Conversion must stop at 501 VEVENTs and still raise the existing batch code."""
    vevents = "\n".join(
        "\n".join(
            [
                "BEGIN:VEVENT",
                f"UID:existing-batch-{index}",
                "DTSTART:20260817T100000Z",
                "DTEND:20260817T110000Z",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )
        for index in range(501)
    )
    existing_ics = f"BEGIN:VCALENDAR\nVERSION:2.0\n{vevents}\nEND:VCALENDAR\n"

    with pytest.raises(CalendarPolicyValidationError) as exc_info:
        evaluate_calendar_conflicts_from_ics(
            proposed_ics=_ics("proposed-confirmed-1000z.ics"),
            existing_ics=existing_ics,
        )

    assert exc_info.value.error_code == "calendar_existing_batch_exceeded"


def test_recurring_non_initial_instance_cannot_be_treated_as_available() -> None:
    """A later RRULE instance must not disappear into a single available interval."""
    existing_ics = "\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:weekly-standup",
            "DTSTAMP:20260801T000000Z",
            "DTSTART:20260810T100000Z",
            "DTEND:20260810T110000Z",
            "RRULE:FREQ=WEEKLY;COUNT=4",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )

    with pytest.raises(CalendarPolicyValidationError) as exc_info:
        evaluate_calendar_conflicts_from_ics(
            proposed_ics=_ics("proposed-confirmed-1000z.ics"),
            existing_ics=existing_ics,
        )

    assert exc_info.value.error_code == "calendar_ics_recurrence_unsupported"


def test_ics_parser_rejects_vevent_without_uid() -> None:
    """Opaque UID is required so conflict evidence stays auditable."""
    with pytest.raises(CalendarPolicyValidationError) as exc_info:
        parse_calendar_commitments_from_ics(
            "\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "BEGIN:VEVENT",
                    "DTSTART:20260817T100000Z",
                    "DTEND:20260817T110000Z",
                    "STATUS:CONFIRMED",
                    "END:VEVENT",
                    "END:VCALENDAR",
                    "",
                ]
            )
        )

    assert exc_info.value.error_code == "calendar_ics_uid_required"
