"""Deterministic policy for preventing silent calendar double-booking.

The policy treats event time ranges as half-open intervals (inclusive start,
exclusive end) and ranks occupying Naruon commitment statuses as confirmed >
tentative > desired. RFC 5545 STATUS:CANCELLED is valid evidence and does not
occupy the interval. The occupying rank is a product policy, not an iCalendar
standard requirement. No lower-priority event is mutated or displaced
automatically.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Literal

CommitmentStatus = Literal["confirmed", "tentative", "desired", "cancelled"]
DecisionCode = Literal["available", "blocked", "review_required"]
PolicyValidationCode = Literal[
    "calendar_commitment_id_required",
    "calendar_timestamp_timezone_required",
    "calendar_interval_invalid",
    "calendar_status_unsupported",
    "calendar_ics_invalid",
    "calendar_ics_vevent_required",
    "calendar_ics_uid_required",
    "calendar_ics_dtstart_required",
    "calendar_ics_interval_required",
    "calendar_ics_datetime_required",
    "calendar_ics_single_vevent_required",
    "calendar_ics_byte_limit_exceeded",
    "calendar_ics_recurrence_unsupported",
    "calendar_existing_batch_exceeded",
    "calendar_proposed_source_missing",
]

_STATUS_PRIORITY: dict[str, int] = {
    "desired": 1,
    "tentative": 2,
    "confirmed": 3,
}
_OCCUPYING_STATUSES = frozenset(_STATUS_PRIORITY)
_KNOWN_STATUSES = frozenset((*_STATUS_PRIORITY, "cancelled"))
UTC = datetime.timezone.utc


class CalendarPolicyValidationError(ValueError):
    """Stable typed validation failure emitted by the calendar policy boundary.

    Attributes:
        error_code: Machine-readable code that remains stable when explanatory
            wording changes.
    """

    def __init__(self, error_code: PolicyValidationCode, message: str) -> None:
        """Create a validation failure with a stable public-facing code."""
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class CalendarCommitment:
    """One auditable scheduling commitment considered by the conflict policy.

    Attributes:
        commitment_id: Opaque non-blank identifier used to correlate evidence.
        start_at: Inclusive timezone-aware start instant.
        end_at: Exclusive timezone-aware end instant, strictly after ``start_at``.
        status: Naruon commitment priority or RFC 5545 cancelled (non-occupying).
    """

    commitment_id: str
    start_at: datetime.datetime
    end_at: datetime.datetime
    status: CommitmentStatus

    def __post_init__(self) -> None:
        """Fail closed when scheduling evidence is ambiguous or unsupported."""
        if not self.commitment_id.strip():
            raise CalendarPolicyValidationError(
                "calendar_commitment_id_required",
                "commitment_id must be non-blank",
            )
        _require_timezone_aware(self.start_at)
        _require_timezone_aware(self.end_at)
        if _as_utc(self.end_at) <= _as_utc(self.start_at):
            raise CalendarPolicyValidationError(
                "calendar_interval_invalid",
                "end_at must be later than start_at",
            )
        if self.status not in _KNOWN_STATUSES:
            raise CalendarPolicyValidationError(
                "calendar_status_unsupported",
                f"Unsupported commitment status: {self.status}",
            )


@dataclass(frozen=True, slots=True)
class CalendarConflictDecision:
    """Deterministic conflict evidence and the customer's required next action."""

    decision_code: DecisionCode
    reason_code: str
    conflicts: tuple[CalendarCommitment, ...]
    recommended_action: str
    policy_version: str = "status-weighted-v1"


def _require_timezone_aware(value: datetime.datetime) -> None:
    """Reject local/naive timestamps whose absolute instant is ambiguous."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise CalendarPolicyValidationError(
            "calendar_timestamp_timezone_required",
            "calendar commitment timestamps must be timezone-aware",
        )


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    """Return an already-validated aware timestamp in absolute UTC time."""
    return value.astimezone(UTC)


def occupies_interval(commitment: CalendarCommitment) -> bool:
    """Return whether the commitment claims its half-open interval.

    RFC 5545 ``STATUS:CANCELLED`` remains valid scheduling evidence, but the
    cancelled VEVENT no longer occupies the slot. Naruon ``desired``,
    ``tentative``, and ``confirmed`` commitments do occupy the interval.
    """
    return commitment.status in _OCCUPYING_STATUSES


def _overlaps(
    left: CalendarCommitment,
    right: CalendarCommitment,
) -> bool:
    """Return whether two half-open event intervals overlap in absolute time."""
    left_start = _as_utc(left.start_at)
    left_end = _as_utc(left.end_at)
    right_start = _as_utc(right.start_at)
    right_end = _as_utc(right.end_at)
    return left_start < right_end and right_start < left_end


def _conflict_sort_key(
    commitment: CalendarCommitment,
) -> tuple[datetime.datetime, str]:
    """Sort provider evidence deterministically by UTC instant then opaque ID."""
    return _as_utc(commitment.start_at), commitment.commitment_id


def evaluate_calendar_conflicts(
    proposed: CalendarCommitment,
    existing: list[CalendarCommitment] | tuple[CalendarCommitment, ...],
) -> CalendarConflictDecision:
    """Classify a proposed commitment without silently mutating existing events.

    Existing commitments with the same opaque identifier are treated as the
    current representation of the proposal rather than as a self-conflict.
    Cancelled commitments do not occupy an interval. Equal or higher-priority
    occupying overlaps block scheduling. Lower-priority occupying overlaps
    require explicit human review instead of automatic displacement.

    Args:
        proposed: Candidate commitment being considered for scheduling.
        existing: Provider- or database-derived commitments in any order.

    Returns:
        A deterministic decision with sorted conflict evidence and a concrete
        next action for the customer.
    """
    if not occupies_interval(proposed):
        return CalendarConflictDecision(
            decision_code="available",
            reason_code="no_overlapping_commitment",
            conflicts=(),
            recommended_action="Proceed with scheduling.",
        )

    conflicts = tuple(
        sorted(
            (
                commitment
                for commitment in existing
                if commitment.commitment_id != proposed.commitment_id
                and occupies_interval(commitment)
                and _overlaps(proposed, commitment)
            ),
            key=_conflict_sort_key,
        )
    )
    if not conflicts:
        return CalendarConflictDecision(
            decision_code="available",
            reason_code="no_overlapping_commitment",
            conflicts=(),
            recommended_action="Proceed with scheduling.",
        )

    proposed_priority = _STATUS_PRIORITY[proposed.status]
    if any(
        _STATUS_PRIORITY[commitment.status] >= proposed_priority
        for commitment in conflicts
    ):
        return CalendarConflictDecision(
            decision_code="blocked",
            reason_code="equal_or_higher_priority_conflict",
            conflicts=conflicts,
            recommended_action=(
                "Choose another time or explicitly resolve the equal/higher-priority "
                "conflict first."
            ),
        )

    return CalendarConflictDecision(
        decision_code="review_required",
        reason_code="lower_priority_conflict_requires_explicit_resolution",
        conflicts=conflicts,
        recommended_action=(
            "Review and explicitly reschedule or accept the lower-priority conflict "
            "before proceeding."
        ),
    )
