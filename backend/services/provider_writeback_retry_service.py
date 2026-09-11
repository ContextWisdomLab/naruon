import asyncio
import datetime
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ProviderWritebackRetryItem
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

WRITEBACK_COMMAND_ACTIONS = frozenset({"write_caldav", "write_webdav"})
RETRYABLE_PROVIDER_WRITEBACK_ERRORS = frozenset(
    {
        "runner_not_connected",
        "runner_response_timeout",
        "runner_dispatch_failed",
    }
)
PROVIDER_WRITEBACK_RETRY_SUMMARY_KEYS = (
    "processed",
    "succeeded",
    "rescheduled",
    "failed_exhausted",
    "failed_permanent",
)

ProviderWritebackDispatch = Callable[..., Awaitable[dict[str, Any]]]


class ProviderWritebackRetryWorker:
    def __init__(
        self,
        dispatch_command: ProviderWritebackDispatch,
        *,
        interval_seconds: int = 60,
        batch_limit: int = 25,
        max_attempts: int = 3,
    ):
        self.dispatch_command = dispatch_command
        self.interval_seconds = interval_seconds
        self.batch_limit = batch_limit
        self.max_attempts = max_attempts
        self._task = None
        self._is_running = False

    async def start(self):
        if self._is_running:
            logger.warning("ProviderWritebackRetryWorker is already running.")
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ProviderWritebackRetryWorker started.")

    async def stop(self):
        if not self._is_running:
            return
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug(
                    "ProviderWritebackRetryWorker cancellation acknowledged during shutdown."
                )
        logger.info("ProviderWritebackRetryWorker stopped.")

    async def _run_loop(self):
        while self._is_running:
            try:
                await self._sync()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Error in ProviderWritebackRetryWorker loop", exc_info=True)

            if self._is_running:
                try:
                    await asyncio.sleep(self.interval_seconds)
                except asyncio.CancelledError:
                    break

    async def _sync(self):
        async with AsyncSessionLocal() as db:
            return await process_due_provider_writeback_retries(
                db,
                self.dispatch_command,
                batch_limit=self.batch_limit,
                retry_delay_seconds=self.interval_seconds,
                max_attempts=self.max_attempts,
            )


def is_retryable_provider_writeback_failure(
    command: dict[str, Any],
    error_code: str | None,
) -> bool:
    action = command.get("action")
    return (
        isinstance(action, str)
        and action in WRITEBACK_COMMAND_ACTIONS
        and error_code in RETRYABLE_PROVIDER_WRITEBACK_ERRORS
    )


async def schedule_provider_writeback_retry(
    db: AsyncSession,
    *,
    organization_id: str,
    workspace_id: str,
    command: dict[str, Any],
    error_code: str,
    runner_request_id: str | None,
    retry_delay_seconds: int = 300,
) -> str | None:
    if not is_retryable_provider_writeback_failure(command, error_code):
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    retry_item = ProviderWritebackRetryItem(
        retry_item_uid=f"provider_retry_{uuid.uuid4().hex}",
        organization_id=organization_id,
        workspace_id=workspace_id,
        source_uid=_source_uid(command),
        command_action=str(command["action"]),
        command_payload_encrypted=_serialize_command(command),
        retry_state="pending",
        last_error_code=error_code,
        runner_request_uid=runner_request_id,
        attempt_count=1,
        next_retry_at=now + datetime.timedelta(seconds=retry_delay_seconds),
        created_at=now,
        updated_at=now,
    )
    db.add(retry_item)
    await db.commit()
    return retry_item.retry_item_uid


async def schedule_provider_writeback_retry_safely(
    *,
    organization_id: str,
    workspace_id: str,
    command: dict[str, Any],
    error_code: str,
    runner_request_id: str | None,
) -> str | None:
    try:
        async with AsyncSessionLocal() as db:
            return await schedule_provider_writeback_retry(
                db,
                organization_id=organization_id,
                workspace_id=workspace_id,
                command=command,
                error_code=error_code,
                runner_request_id=runner_request_id,
            )
    except Exception:
        logger.debug("Provider writeback retry scheduling skipped", exc_info=True)
        return None


