import datetime
from contextlib import nullcontext
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Email, TenantConfig, TicketTask
from services.reply_tracking_service import check_missing_replies
from services.text_safety import contains_html_markup
from services.threading_service import normalize_message_id

REPLY_SLA_SOURCE_TYPE = "reply_sla"
REPLY_SLA_MAX_BATCH_ATTEMPTS = 3


class ReplySlaTaskConflict(Exception):
    pass


@dataclass(frozen=True)
class ReplySlaEscalatedTask:
    task: TicketTask
    source_email_id: str | None


@dataclass(frozen=True)
class ReplySlaEscalationResult:
    evaluated: int
    created: int
    overdue_hours: int
    tasks: list[ReplySlaEscalatedTask]


def canonical_reply_sla_thread_key(email: Email) -> str:
    return (
        normalize_message_id(email.thread_id)
        or normalize_message_id(email.message_id)
        or email.message_id
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


async def _fetch_existing_tasks_by_email(
    db: AsyncSession, user_id: str, organization_id: str | None, email_ids: list[int]
) -> dict[int, TicketTask]:
    result = await db.execute(
        select(TicketTask)
        .where(
            TicketTask.user_id == user_id,
            TicketTask.organization_id == organization_id,
            TicketTask.related_email_id.in_(email_ids),
            TicketTask.source_type == REPLY_SLA_SOURCE_TYPE,
        )
        .order_by(TicketTask.updated_at.desc())
    )
    tasks_by_email = {}
    for task in result.scalars().all():
        if task.related_email_id not in tasks_by_email:
            tasks_by_email[task.related_email_id] = task
    return tasks_by_email


def _update_task_for_escalation(
    task: TicketTask, email: Email, now: datetime.datetime
) -> None:
    if task.status != "done":
        task.title = _reply_sla_task_title(email)
        task.status = "blocked"
        task.priority = "urgent"
        task.related_thread_id = canonical_reply_sla_thread_key(email)
        task.updated_at = now


def _create_task_for_escalation(
    user_id: str, organization_id: str | None, email: Email
) -> TicketTask:
    return TicketTask(
        user_id=user_id,
        organization_id=organization_id,
        title=_reply_sla_task_title(email),
        status="blocked",
        priority="urgent",
        source_type=REPLY_SLA_SOURCE_TYPE,
        related_email_id=email.id,
        related_thread_id=canonical_reply_sla_thread_key(email),
    )


async def _refresh_escalated_tasks(
    db: AsyncSession,
    user_id: str,
    organization_id: str | None,
    email_ids: list[int],
    escalated_tasks: list[tuple[TicketTask, str | None]],
) -> None:
    refreshed_tasks_by_email = await _fetch_existing_tasks_by_email(
        db, user_id, organization_id, email_ids
    )
    for i, (task, message_id) in enumerate(escalated_tasks):
        refreshed_task = refreshed_tasks_by_email.get(task.related_email_id)
        if refreshed_task is not None:
            escalated_tasks[i] = (refreshed_task, message_id)


async def _process_bulk_escalation(
    db: AsyncSession,
    user_id: str,
    organization_id: str | None,
    overdue_replies: list[Email],
    now: datetime.datetime,
) -> tuple[int, list[tuple[TicketTask, str | None]]]:
    email_ids = [email.id for email in overdue_replies]
    existing_tasks_by_email = await _fetch_existing_tasks_by_email(
        db, user_id, organization_id, email_ids
    )

    created_count = 0
    escalated_tasks: list[tuple[TicketTask, str | None]] = []

    for email in overdue_replies:
        if email.id in existing_tasks_by_email:
            task = existing_tasks_by_email[email.id]
            _update_task_for_escalation(task, email, now)
            escalated_tasks.append((task, email.message_id))
        else:
            task = _create_task_for_escalation(user_id, organization_id, email)
            db.add(task)
            created_count += 1
            escalated_tasks.append((task, email.message_id))

    if created_count > 0 or any(
        email.id in existing_tasks_by_email for email in overdue_replies
    ):
        await db.commit()

        if created_count > 0:
            await _refresh_escalated_tasks(
                db, user_id, organization_id, email_ids, escalated_tasks
            )

    return created_count, escalated_tasks


async def _process_fallback_escalation(
    db: AsyncSession,
    user_id: str,
    organization_id: str | None,
    overdue_replies: list[Email],
    now: datetime.datetime,
) -> tuple[int, list[tuple[TicketTask, str | None]]]:
    """Bound contention recovery without committing a partially reconciled batch."""
    email_ids = [email.id for email in overdue_replies]
    existing_tasks_by_email = await _fetch_existing_tasks_by_email(
        db, user_id, organization_id, email_ids
    )
    entries: list[tuple[Email, TicketTask]] = []
    pending: list[tuple[int, Email, TicketTask]] = []

    for email in overdue_replies:
        task = existing_tasks_by_email.get(email.id)
        if task is None:
            task = _create_task_for_escalation(user_id, organization_id, email)
            pending.append((len(entries), email, task))
        else:
            _update_task_for_escalation(task, email, now)
        entries.append((email, task))

    created_count = 0
    for _ in range(REPLY_SLA_MAX_BATCH_ATTEMPTS):
        if not pending:
            break
        savepoint_started = False
        try:
            async with db.begin_nested():
                savepoint_started = True
                for _, _, task in pending:
                    db.add(task)
                await db.flush()
        except IntegrityError:
            if not savepoint_started:
                # begin_nested() flushes existing dirty work before establishing
                # the savepoint; that failure needs an outer rollback first.
                await db.rollback()
                raise
            # SAVEPOINT rollback already detaches its pending inserts. Reconcile
            # winners in one read; expunging those transient objects is invalid.
            with getattr(db, "no_autoflush", nullcontext()):
                winners = await _fetch_existing_tasks_by_email(
                    db,
                    user_id,
                    organization_id,
                    [email.id for _, email, _ in pending],
                )
            remaining = []
            for index, email, task in pending:
                winner = winners.get(email.id)
                if winner is None:
                    remaining.append((index, email, task))
                else:
                    _update_task_for_escalation(winner, email, now)
                    entries[index] = (email, winner)
            if len(remaining) == len(pending):
                # No visible duplicate explains this failure (e.g. FK or NOT
                # NULL). Preserve the database error instead of retrying rows.
                await db.rollback()
                raise
            pending = remaining
        else:
            created_count = len(pending)
            pending = []
            break

    if pending:
        # Do not turn sustained contention into N savepoints while retaining
        # earlier write locks. The API already maps this domain error to 409.
        await db.rollback()
        raise ReplySlaTaskConflict(
            "reply_sla_task_conflict: batch retry budget exhausted"
        )

    escalated_tasks = [(task, email.message_id) for email, task in entries]
    if created_count > 0 or any(task.status != "done" for task, _ in escalated_tasks):
        await db.commit()
        await _refresh_escalated_tasks(
            db, user_id, organization_id, email_ids, escalated_tasks
        )
    return created_count, escalated_tasks


async def _reload_overdue_replies(
    db: AsyncSession,
    user_id: str,
    organization_id: str | None,
    email_ids: list[int],
) -> list[Email]:
    """Reload expired inputs in one owner-scoped query, preserving their order."""
    result = await db.execute(
        select(Email)
        .where(
            Email.user_id == user_id,
            Email.organization_id == organization_id,
            Email.id.in_(email_ids),
        )
        .execution_options(populate_existing=True)
    )
    by_email_id = {email.id: email for email in result.scalars().all()}
    if any(email_id not in by_email_id for email_id in email_ids):
        await db.rollback()
        raise ReplySlaTaskConflict(
            "reply_sla_task_conflict: source email no longer available"
        )
    return [by_email_id[email_id] for email_id in email_ids]


async def create_reply_sla_escalation_tasks(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
    overdue_hours: int,
    limit: int,
    tenant_config: TenantConfig | None = None,
) -> ReplySlaEscalationResult:
    pending_replies = await check_missing_replies(
        db, user_id, organization_id, tenant_config=tenant_config
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    overdue_cutoff = now - datetime.timedelta(hours=overdue_hours)
    overdue_replies = sorted(
        [
            email
            for email in pending_replies
            if _email_date_utc(email) <= overdue_cutoff
        ],
        key=_email_date_utc,
    )[:limit]

    if not overdue_replies:
        return ReplySlaEscalationResult(
            evaluated=len(pending_replies),
            created=0,
            overdue_hours=overdue_hours,
            tasks=[],
        )

    # rollback() expires even primary keys, regardless of expire_on_commit.
    email_ids = [email.id for email in overdue_replies]
    try:
        created_count, escalated_tasks = await _process_bulk_escalation(
            db, user_id, organization_id, overdue_replies, now
        )
    except IntegrityError:
        await db.rollback()
        overdue_replies = await _reload_overdue_replies(
            db, user_id, organization_id, email_ids
        )
        created_count, escalated_tasks = await _process_fallback_escalation(
            db, user_id, organization_id, overdue_replies, now
        )

    return ReplySlaEscalationResult(
        evaluated=len(pending_replies),
        created=created_count,
        overdue_hours=overdue_hours,
        tasks=[
            ReplySlaEscalatedTask(task=task, source_email_id=source_email_id)
            for task, source_email_id in escalated_tasks
        ],
    )
