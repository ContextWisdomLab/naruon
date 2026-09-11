import pytest

import services.provider_writeback_retry_service as retry_service
from services.provider_writeback_retry_service import ProviderWritebackRetryWorker


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fake_session_local():
    return _FakeSessionContext()


@pytest.mark.asyncio
async def test_worker_poll_interval_does_not_define_retry_backoff(monkeypatch):
    """Keep scheduling cadence independent from provider retry backoff policy."""
    captured: list[dict[str, int]] = []

    async def dispatch_command(*args, **kwargs):
        return {"provider_write_executed": True}

    async def fake_process_due_retries(db, dispatch, **kwargs):
        captured.append(kwargs)
        return {
            "processed": 0,
            "succeeded": 0,
            "rescheduled": 0,
            "failed_exhausted": 0,
            "failed_permanent": 0,
        }

    monkeypatch.setattr(retry_service, "AsyncSessionLocal", _fake_session_local)
    monkeypatch.setattr(
        retry_service,
        "process_due_provider_writeback_retries",
        fake_process_due_retries,
    )

    worker = ProviderWritebackRetryWorker(
        dispatch_command,
        interval_seconds=7,
        retry_delay_seconds=300,
        batch_limit=11,
        max_attempts=5,
    )

    await worker._sync()

    assert captured == [
        {
            "batch_limit": 11,
            "retry_delay_seconds": 300,
            "max_attempts": 5,
        }
    ]


@pytest.mark.parametrize("retry_delay_seconds", [-1, -300])
def test_worker_rejects_negative_retry_backoff(retry_delay_seconds):
    async def dispatch_command(*args, **kwargs):
        return {"provider_write_executed": True}

    with pytest.raises(ValueError, match="retry_delay_seconds must not be negative"):
        ProviderWritebackRetryWorker(
            dispatch_command,
            retry_delay_seconds=retry_delay_seconds,
        )


def test_worker_allows_explicit_immediate_retry_backoff():
    async def dispatch_command(*args, **kwargs):
        return {"provider_write_executed": True}

    worker = ProviderWritebackRetryWorker(
        dispatch_command,
        retry_delay_seconds=0,
    )

    assert worker.retry_delay_seconds == 0
