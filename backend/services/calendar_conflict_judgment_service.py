"""Persist `evaluate_calendar_conflicts` decisions and human corrections to them."""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CalendarConflictCorrection, CalendarConflictJudgment
from services.calendar_conflict_policy import (
    CalendarConflictDecision,
    default_recommended_action,
)

ALLOWED_DECISION_CODES = frozenset({"available", "blocked", "review_required"})
ALLOWED_STATUS_CODES = frozenset({"proposed", "confirmed", "overridden", "dismissed"})
# Coherence contract between status_code and decision_code: an override must
# replace the decision (there is nothing else it could mean), while every
# other status must leave the existing decision untouched -- a "confirmed" or
# "dismissed" judgment whose decision silently changed would let the audit
# history and the current decision disagree.
_STATUS_CODES_REQUIRING_DECISION_CHANGE = frozenset({"overridden"})
_STATUS_CODES_FORBIDDING_DECISION_CHANGE = frozenset({"proposed", "confirmed", "dismissed"})
# A human correction that changes decision_code always replaces reason_code
# and recommended_action together, so a caller can never observe a decision
# paired with a reason/action that describes a different decision.
CORRECTED_DECISION_REASON_CODE = "corrected_by_human_review"
_MAX_JUDGMENTS_PER_LIST = 200


class CalendarConflictJudgmentNotFoundError(ValueError):
    """Raised when a judgment_uid does not resolve inside the caller's own scope."""


CORRECTION_INCOHERENT_ERROR_CODE = "calendar_correction_incoherent"


class CalendarConflictCorrectionIncoherentError(ValueError):
    """Raised when a correction's status_code and decision_code disagree.

    Carries a stable ``error_code`` (mirroring
    ``CalendarConflictUnsupportedValueError``'s pattern below) so a caller
    can map this to a deterministic response without parsing ``str(exc)``.
    """

    def __init__(self, message: str) -> None:
        """Create a coherence failure with the shared, stable error_code."""
        super().__init__(message)
        self.error_code = CORRECTION_INCOHERENT_ERROR_CODE


class CalendarConflictUnsupportedValueError(ValueError):
    """Stable typed failure for an unsupported status_code/decision_code value.

    Mirrors ``CalendarPolicyValidationError``'s pattern (a message-independent
    ``error_code`` attribute) so a route can map this to a deterministic
    response without parsing ``str(exc)``.
    """

    def __init__(self, error_code: str, message: str) -> None:
        """Create a validation failure with a stable public-facing code."""
        super().__init__(message)
        self.error_code = error_code


UNSUPPORTED_STATUS_CODE_ERROR_CODE = "calendar_correction_status_code_unsupported"
UNSUPPORTED_DECISION_CODE_ERROR_CODE = "calendar_correction_decision_code_unsupported"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _conflicts_to_json(decision: CalendarConflictDecision) -> list[dict[str, Any]]:
    return [
        {
            "commitment_id": conflict.commitment_id,
            "start_at": conflict.start_at.isoformat(),
            "end_at": conflict.end_at.isoformat(),
            "status": conflict.status,
        }
        for conflict in decision.conflicts
    ]


def _organization_filter(organization_id: str | None):
    if organization_id is not None:
        return CalendarConflictJudgment.organization_id == organization_id
    return CalendarConflictJudgment.organization_id.is_(None)


def validate_correction_coherence(*, status_code: str, decision_code: str | None) -> None:
    """Reject a status_code/decision_code combination that would leave the
    judgment's decision and its correction status describing different things.

    Shared by the API request model and apply_correction (for non-HTTP
    callers), so neither entry point can bypass the other's check.
    """
    if status_code in _STATUS_CODES_REQUIRING_DECISION_CHANGE and decision_code is None:
        raise CalendarConflictCorrectionIncoherentError(
            f"status_code={status_code!r} requires a replacement decision_code"
        )
    if status_code in _STATUS_CODES_FORBIDDING_DECISION_CHANGE and decision_code is not None:
        raise CalendarConflictCorrectionIncoherentError(
            f"status_code={status_code!r} must not change decision_code"
        )


async def create_judgment(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    proposed_commitment_id: str,
    source_thread_id: str | None,
    source_message_id: str | None,
    decision: CalendarConflictDecision,
) -> CalendarConflictJudgment:
    """Persist one deterministic conflict decision as a correctable judgment record."""
    judgment = CalendarConflictJudgment(
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        proposed_commitment_id=proposed_commitment_id,
        source_thread_id=source_thread_id,
        source_message_id=source_message_id,
        decision_code=decision.decision_code,
        reason_code=decision.reason_code,
        recommended_action=decision.recommended_action,
        policy_version=decision.policy_version,
        conflicts_json=_conflicts_to_json(decision),
    )
    db.add(judgment)
    await db.flush()
    return judgment