async def process_due_provider_writeback_retries(
    db: AsyncSession,
    dispatch_command: ProviderWritebackDispatch,
    *,
    now: datetime.datetime | None = None,
    batch_limit: int = 25,
    retry_delay_seconds: int = 300,
    max_attempts: int = 3,
) -> dict[str, int]:
    current_time = now or datetime.datetime.now(datetime.timezone.utc)
    result = await db.execute(
        select(ProviderWritebackRetryItem)
        .where(
            ProviderWritebackRetryItem.retry_state == "pending",
            ProviderWritebackRetryItem.next_retry_at <= current_time,
        )
        .order_by(ProviderWritebackRetryItem.next_retry_at.asc())
        .limit(batch_limit)
    )
    retry_items = list(result.scalars().all())
    summary = {key: 0 for key in PROVIDER_WRITEBACK_RETRY_SUMMARY_KEYS}
    if not retry_items:
        return summary

    for retry_item in retry_items:
        summary["processed"] += 1
        if retry_item.attempt_count >= max_attempts:
            _mark_retry_exhausted(retry_item, current_time)
            summary["failed_exhausted"] += 1
            continue

        command = _deserialize_retry_command(retry_item)
        if command is None:
            _mark_retry_permanent_failure(
                retry_item,
                current_time,
                "invalid_retry_payload",
            )
            summary["failed_permanent"] += 1
            continue

        retry_item.attempt_count += 1
        retry_item.retry_state = "running"
        retry_item.updated_at = current_time
        dispatch_result = await dispatch_command(
            retry_item.organization_id,
            retry_item.workspace_id,
            command,
            schedule_retry=False,
        )
        if dispatch_result.get("provider_write_executed") is True:
            retry_item.retry_state = "succeeded"
            retry_item.updated_at = current_time
            summary["succeeded"] += 1
            continue

        error_code = _dispatch_error_code(dispatch_result)
        retry_item.last_error_code = error_code
        retry_item.updated_at = current_time
        if is_retryable_provider_writeback_failure(command, error_code):
            if retry_item.attempt_count >= max_attempts:
                _mark_retry_exhausted(retry_item, current_time, error_code)
                summary["failed_exhausted"] += 1
            else:
                retry_item.retry_state = "pending"
                retry_item.next_retry_at = current_time + datetime.timedelta(
                    seconds=_retry_delay_seconds(
                        retry_delay_seconds,
                        retry_item.attempt_count,
                    )
                )
                summary["rescheduled"] += 1
        else:
            _mark_retry_permanent_failure(retry_item, current_time, error_code)
            summary["failed_permanent"] += 1

    await db.commit()
    return summary


def _deserialize_retry_command(
    retry_item: ProviderWritebackRetryItem,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(retry_item.command_payload_encrypted)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _dispatch_error_code(dispatch_result: dict[str, Any]) -> str:
    error_code = dispatch_result.get("error_code") or dispatch_result.get("error")
    if isinstance(error_code, str) and error_code.strip():
        return error_code.strip()
    return "provider_writeback_retry_failed"


def _retry_delay_seconds(base_delay_seconds: int, attempt_count: int) -> int:
    return base_delay_seconds * (2 ** max(attempt_count - 2, 0))


def _mark_retry_exhausted(
    retry_item: ProviderWritebackRetryItem,
    now: datetime.datetime,
    error_code: str = "retry_attempts_exhausted",
) -> None:
    retry_item.retry_state = "failed_exhausted"
    retry_item.last_error_code = error_code
    retry_item.updated_at = now


def _mark_retry_permanent_failure(
    retry_item: ProviderWritebackRetryItem,
    now: datetime.datetime,
    error_code: str,
) -> None:
    retry_item.retry_state = "failed_permanent"
    retry_item.last_error_code = error_code
    retry_item.updated_at = now


def _source_uid(command: dict[str, Any]) -> str | None:
    for key in ("source_id", "account"):
        value = command.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _serialize_command(command: dict[str, Any]) -> str:
    return json.dumps(
        command,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
