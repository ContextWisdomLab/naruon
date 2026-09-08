"""Regression contracts for deterministic status-weighted calendar conflicts."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest

from services.calendar_conflict_policy import (
    CalendarCommitment,
    evaluate_calendar_conflicts,
)

UTC = datetime.timezone.utc


def _commitment(
    commitment_id: str,
    start_hour: int,
    end_hour: int,
    status: str,
    *,
    tz: datetime.tzinfo = UTC,
) -> CalendarCommitment:
    """Build one realistic commitment on a fixed date for policy tests."""
    return CalendarCommitment(
        commitment_id=commitment_id,
        start_at=datetime.datetime(2026, 8, 17, start_hour, tzinfo=tz),
        end_at=datetime.datetime(2026, 8, 17, end_hour, tzinfo=tz),
        status=status,
    )


@pytest.mark.parametrize(
    ("proposed_status", "existing_status"),
    [
        ("confirmed", "confirmed"),
        ("tentative", "confirmed"),
        ("tentative", "tentative"),
        ("desired", "confirmed"),
        ("desired", "tentative"),
        ("desired", "desired"),
    ],
)
def test_equal_or_higher_priority_overlap_blocks_scheduling(
    proposed_status: str,
    existing_status: str,
) -> None:
    """Equal or stronger existing commitments must block silent double-booking."""
    result = evaluate_calendar_conflicts(
        _commitment("proposal", 10, 11, proposed_status),
        [_commitment("existing", 10, 11, existing_status)],
    )

    assert result.decision_code == "blocked"
    assert result.reason_code == "equal_or_higher_priority_conflict"
    assert [conflict.commitment_id for conflict in result.conflicts] == ["existing"]
    assert "Choose another time" in result.recommended_action


@pytest.mark.parametrize(
    ("proposed_status", "existing_status"),
    [
        ("confirmed", "tentative"),
        ("confirmed", "desired"),
        ("tentative", "desired"),
    ],
)
def test_lower_priority_overlap_requires_explicit_review(
    proposed_status: str,
    existing_status: str,
) -> None:
    """Higher-priority proposals may not silently displace lower commitments."""
    result = evaluate_calendar_conflicts(
        _commitment("proposal", 10, 11, proposed_status),
        [_commitment("existing", 10, 11, existing_status)],
    )

    assert result.decision_code == "review_required"
    assert result.reason_code == "lower_priority_conflict_requires_explicit_resolution"
    assert "Review" in result.recommended_action


def test_adjacent_half_open_intervals_are_available() -> None:
    """RFC 5545 end-exclusive event boundaries must not create false conflicts."""
    result = evaluate_calendar_conflicts(
        _commitment("proposal", 11, 12, "confirmed"),
        [_commitment("existing", 10, 11, "confirmed")],
    )

    assert result.decision_code == "available"
    assert result.reason_code == "no_overlapping_commitment"
    assert result.conflicts == ()
    assert result.recommended_action == "Proceed with scheduling."


def test_equivalent_instants_across_offsets_overlap() -> None:
    """Equivalent instants represented in different UTC offsets must conflict."""
    korea = datetime.timezone(datetime.timedelta(hours=9))
    result = evaluate_calendar_conflicts(
        _commitment("proposal", 10, 11, "confirmed", tz=korea),
        [
            CalendarCommitment(
                commitment_id="existing",
                start_at=datetime.datetime(2026, 8, 17, 0, 30, tzinfo=UTC),
                end_at=datetime.datetime(2026, 8, 17, 1, 30, tzinfo=UTC),
                status="confirmed",
            )
        ],
    )

    assert result.decision_code == "blocked"


def test_dst_fold_interval_order_uses_absolute_instants() -> None:
    """A valid interval spanning the repeated DST hour must compare by UTC instant."""
    new_york = ZoneInfo("America/New_York")
    commitment = CalendarCommitment(
        commitment_id="fall-back-span",
        start_at=datetime.datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0),
        end_at=datetime.datetime(2026, 11, 1, 1, 15, tzinfo=new_york, fold=1),
        status="confirmed",
    )

    assert commitment.start_at.astimezone(UTC) < commitment.end_at.astimezone(UTC)


def test_dst_fold_overlap_uses_absolute_instants() -> None:
    """Repeated-hour wall times that are disjoint in UTC must remain non-conflicting."""
    new_york = ZoneInfo("America/New_York")
    proposed = CalendarCommitment(
        commitment_id="first-hour",
        start_at=datetime.datetime(2026, 11, 1, 1, 0, tzinfo=new_york, fold=0),
        end_at=datetime.datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0),
        status="desired",
    )
    existing = CalendarCommitment(
        commitment_id="second-hour",
        start_at=datetime.datetime(2026, 11, 1, 1, 15, tzinfo=new_york, fold=1),
        end_at=datetime.datetime(2026, 11, 1, 1, 45, tzinfo=new_york, fold=1),
        status="confirmed",
    )

    result = evaluate_calendar_conflicts(proposed, [existing])

    assert result.decision_code == "available"
    assert result.conflicts == ()


def test_conflicts_are_deterministically_sorted_by_utc_start_and_identifier() -> None:
    """Conflict evidence ordering must not depend on provider response ordering."""
    proposed = _commitment("proposal", 9, 13, "desired")
    existing = [
        _commitment("z-later", 11, 12, "confirmed"),
        _commitment("b-same", 10, 11, "confirmed"),
        _commitment("a-same", 10, 11, "tentative"),
    ]

    result = evaluate_calendar_conflicts(proposed, existing)

    assert [conflict.commitment_id for conflict in result.conflicts] == [
        "a-same",
        "b-same",
        "z-later",
    ]


def test_same_commitment_identifier_is_not_self_conflict() -> None:
    """An update may include its current event in provider results without self-blocking."""
    proposed = _commitment("same-event", 10, 11, "confirmed")

    result = evaluate_calendar_conflicts(proposed, [proposed])

    assert result.decision_code == "available"


@pytest.mark.parametrize(
    ("start_at", "end_at", "message"),
    [
        (
            datetime.datetime(2026, 8, 17, 10),
            datetime.datetime(2026, 8, 17, 11),
            "timezone-aware",
        ),
        (
            datetime.datetime(2026, 8, 17, 10, tzinfo=UTC),
            datetime.datetime(2026, 8, 17, 10, tzinfo=UTC),
            "later than start_at",
        ),
    ],
)
def test_commitment_rejects_ambiguous_or_non_positive_intervals(
    start_at: datetime.datetime,
    end_at: datetime.datetime,
    message: str,
) -> None:
    """Conflict decisions must reject naive or zero-length scheduling evidence."""
    with pytest.raises(ValueError, match=message):
        CalendarCommitment(
            commitment_id="invalid",
            start_at=start_at,
            end_at=end_at,
            status="confirmed",
        )


def test_commitment_requires_non_blank_identifier() -> None:
    """Opaque commitment identifiers must be non-blank for auditable evidence."""
    with pytest.raises(ValueError, match="non-blank"):
        _commitment("   ", 10, 11, "confirmed")


def test_cancelled_existing_commitment_does_not_block_confirmed_proposal() -> None:
    """RFC 5545 STATUS:CANCELLED does not occupy the interval, so booking may proceed."""
    result = evaluate_calendar_conflicts(
        _commitment("proposal", 10, 11, "confirmed"),
        [_commitment("cancelled-prior", 10, 11, "cancelled")],
    )

    assert result.decision_code == "available"
    assert result.reason_code == "no_overlapping_commitment"
    assert result.conflicts == ()


def test_cancelled_proposal_does_not_claim_the_interval() -> None:
    """A cancelled proposal is not a booking and must not create a conflict decision."""
    result = evaluate_calendar_conflicts(
        _commitment("cancelled-proposal", 10, 11, "cancelled"),
        [_commitment("existing", 10, 11, "confirmed")],
    )

    assert result.decision_code == "available"
    assert result.conflicts == ()


def test_commitment_rejects_unknown_status() -> None:
    """Unknown participation states must fail closed instead of gaining a rank."""
    with pytest.raises(ValueError, match="Unsupported commitment status"):
        _commitment("unknown-status", 10, 11, "busy")
