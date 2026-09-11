import json
import datetime

import pytest

from db.models import ProviderWritebackRetryItem
from services.provider_writeback_retry_service import (
    is_retryable_provider_writeback_failure,
    process_due_provider_writeback_retries,
    schedule_provider_writeback_retry,
)


class FakeRetrySession:
    def __init__(self, due_items=None):
        self.added_items: list[ProviderWritebackRetryItem] = []
        self.due_items = list(due_items or [])
        self.commit_count = 0

    def add(self, item):
        self.added_items.append(item)

    async def execute(self, query):
        return FakeRetryResult(self.due_items)

    async def commit(self):
        self.commit_count += 1


class FakeRetryResult:
    def __init__(self, due_items):
        self.due_items = due_items

    def scalars(self):
        return self

    def all(self):
        return self.due_items


def _retry_item(
    *,
    attempt_count: int = 1,
    retry_state: str = "pending",
    error_code: str = "runner_not_connected",
    due_at: datetime.datetime | None = None,
) -> ProviderWritebackRetryItem:
    now = due_at or datetime.datetime(2026, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)
    return ProviderWritebackRetryItem(
        retry_item_uid=f"provider_retry_test_{attempt_count}_{retry_state}",
        organization_id="org-acme",
        workspace_id="workspace-org-acme",
        source_uid="webdav_src_primary",
        command_action="write_webdav",
        command_payload_encrypted=json.dumps(
            {
                "action": "write_webdav",
                "source_id": "webdav_src_primary",
                "target_path": "/Naruon/Notes/task.md",
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        retry_state=retry_state,
        last_error_code=error_code,
        runner_request_uid="runner_req_original",
        attempt_count=attempt_count,
        next_retry_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_schedule_provider_writeback_retry_persists_scoped_item_metadata():
    db = FakeRetrySession()
    command = {
        "action": "write_webdav",
        "source_id": "webdav_src_primary",
        "target_path": "/Naruon/Notes/task.md",
        "if_match": "etag-before-write",
        "content": "sensitive generated provider payload",
    }

    retry_item_uid = await schedule_provider_writeback_retry(
        db,
        organization_id="org-acme",
        workspace_id="workspace-org-acme",
        command=command,
        error_code="runner_not_connected",
        runner_request_id="runner_req_1",
        retry_delay_seconds=60,
    )

    assert retry_item_uid.startswith("provider_retry_")
    assert db.commit_count == 1
    [retry_item] = db.added_items
    assert retry_item.organization_id == "org-acme"
    assert retry_item.workspace_id == "workspace-org-acme"
    assert retry_item.source_uid == "webdav_src_primary"
    assert retry_item.command_action == "write_webdav"
    assert retry_item.retry_state == "pending"
    assert retry_item.last_error_code == "runner_not_connected"
    assert retry_item.runner_request_uid == "runner_req_1"
    assert retry_item.attempt_count == 1
    assert retry_item.next_retry_at > retry_item.created_at
    assert json.loads(retry_item.command_payload_encrypted) == command
    metadata_text = "|".join(
        [
            retry_item.organization_id,
            retry_item.workspace_id,
            retry_item.source_uid or "",
            retry_item.command_action,
            retry_item.retry_state,
            retry_item.last_error_code,
            retry_item.runner_request_uid or "",
        ]
    )
    assert "sensitive generated provider payload" not in metadata_text


@pytest.mark.asyncio
async def test_schedule_provider_writeback_retry_ignores_non_retryable_failures():
    db = FakeRetrySession()

    retry_item_uid = await schedule_provider_writeback_retry(
        db,
        organization_id="org-acme",
        workspace_id="workspace-org-acme",
        command={"action": "write_caldav", "source_id": "calendar-primary"},
        error_code="adapter_not_configured",
        runner_request_id="runner_req_1",
    )

    assert retry_item_uid is None
    assert db.added_items == []
    assert db.commit_count == 0


def test_retryable_provider_writeback_failure_is_limited_to_writeback_transients():
    assert is_retryable_provider_writeback_failure(
        {"action": "write_caldav"}, "runner_response_timeout"
    )
    assert not is_retryable_provider_writeback_failure(
        {"action": "imap_fetch"}, "runner_response_timeout"
    )
    assert not is_retryable_provider_writeback_failure(
        {"action": "write_webdav"}, "adapter_not_configured"
    )


@pytest.mark.asyncio
async def test_process_due_provider_writeback_retries_marks_successful_retry():
    now = datetime.datetime(2026, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)
    retry_item = _retry_item(due_at=now)
    db = FakeRetrySession([retry_item])
    dispatched: list[dict[str, object]] = []

    async def dispatch_command(
        organization_id,
        workspace_id,
        command,
        *,
        timeout_seconds=30,
        schedule_retry=True,
    ):
        dispatched.append(
            {
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "command": command,
                "schedule_retry": schedule_retry,
            }
        )
        return {
            "status": "success",
            "provider_write_executed": True,
            "provider_status": 204,
        }

    summary = await process_due_provider_writeback_retries(
        db,
        dispatch_command,
        now=now,
        retry_delay_seconds=60,
        max_attempts=3,
    )

    assert summary == {
        "processed": 1,
        "succeeded": 1,
        "rescheduled": 0,
        "failed_exhausted": 0,
        "failed_permanent": 0,
    }
    assert retry_item.retry_state == "succeeded"
    assert retry_item.attempt_count == 2
    assert retry_item.updated_at == now
    assert db.commit_count == 1
    assert dispatched == [
        {
            "organization_id": "org-acme",
            "workspace_id": "workspace-org-acme",
            "command": {
                "action": "write_webdav",
                "source_id": "webdav_src_primary",
                "target_path": "/Naruon/Notes/task.md",
            },
            "schedule_retry": False,
        }
    ]


@pytest.mark.asyncio
async def test_process_due_provider_writeback_retries_reschedules_transient_failure():
    now = datetime.datetime(2026, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)
    retry_item = _retry_item(attempt_count=1, due_at=now)
    db = FakeRetrySession([retry_item])

    async def dispatch_command(*args, **kwargs):
        return {
            "status": "error",
            "error_code": "runner_response_timeout",
            "provider_write_executed": False,
        }

    summary = await process_due_provider_writeback_retries(
        db,
        dispatch_command,
        now=now,
        retry_delay_seconds=60,
        max_attempts=3,
    )

    assert summary["rescheduled"] == 1
    assert retry_item.retry_state == "pending"
    assert retry_item.attempt_count == 2
    assert retry_item.last_error_code == "runner_response_timeout"
    assert retry_item.next_retry_at == now + datetime.timedelta(seconds=60)
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_process_due_provider_writeback_retries_exhausts_before_dispatch():
    now = datetime.datetime(2026, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)
    retry_item = _retry_item(attempt_count=3, due_at=now)
    db = FakeRetrySession([retry_item])
    dispatched = False

    async def dispatch_command(*args, **kwargs):
        nonlocal dispatched
        dispatched = True
        return {
            "status": "success",
            "provider_write_executed": True,
        }

    summary = await process_due_provider_writeback_retries(
        db,
        dispatch_command,
        now=now,
        retry_delay_seconds=60,
        max_attempts=3,
    )

    assert summary["failed_exhausted"] == 1
    assert dispatched is False
    assert retry_item.retry_state == "failed_exhausted"
    assert retry_item.last_error_code == "retry_attempts_exhausted"
    assert retry_item.updated_at == now
    assert db.commit_count == 1
