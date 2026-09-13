import datetime
from contextlib import nullcontext
from dataclasses import dataclass

from sqlalchemy import inspect as sqlalchemy_inspect
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
    """Report a concurrent source-task conflict that cannot be reconciled."""

    def __init__(self, error_code: str, message: str) -> None:
        """Create a conflict with stable classification independent of prose."""
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class ReplySlaEscalatedTask:
    """Pair a persisted task with its original external email reference."""

    task: TicketTask
    source_email_id: str | None


@dataclass(frozen=True)
class ReplySlaEscalationResult:
    """Summarize evaluated mail and created or updated follow-up tasks."""

    evaluated: int
    created: int
    overdue_hours: int
    tasks: list[ReplySlaEscalatedTask]


def canonical_reply_sla_thread_key(email: Email) -> str:
    """Prefer the normalized thread reference, then the message reference."""
    return (
        normalize_message_id(email.thread_id)
        or normalize_message_id(email.message_id)
        or email.message_id
    )


def _safe_email_subject(subject: str | None) -> str:
    """Keep a bounded plain-text title without active email markup."""
    trimmed = (subject or "제목 없음").replace("\x00", " ").strip()
    if not trimmed or contains_html_markup(trimmed):
        return "제목 정리 필요"
    return " ".join(trimmed.split())[:120]


def _reply_sla_task_title(email: Email) -> str:
    """Build the existing follow-up label from a sanitized mail subject."""
    return f"미답변 팔로업: {_safe_email_subject(email.subject)}"


def _email_date_utc(email: Email) -> datetime.datetime:
    """Interpret legacy naive timestamps as UTC for deadline comparisons."""
    message_date = email.date
    if message_date.tzinfo is None:
        return message_date.replace(tzinfo=datetime.timezone.utc)
    return message_date


async def _fetch_existing_tasks_by_email(
    db: AsyncSession, user_id: str, organization_id: str | None, email_ids: list[int]
) -> dict[int, TicketTask]:
    """Select the most recently updated owner-scoped task per source email."""
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
    """Escalate pending work without reopening a completed task."""
    if task.status != "done":
        task.title = _reply_sla_task_title(email)
        task.status = "blocked"
        task.priority = "urgent"
        task.related_thread_id = canonical_reply_sla_thread_key(email)
        task.updated_at = now


def _create_task_for_escalation(
    user_id: str, organization_id: str | None, email: Email
) -> TicketTask:
    """Create a source-linked urgent task using the established identity contract."""
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
    """Replace task references with persisted owner-scoped rows when present."""
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
    """Create or update overdue follow-ups in the ordinary single commit path."""
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


def _is_non_unique_constraint_failure(error: IntegrityError) -> bool:
    """Classify known driver constraint codes without parsing localized prose."""
    sqlstate = getattr(error.orig, "sqlstate", None) or getattr(
        error.orig, "pgcode", None
    )
    if sqlstate is not None:
        return sqlstate != "23505"
    sqlite_errorname = getattr(error.orig, "sqlite_errorname", None)
    if sqlite_errorname is not None:
        return sqlite_errorname not in {
            "SQLITE_CONSTRAINT_UNIQUE",
            "SQLITE_CONSTRAINT_PRIMARYKEY",
        }
    # Untyped IntegrityError retains the established conflict contract. Do not
    # infer a constraint category from provider- or locale-specific text.
    return False


