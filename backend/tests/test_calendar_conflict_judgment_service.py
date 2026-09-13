"""Unit tests for the pure/validation logic in the judgment persistence service."""

from __future__ import annotations

import datetime

import pytest

from db.models import CalendarConflictJudgment
from services.calendar_conflict_judgment_service import (
    CORRECTED_DECISION_REASON_CODE,
    UNSUPPORTED_DECISION_CODE_ERROR_CODE,
    UNSUPPORTED_STATUS_CODE_ERROR_CODE,
    _MAX_JUDGMENTS_PER_LIST,
    CalendarConflictCorrectionIncoherentError,
    CalendarConflictUnsupportedValueError,
    _conflicts_to_json,
    apply_correction,
    get_judgment,
    list_judgments,
    validate_correction_coherence,
)
from services.calendar_conflict_policy import (
    CalendarCommitment,
    CalendarConflictDecision,
    default_recommended_action,
)


class _FakeScalars:
    """The `.scalars()` half of a fake result, for list-style queries."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    """A scalar-result stand-in that never touches a real database."""

    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def scalars(self):
        rows = [] if self._row is None else [self._row]
        return _FakeScalars(rows)


class _RecordingSession:
    """Captures every statement passed to execute() instead of running it."""

    def __init__(self, row=None):
        self._row = row
        self.captured_statements: list[object] = []

    async def execute(self, stmt):
        self.captured_statements.append(stmt)
        return _FakeResult(self._row)

    async def flush(self) -> None:
        """No-op: this fake never talks to a real database."""

    def add(self, obj) -> None:
        """No-op: this fake never talks to a real database."""


def _judgment(**overrides) -> CalendarConflictJudgment:
    defaults = {
        "user_id": "user-1",
        "organization_id": None,
        "workspace_id": "workspace-1",
        "proposed_commitment_id": "proposal-1",
        "source_thread_id": "thread-1",
        "source_message_id": None,
        "decision_code": "review_required",
        "reason_code": "lower_priority_conflict_requires_explicit_resolution",
        "recommended_action": "Ask the proposer to confirm or reschedule.",
        "policy_version": "status-weighted-v1",
        "conflicts_json": [],
        "status_code": "proposed",
    }
    defaults.update(overrides)
    return CalendarConflictJudgment(**defaults)


def _decision() -> CalendarConflictDecision:
    conflict = CalendarCommitment(
        commitment_id="existing-1",
        start_at=datetime.datetime(2026, 8, 17, 10, 30, tzinfo=datetime.timezone.utc),
        end_at=datetime.datetime(2026, 8, 17, 11, 30, tzinfo=datetime.timezone.utc),
        status="tentative",
    )
    return CalendarConflictDecision(
        decision_code="review_required",
        reason_code="lower_priority_conflict_requires_explicit_resolution",
        conflicts=(conflict,),
        recommended_action="Ask the proposer to confirm or reschedule.",
    )


def test_conflicts_to_json_serializes_iso_timestamps_and_status() -> None:
    """The persisted evidence blob must be plain JSON, not raw datetimes."""
    payload = _conflicts_to_json(_decision())

    assert payload == [
        {
            "commitment_id": "existing-1",
            "start_at": "2026-08-17T10:30:00+00:00",
            "end_at": "2026-08-17T11:30:00+00:00",
            "status": "tentative",
        }
    ]


def test_validate_correction_coherence_requires_decision_for_override() -> None:
    """An override with no replacement decision is meaningless."""
    with pytest.raises(CalendarConflictCorrectionIncoherentError, match="requires a replacement"):
        validate_correction_coherence(status_code="overridden", decision_code=None)


@pytest.mark.parametrize("status_code", ["proposed", "confirmed", "dismissed"])
def test_validate_correction_coherence_forbids_decision_change_without_override(
    status_code: str,
) -> None:
    """Confirming or dismissing must never silently swap the decision."""
    with pytest.raises(CalendarConflictCorrectionIncoherentError, match="must not change"):
        validate_correction_coherence(status_code=status_code, decision_code="available")


def test_validate_correction_coherence_accepts_matching_pairs() -> None:
    """The two coherent shapes (override+decision, confirm/dismiss with none) pass."""
    validate_correction_coherence(status_code="overridden", decision_code="available")
    validate_correction_coherence(status_code="confirmed", decision_code=None)
    validate_correction_coherence(status_code="dismissed", decision_code=None)


@pytest.mark.asyncio
async def test_apply_correction_rejects_unsupported_status_code() -> None:
    """A bogus status_code must fail closed before any database lookup runs."""
    with pytest.raises(
        CalendarConflictUnsupportedValueError, match="status_code"
    ) as exc_info:
        await apply_correction(
            object(),
            judgment_uid="conflict_judgment_test",
            user_id="user-1",
            organization_id=None,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            correction_action="override",
            decision_code=None,
            status_code="not_a_real_status",
            rationale=None,
        )
    assert exc_info.value.error_code == UNSUPPORTED_STATUS_CODE_ERROR_CODE


@pytest.mark.asyncio
async def test_apply_correction_rejects_unsupported_decision_code() -> None:
    """A bogus decision_code must fail closed before any database lookup runs."""
    with pytest.raises(
        CalendarConflictUnsupportedValueError, match="decision_code"
    ) as exc_info:
        await apply_correction(
            object(),
            judgment_uid="conflict_judgment_test",
            user_id="user-1",
            organization_id=None,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            correction_action="override",
            decision_code="not_a_real_decision",
            status_code="confirmed",
            rationale=None,
        )
    assert exc_info.value.error_code == UNSUPPORTED_DECISION_CODE_ERROR_CODE


@pytest.mark.asyncio
async def test_apply_correction_rejects_incoherent_status_and_decision() -> None:
    """A confirm/dismiss that also tries to change the decision must fail closed."""
    with pytest.raises(CalendarConflictCorrectionIncoherentError):
        await apply_correction(
            object(),
            judgment_uid="conflict_judgment_test",
            user_id="user-1",
            organization_id=None,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            correction_action="confirm_decision",
            decision_code="available",
            status_code="confirmed",
            rationale=None,
        )


@pytest.mark.asyncio
async def test_apply_correction_locks_the_judgment_row() -> None:
    """Concurrent corrections must never read the same unlocked row."""
    session = _RecordingSession(row=_judgment())

    await apply_correction(
        session,
        judgment_uid="conflict_judgment_test",
        user_id="user-1",
        organization_id=None,
        workspace_id="workspace-1",
        actor_user_id="reviewer",
        correction_action="override_decision",
        decision_code="available",
        status_code="overridden",
        rationale="Confirmed with the proposer directly.",
    )

    assert len(session.captured_statements) == 1
    compiled = str(session.captured_statements[0])
    assert "FOR UPDATE" in compiled
    assert "workspace_id" in compiled


@pytest.mark.asyncio
async def test_apply_correction_overriding_decision_keeps_reason_and_action_coherent() -> None:
    """A corrected decision must never be paired with the old decision's reason/action."""
    judgment = _judgment()
    session = _RecordingSession(row=judgment)

    correction = await apply_correction(
        session,
        judgment_uid="conflict_judgment_test",
        user_id="user-1",
        organization_id=None,
        workspace_id="workspace-1",
        actor_user_id="reviewer",
        correction_action="override_decision",
        decision_code="available",
        status_code="overridden",
        rationale="Confirmed with the proposer directly.",
    )

    assert judgment.decision_code == "available"
    assert judgment.reason_code == CORRECTED_DECISION_REASON_CODE
    # recommended_action is restated from the policy's own canonical mapping,
    # never from rationale -- rationale is an explanation, not scheduling advice.
    assert judgment.recommended_action == default_recommended_action("available")
    assert judgment.recommended_action != "Confirmed with the proposer directly."
    # The rationale itself is preserved, just not as recommended_action.
    assert correction.correction_rationale == "Confirmed with the proposer directly."
    # The original decision's reason/action are never lost -- they are in before_json.
    assert correction.before_json["reason_code"] == "lower_priority_conflict_requires_explicit_resolution"
    assert correction.after_json["reason_code"] == CORRECTED_DECISION_REASON_CODE
    assert correction.after_json["recommended_action"] == default_recommended_action("available")