async def list_judgments(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    source_thread_id: str | None = None,
) -> list[CalendarConflictJudgment]:
    """List persisted judgments in the caller's own scope, newest first."""
    filters = [
        CalendarConflictJudgment.user_id == user_id,
        _organization_filter(organization_id),
        CalendarConflictJudgment.workspace_id == workspace_id,
    ]
    if source_thread_id is not None:
        filters.append(CalendarConflictJudgment.source_thread_id == source_thread_id)
    stmt = (
        select(CalendarConflictJudgment)
        .where(*filters)
        .order_by(
            CalendarConflictJudgment.created_at.desc(),
            CalendarConflictJudgment.calendar_conflict_judgment_id.desc(),
        )
        .limit(_MAX_JUDGMENTS_PER_LIST)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_judgment(
    db: AsyncSession,
    *,
    judgment_uid: str,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
) -> CalendarConflictJudgment:
    """Fetch one judgment by its opaque uid, regardless of list_judgments' bound.

    A judgment older than the most recent _MAX_JUDGMENTS_PER_LIST rows falls
    out of list_judgments' window, but it is never unreachable: the caller
    that received its judgment_uid (from the original create_judgment
    response, or from a correction) can always look it up directly here.
    """
    return await _get_scoped_judgment(
        db,
        judgment_uid=judgment_uid,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )


async def _get_scoped_judgment(
    db: AsyncSession,
    *,
    judgment_uid: str,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    for_update: bool = False,
) -> CalendarConflictJudgment:
    stmt = select(CalendarConflictJudgment).where(
        CalendarConflictJudgment.judgment_uid == judgment_uid,
        CalendarConflictJudgment.user_id == user_id,
        _organization_filter(organization_id),
        CalendarConflictJudgment.workspace_id == workspace_id,
    )
    if for_update:
        # Serialize concurrent corrections to the same judgment: without this,
        # two concurrent apply_correction calls can both read the same prior
        # state, both record a "before" snapshot that matches, and race on
        # which correction's decision/status the row ends up with.
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    judgment = result.scalar_one_or_none()
    if judgment is None:
        raise CalendarConflictJudgmentNotFoundError(
            "Calendar conflict judgment is outside the requested scope"
        )
    return judgment


def _judgment_snapshot(judgment: CalendarConflictJudgment) -> dict[str, Any]:
    return {
        "decision_code": judgment.decision_code,
        "reason_code": judgment.reason_code,
        "recommended_action": judgment.recommended_action,
        "status_code": judgment.status_code,
    }


async def apply_correction(
    db: AsyncSession,
    *,
    judgment_uid: str,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    actor_user_id: str,
    correction_action: str,
    decision_code: str | None,
    status_code: str,
    rationale: str | None,
) -> CalendarConflictCorrection:
    """Record a human override/confirmation of a persisted conflict judgment."""
    if status_code not in ALLOWED_STATUS_CODES:
        raise CalendarConflictUnsupportedValueError(
            UNSUPPORTED_STATUS_CODE_ERROR_CODE,
            f"Unsupported calendar conflict status_code: {status_code!r}",
        )
    if decision_code is not None and decision_code not in ALLOWED_DECISION_CODES:
        raise CalendarConflictUnsupportedValueError(
            UNSUPPORTED_DECISION_CODE_ERROR_CODE,
            f"Unsupported calendar conflict decision_code: {decision_code!r}",
        )
    validate_correction_coherence(status_code=status_code, decision_code=decision_code)

    judgment = await _get_scoped_judgment(
        db,
        judgment_uid=judgment_uid,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        for_update=True,
    )
    before_json = _judgment_snapshot(judgment)
    if decision_code is not None and decision_code != judgment.decision_code:
        # Replace reason_code/recommended_action together with decision_code
        # so a later read can never pair a corrected decision with the
        # original decision's now-stale reason and instruction. The original
        # values are never lost -- they are exactly what before_json above
        # already captured. recommended_action is restated from the policy's
        # own canonical mapping, never from rationale: rationale explains why
        # a human overrode the decision, it is not forward-looking scheduling
        # guidance, and the two must never be conflated.
        #
        # Gated on an actual change (not just decision_code is not None): an
        # "override" that repeats the judgment's current decision is a no-op
        # on the decision itself, and must not wipe out the original,
        # still-accurate reason_code/recommended_action for no real reason.
        judgment.decision_code = decision_code
        judgment.reason_code = CORRECTED_DECISION_REASON_CODE
        judgment.recommended_action = default_recommended_action(decision_code)
    judgment.status_code = status_code
    judgment.updated_at = _utcnow()
    after_json = _judgment_snapshot(judgment)

    correction = CalendarConflictCorrection(
        judgment=judgment,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        correction_action=correction_action,
        before_json=before_json,
        after_json=after_json,
        correction_rationale=rationale,
    )
    db.add(correction)
    await db.flush()
    return correction