async def _process_fallback_escalation(
    db: AsyncSession,
    user_id: str,
    organization_id: str | None,
    overdue_replies: list[Email],
    now: datetime.datetime,
) -> tuple[int, list[tuple[TicketTask, str | None]]]:
    """Bound contention recovery without per-row SAVEPOINT retries."""
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
        flush_started = False
        try:
            async with db.begin_nested():
                savepoint_started = True
                for _, _, task in pending:
                    db.add(task)
                flush_started = True
                await db.flush()
        except IntegrityError as error:
            if not savepoint_started:
                # AsyncSession.begin_nested() flushes dirty state before the
                # SAVEPOINT exists. A pre-savepoint failure poisons the outer
                # transaction and must not be treated as a uniqueness race.
                await db.rollback()
                raise
            if _is_non_unique_constraint_failure(error):
                await db.rollback()
                raise

            # SAVEPOINT rollback already detaches failed inserts. Read visible
            # winners in one owner-scoped query and retry only the remainder.
            with getattr(db, "no_autoflush", nullcontext()):
                winners = await _fetch_existing_tasks_by_email(
                    db,
                    user_id,
                    organization_id,
                    [email.id for _, email, _ in pending],
                )
            remaining: list[tuple[int, Email, TicketTask]] = []
            for index, email, task in pending:
                winner = winners.get(email.id)
                if winner is None:
                    remaining.append((index, email, task))
                    continue
                _update_task_for_escalation(winner, email, now)
                entries[index] = (email, winner)

            # Some scripted compatibility sessions surface a simulated unique
            # race from add() rather than flush(). A real AsyncSession does not,
            # but preserving that harness is useful: reconcile a visible winner
            # once, and fail closed if the synthetic conflict has no winner.
            if not flush_started and len(remaining) == len(pending):
                await db.rollback()
                raise ReplySlaTaskConflict(
                    "reply_sla_task_conflict",
                    "no visible duplicate winner",
                ) from error
            pending = remaining
        else:
            created_count = len(pending)
            pending = []
            break

    if pending:
        # Sustained contention is bounded by batch attempts. Rolling back here
        # also reverts updates to pre-existing tasks, so no partial write leaks.
        await db.rollback()
        raise ReplySlaTaskConflict(
            "reply_sla_batch_retry_exhausted",
            "batch retry budget exhausted",
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
    workspace_id: str,
    email_ids: list[int],
) -> list[Email]:
    """Reload rollback-expired source mail in one workspace-scoped query."""
    result = await db.execute(
        select(Email)
        .where(
            Email.user_id == user_id,
            Email.organization_id == organization_id,
            Email.workspace_id == workspace_id,
            Email.id.in_(email_ids),
        )
        .execution_options(populate_existing=True)
    )
    by_email_id = {email.id: email for email in result.scalars().all()}
    if any(email_id not in by_email_id for email_id in email_ids):
        await db.rollback()
        raise ReplySlaTaskConflict(
            "reply_sla_source_email_unavailable",
            "source email no longer available in the authorized workspace",
        )
    return [by_email_id[email_id] for email_id in email_ids]


def _rollback_expired_any_source(overdue_replies: list[Email]) -> bool:
    """Detect whether SQLAlchemy rollback made a source unsafe to read directly."""
    return any(
        sqlalchemy_inspect(email).expired or sqlalchemy_inspect(email).detached
        for email in overdue_replies
    )


async def create_reply_sla_escalation_tasks(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    overdue_hours: int,
    limit: int,
    tenant_config: TenantConfig | None = None,
) -> ReplySlaEscalationResult:
    """Persist bounded follow-ups selected by authoritative scoped reply tracking."""
    pending_replies = await check_missing_replies(
        db,
        user_id,
        organization_id,
        workspace_id,
        tenant_config=tenant_config,
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

    # Keep primitive IDs before the transaction can expire mapped source rows.
    email_ids = [email.id for email in overdue_replies]
    try:
        created_count, escalated_tasks = await _process_bulk_escalation(
            db, user_id, organization_id, overdue_replies, now
        )
    except IntegrityError as error:
        await db.rollback()
        if _is_non_unique_constraint_failure(error):
            raise
        # Real SQLAlchemy rollback expires mapped source rows. Scripted unit
        # sessions that do not model expiration retain their in-memory fixtures;
        # production takes the workspace-scoped one-query reload path.
        if _rollback_expired_any_source(overdue_replies):
            overdue_replies = await _reload_overdue_replies(
                db,
                user_id,
                organization_id,
                workspace_id,
                email_ids,
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
