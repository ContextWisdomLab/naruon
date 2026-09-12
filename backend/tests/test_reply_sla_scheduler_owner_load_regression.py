"""Regression coverage for owner-local Reply SLA config-load failures."""

import pytest

from services.reply_sla_scheduler import ReplySlaScheduler


class _ScalarIds:
    def all(self):
        return [17]


class _ConfigIdsResult:
    def scalars(self):
        return _ScalarIds()


class _RecoverableOwnerLoadFailureSession:
    def __init__(self) -> None:
        self.rollback_count = 0

    async def execute(self, _statement):
        return _ConfigIdsResult()

    async def get(self, *_args, **_kwargs):
        raise RuntimeError("owner config refresh failed")

    async def rollback(self) -> None:
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_owner_config_load_failure_is_isolated_to_that_owner() -> None:
    """A recoverable config refresh failure must roll back and end the owner lane."""
    session = _RecoverableOwnerLoadFailureSession()
    scheduler = ReplySlaScheduler()

    await scheduler._sweep_configured_owners(session)

    assert session.rollback_count == 1
