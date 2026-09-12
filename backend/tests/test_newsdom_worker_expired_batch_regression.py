"""Regression coverage for NewsDOM batch identity after session rollback."""

import pytest

from services.newsdom_worker import NewsdomRecognitionWorker


class _OneReadAttachmentId:
    """Bulk row whose mapped identity becomes unreadable after first access."""

    def __init__(self, attachment_id: int) -> None:
        self._attachment_id = attachment_id
        self._reads = 0

    @property
    def id(self) -> int:
        self._reads += 1
        if self._reads > 1:
            raise RuntimeError("bulk row was expired by rollback")
        return self._attachment_id


class _RollbackSession:
    def __init__(self) -> None:
        self.rollback_count = 0

    async def get(self, *_args, **_kwargs):
        raise RuntimeError("force per-item rollback")

    async def rollback(self) -> None:
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_attachment_cursor_uses_ids_snapshotted_before_rollback() -> None:
    """Cursor advancement must not dereference bulk ORM rows after rollback."""
    bulk_row = _OneReadAttachmentId(41)
    session = _RollbackSession()
    worker = NewsdomRecognitionWorker()

    async def load_pending(_session):
        return [bulk_row]

    worker._load_pending_attachments = load_pending  # type: ignore[method-assign]

    await worker._sweep_attachments(session)  # type: ignore[arg-type]

    assert session.rollback_count == 1
    assert worker._attachment_cursor == 41
    assert worker._attachment_retry_ids == {41}
