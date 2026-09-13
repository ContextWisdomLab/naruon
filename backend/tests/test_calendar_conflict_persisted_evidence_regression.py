"""Regression coverage for malformed persisted calendar-conflict evidence."""

import datetime
from types import SimpleNamespace

import pytest

from api.calendar_conflicts import (
    CalendarConflictStoredEvidenceError,
    _judgment_response,
)


def _persisted_judgment_with(conflicts_json):
    now = datetime.datetime.now(datetime.UTC)
    return SimpleNamespace(
        judgment_uid="judgment_1",
        proposed_commitment_id="proposal_1",
        source_thread_id=None,
        source_message_id=None,
        decision_code="blocked",
        reason_code="overlap",
        conflicts_json=conflicts_json,
        recommended_action="Choose another time.",
        policy_version="v1",
        status_code="proposed",
        created_at=now,
        updated_at=now,
    )


def test_malformed_persisted_conflict_evidence_fails_with_stable_integrity_error() -> None:
    """Corrupt stored evidence must fail closed without leaking KeyError/Pydantic internals."""
    judgment = _persisted_judgment_with(
        [{"commitment_id": "existing_1", "status": "confirmed"}]
    )

    with pytest.raises(CalendarConflictStoredEvidenceError) as exc_info:
        _judgment_response(judgment)

    assert exc_info.value.error_code == "calendar_conflict_stored_evidence_corrupt"


@pytest.mark.parametrize("conflicts_json", [None, {}, "not-a-list"])
def test_non_list_persisted_conflict_evidence_fails_closed(conflicts_json) -> None:
    """The persisted JSON boundary requires a list of complete typed evidence rows."""
    with pytest.raises(CalendarConflictStoredEvidenceError):
        _judgment_response(_persisted_judgment_with(conflicts_json))
