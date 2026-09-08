"""API contracts for buyer-visible calendar conflict decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.auth import get_auth_context
from api.calendar_conflicts import (
    CalendarConflictRequest,
    evaluate_calendar_conflict_request,
)
from main import app

pytestmark = pytest.mark.usefixtures("dev_auth_dependency_overrides")

client = TestClient(app, headers={"X-User-Id": "calendar-conflict-user"})


def _request_payload() -> dict[str, object]:
    """Return one realistic confirmed-vs-tentative scheduling collision."""
    return {
        "proposed": {
            "commitment_id": "proposal-1",
            "start_at": "2026-08-17T10:00:00+09:00",
            "end_at": "2026-08-17T11:00:00+09:00",
            "status": "confirmed",
        },
        "existing": [
            {
                "commitment_id": "existing-1",
                "start_at": "2026-08-17T10:30:00+09:00",
                "end_at": "2026-08-17T11:30:00+09:00",
                "status": "tentative",
            }
        ],
    }


def test_calendar_conflict_decision_requires_explicit_review_for_lower_priority_overlap() -> None:
    """Customers must receive a concrete next action instead of silent displacement."""
    response = client.post(
        "/api/calendar/conflicts/evaluate",
        json=_request_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "decision_code": "review_required",
        "reason_code": "lower_priority_conflict_requires_explicit_resolution",
        "conflicts": [
            {
                "commitment_id": "existing-1",
                "start_at": "2026-08-17T10:30:00+09:00",
                "end_at": "2026-08-17T11:30:00+09:00",
                "status": "tentative",
            }
        ],
        "recommended_action": (
            "Review and explicitly reschedule or accept the lower-priority conflict "
            "before proceeding."
        ),
        "policy_version": "status-weighted-v1",
    }


def test_calendar_conflict_decision_rejects_naive_timestamps() -> None:
    """The public API must reject calendar instants without an explicit offset."""
    payload = _request_payload()
    proposed = payload["proposed"]
    assert isinstance(proposed, dict)
    proposed["start_at"] = "2026-08-17T10:00:00"

    response = client.post("/api/calendar/conflicts/evaluate", json=payload)

    assert response.status_code == 422
    assert response.json()["error_code"] == "calendar_request_invalid"
    assert "detail" in response.json()


def test_calendar_conflict_decision_rejects_both_proposed_sources_with_stable_code() -> None:
    """Exactly-one proposed-source validation must use the application error envelope."""
    payload = _request_payload()
    payload["proposed_ics"] = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\n"
        "UID:duplicate-source\nDTSTART:20260817T100000Z\n"
        "DTEND:20260817T110000Z\nEND:VEVENT\nEND:VCALENDAR\n"
    )

    response = client.post("/api/calendar/conflicts/evaluate", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error_code": "calendar_proposed_source_missing",
        "detail": "Provide exactly one of proposed or proposed_ics",
    }


def test_calendar_conflict_decision_rejects_missing_proposed_sources_with_stable_code() -> None:
    """Neither proposed nor proposed_ics must use the same one-source error envelope."""
    response = client.post("/api/calendar/conflicts/evaluate", json={"existing": []})

    assert response.status_code == 422
    assert response.json() == {
        "error_code": "calendar_proposed_source_missing",
        "detail": "Provide exactly one of proposed or proposed_ics",
    }


def test_calendar_conflict_decision_rejects_invalid_interval_with_stable_code() -> None:
    """Policy validation must expose a stable code instead of raw implementation text."""
    payload = _request_payload()
    proposed = payload["proposed"]
    assert isinstance(proposed, dict)
    proposed["end_at"] = proposed["start_at"]

    response = client.post("/api/calendar/conflicts/evaluate", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error_code": "calendar_interval_invalid",
        "detail": "end_at must be later than start_at",
    }


def test_calendar_conflict_decision_requires_authentication() -> None:
    """The private conflict evaluator must reject a request with no authenticated session."""
    original_override = app.dependency_overrides.pop(get_auth_context, None)
    try:
        unauthenticated_client = TestClient(
            app,
            headers={"Origin": "http://localhost:3000"},
        )
        response = unauthenticated_client.post(
            "/api/calendar/conflicts/evaluate",
            json=_request_payload(),
        )
    finally:
        if original_override is not None:
            app.dependency_overrides[get_auth_context] = original_override

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_calendar_conflict_decision_bounds_existing_evidence_batch() -> None:
    """A caller cannot send an unbounded provider calendar snapshot to the endpoint."""
    payload = _request_payload()
    existing = payload["existing"]
    assert isinstance(existing, list)
    payload["existing"] = existing * 501

    response = client.post("/api/calendar/conflicts/evaluate", json=payload)

    assert response.status_code == 422


def test_calendar_conflict_decision_evaluates_known_ics_cancelled_pair() -> None:
    """iCalendar/ICS STATUS:CANCELLED overlap must allow the confirmed proposal."""
    fixture_dir = Path(__file__).parent / "fixtures" / "calendar"
    response = client.post(
        "/api/calendar/conflicts/evaluate",
        json={
            "proposed_ics": (fixture_dir / "proposed-confirmed-1000z.ics").read_text(
                encoding="utf-8"
            ),
            "existing_ics": (fixture_dir / "existing-cancelled-1000z.ics").read_text(
                encoding="utf-8"
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision_code"] == "available"
    assert body["reason_code"] == "no_overlapping_commitment"
    assert body["conflicts"] == []
    assert "Proceed" in body["recommended_action"]


def test_calendar_conflict_decision_evaluates_known_ics_confirmed_pair() -> None:
    """iCalendar/ICS STATUS:CONFIRMED overlap must block silent double-booking."""
    fixture_dir = Path(__file__).parent / "fixtures" / "calendar"
    response = client.post(
        "/api/calendar/conflicts/evaluate",
        json={
            "proposed_ics": (fixture_dir / "proposed-tentative-1000z.ics").read_text(
                encoding="utf-8"
            ),
            "existing_ics": (fixture_dir / "existing-confirmed-1000z.ics").read_text(
                encoding="utf-8"
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision_code"] == "blocked"
    assert body["reason_code"] == "equal_or_higher_priority_conflict"
    assert [item["commitment_id"] for item in body["conflicts"]] == [
        "existing-confirmed-1000z"
    ]
    assert "Choose another time" in body["recommended_action"]


def test_calendar_conflict_evaluator_fails_closed_when_proposed_source_missing() -> None:
    """A missing proposal must return 422 even if the request validator is bypassed."""
    request = CalendarConflictRequest.model_construct(
        proposed=None,
        existing=[],
        proposed_ics=None,
        existing_ics=None,
    )

    response = evaluate_calendar_conflict_request(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert json.loads(response.body) == {
        "error_code": "calendar_proposed_source_missing",
        "detail": "Provide exactly one of proposed or proposed_ics",
    }
