import datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import AuthContext, get_auth_context
from api.emails import canonical_thread_key
from db.models import Email, TicketTask
from db.session import get_db
from services.reply_sla_escalation_service import (
    ReplySlaEscalationResult,
    ReplySlaTaskConflict,
    create_reply_sla_escalation_tasks,
)
from services.text_safety import contains_html_markup

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


TaskStatus = Literal["open", "in_progress", "blocked", "done"]
TaskPriority = Literal["low", "normal", "high", "urgent"]


class CreateTasksFromEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_email_id: str
    thread_id: str | None = None
    items: list[str]


class TicketTaskResponse(BaseModel):
    id: str
    title: str
    status: TaskStatus
    priority: TaskPriority
    source_type: str
    source_email_id: str | None
    related_thread_id: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class CreateTasksFromEmailResponse(BaseModel):
    created: int
    tasks: list[TicketTaskResponse]


class ReplySlaEscalationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overdue_hours: int = Field(default=48, ge=1, le=720)
    limit: int = Field(default=10, ge=1, le=50)


class ReplySlaPolicyResponse(BaseModel):
    overdue_hours: int


class ReplySlaEscalationResponse(BaseModel):
    evaluated: int
    created: int
    policy: ReplySlaPolicyResponse
    tasks: list[TicketTaskResponse]


class UpdateTicketTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    priority: TaskPriority | None = None


def _normalize_execution_items(items: list[str]) -> list[str]:
    normalized = []
    for item in items:
        trimmed = item.replace("\x00", "").strip()
        if trimmed:
            if contains_html_markup(trimmed):
                raise HTTPException(
                    status_code=422, detail="Execution items must be plain text"
                )
            normalized.append(trimmed)
    return normalized


def _email_matches_auth(email: Email, auth_context: AuthContext) -> bool:
    return (
        email.user_id == auth_context.user_id
        and email.organization_id == auth_context.organization_id
    )


def _safe_email_subject(subject: str | None) -> str:
    trimmed = (subject or "제목 없음").replace("\x00", " ").strip()
    if not trimmed or contains_html_markup(trimmed):
        return "제목 정리 필요"
    return " ".join(trimmed.split())[:120]


def _reply_sla_task_title(email: Email) -> str:
    return f"미답변 팔로업: {_safe_email_subject(email.subject)}"


def _email_date_utc(email: Email) -> datetime.datetime:
    message_date = email.date
    if message_date.tzinfo is None:
        return message_date.replace(tzinfo=datetime.timezone.utc)
    return message_date


def _task_response(task: TicketTask, source_email_id: str | None) -> TicketTaskResponse:
    scoped_thread_id = task.related_thread_id if source_email_id is not None else None
    return TicketTaskResponse(
        id=task.task_uid,
        title=task.title,
        status=cast(TaskStatus, task.status),
        priority=cast(TaskPriority, task.priority),
        source_type=task.source_type,
        source_email_id=source_email_id,
        related_thread_id=scoped_thread_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _reply_sla_response(
    escalation_result: ReplySlaEscalationResult,
) -> ReplySlaEscalationResponse:
    return ReplySlaEscalationResponse(
        evaluated=escalation_result.evaluated,
        created=escalation_result.created,
        policy=ReplySlaPolicyResponse(overdue_hours=escalation_result.overdue_hours),
        tasks=[
            _task_response(entry.task, entry.source_email_id)
            for entry in escalation_result.tasks
        ],
    )


@router.post("/reply-sla-escalations", response_model=ReplySlaEscalationResponse)
async def create_reply_sla_escalations(
    request: ReplySlaEscalationRequest,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ReplySlaEscalationResponse:
    try:
        escalation_result = await create_reply_sla_escalation_tasks(
            db,
            user_id=auth_context.user_id,
            organization_id=auth_context.organization_id,
            workspace_id=auth_context.workspace_id,
            overdue_hours=request.overdue_hours,
            limit=request.limit,
        )
    except ReplySlaTaskConflict as conflict_error:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": conflict_error.error_code,
                "message": "Overdue reply follow-up task conflict",
            },
        ) from None
    return _reply_sla_response(escalation_result)


def _build_task_query(auth_context: AuthContext):
    return (
        select(TicketTask, Email.message_id)
        .outerjoin(
            Email,
            and_(
                TicketTask.related_email_id == Email.id,
                Email.user_id == auth_context.user_id,
                Email.organization_id == auth_context.organization_id,
                Email.workspace_id == auth_context.workspace_id,
            ),
        )
        .where(
            TicketTask.user_id == auth_context.user_id,
            TicketTask.organization_id == auth_context.organization_id,
            or_(
                TicketTask.related_email_id.is_(None),
                Email.id.is_not(None),
            ),
        )
    )


@router.get("", response_model=list[TicketTaskResponse])
async def list_ticket_tasks(
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[TicketTaskResponse]:
    result = await db.execute(
        _build_task_query(auth_context).order_by(TicketTask.updated_at.desc())
    )
    return [
        _task_response(task, source_email_id) for task, source_email_id in result.all()
    ]


@router.patch("/{task_uid}", response_model=TicketTaskResponse)
async def update_ticket_task(
    task_uid: str,
    request: UpdateTicketTaskRequest,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
) -> TicketTaskResponse:
    if request.status is None and request.priority is None:
        raise HTTPException(
            status_code=422, detail="At least one ticket field is required"
        )

    result = await db.execute(
        _build_task_query(auth_context).where(TicketTask.task_uid == task_uid)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    task, source_email_id = row
    if request.status is not None:
        task.status = request.status
    if request.priority is not None:
        task.priority = request.priority
    task.updated_at = datetime.datetime.now(datetime.timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _task_response(task, source_email_id)


def _validate_execution_items(items: list[str]) -> list[str]:
    normalized_items = _normalize_execution_items(items)
    if not normalized_items:
        raise HTTPException(
            status_code=422, detail="At least one execution item is required"
        )
    if len(normalized_items) > 50:
        raise HTTPException(status_code=422, detail="Too many execution items")
    return normalized_items


async def _fetch_source_email(
    db: AsyncSession, request: CreateTasksFromEmailRequest, auth_context: AuthContext
) -> Email:
    email_result = await db.execute(
        select(Email).where(
            Email.message_id == request.source_email_id,
            Email.user_id == auth_context.user_id,
            Email.organization_id == auth_context.organization_id,
            Email.workspace_id == auth_context.workspace_id,
        )
    )
    email = email_result.scalar_one_or_none()
    if email is None or not _email_matches_auth(email, auth_context):
        raise HTTPException(status_code=404, detail="Source email not found")
    return email


@router.post("/from-email", response_model=CreateTasksFromEmailResponse)
async def create_tasks_from_email(
    request: CreateTasksFromEmailRequest,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
) -> CreateTasksFromEmailResponse:
    items = _validate_execution_items(request.items)
    email = await _fetch_source_email(db, request, auth_context)

    thread_id = canonical_thread_key(email) or request.thread_id
    tasks = [
        TicketTask(
            user_id=auth_context.user_id,
            organization_id=auth_context.organization_id,
            title=item,
            status="open",
            priority="normal",
            source_type="email",
            related_email_id=email.id,
            related_thread_id=thread_id,
        )
        for item in items
    ]
    for task in tasks:
        db.add(task)

    await db.commit()

    return CreateTasksFromEmailResponse(
        created=len(tasks),
        tasks=[_task_response(task, email.message_id) for task in tasks],
    )