@pytest.mark.asyncio
async def test_apply_correction_confirming_without_decision_change_keeps_original_reason() -> None:
    """Confirming a judgment as-is must not fabricate a new reason/action."""
    judgment = _judgment()
    session = _RecordingSession(row=judgment)

    await apply_correction(
        session,
        judgment_uid="conflict_judgment_test",
        user_id="user-1",
        organization_id=None,
        workspace_id="workspace-1",
        actor_user_id="reviewer",
        correction_action="confirm_decision",
        decision_code=None,
        status_code="confirmed",
        rationale=None,
    )

    assert judgment.decision_code == "review_required"
    assert judgment.reason_code == "lower_priority_conflict_requires_explicit_resolution"
    assert judgment.recommended_action == "Ask the proposer to confirm or reschedule."
    assert judgment.status_code == "confirmed"


@pytest.mark.asyncio
async def test_apply_correction_override_repeating_current_decision_keeps_original_reason() -> None:
    """An override that repeats the current decision must not erase the original reason."""
    judgment = _judgment()
    session = _RecordingSession(row=judgment)

    await apply_correction(
        session,
        judgment_uid="conflict_judgment_test",
        user_id="user-1",
        organization_id=None,
        workspace_id="workspace-1",
        actor_user_id="reviewer",
        correction_action="override_decision",
        decision_code="review_required",  # same as the judgment's current decision
        status_code="overridden",
        rationale=None,
    )

    assert judgment.decision_code == "review_required"
    assert judgment.reason_code == "lower_priority_conflict_requires_explicit_resolution"
    assert judgment.recommended_action == "Ask the proposer to confirm or reschedule."
    assert judgment.status_code == "overridden"


@pytest.mark.asyncio
async def test_list_judgments_bounds_the_result_set_and_scopes_by_workspace() -> None:
    """An unbounded list query could grow without limit for a long-lived account."""
    session = _RecordingSession()

    await list_judgments(
        session, user_id="user-1", organization_id=None, workspace_id="workspace-1"
    )

    assert len(session.captured_statements) == 1
    compiled = str(
        session.captured_statements[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert f"LIMIT {_MAX_JUDGMENTS_PER_LIST}" in compiled
    assert "workspace_id" in compiled
    # created_at alone is not a unique key: two judgments created in the same
    # instant could otherwise reorder across the 200-row boundary between
    # calls. calendar_conflict_judgment_id (a monotonic primary key) breaks
    # the tie deterministically.
    assert "ORDER BY calendar_conflict_judgments.created_at DESC, " in compiled
    assert "calendar_conflict_judgments.calendar_conflict_judgment_id DESC" in compiled


@pytest.mark.asyncio
async def test_get_judgment_reaches_a_row_outside_the_list_bound() -> None:
    """A judgment past the 200-row list window must still be individually reachable."""
    judgment = _judgment()
    session = _RecordingSession(row=judgment)

    fetched = await get_judgment(
        session,
        judgment_uid="conflict_judgment_test",
        user_id="user-1",
        organization_id=None,
        workspace_id="workspace-1",
    )

    assert fetched is judgment
    assert len(session.captured_statements) == 1
    assert "workspace_id" in str(session.captured_statements[0])
