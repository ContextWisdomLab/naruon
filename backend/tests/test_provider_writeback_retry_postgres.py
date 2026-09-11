import asyncio
import datetime

import asyncpg
import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from db.models import ProviderWritebackRetryItem
from services.provider_writeback_retry_service import (
    _due_retry_query,
    schedule_provider_writeback_retry,
)


@pytest.mark.asyncio
async def test_due_retry_claim_skips_row_locked_by_concurrent_postgres_worker():
    """Prove the retry claim skips a row held by another PostgreSQL transaction."""
    engine = create_async_engine(settings.DATABASE_URL)
    if engine.dialect.name != "postgresql":
        await engine.dispose()
        pytest.skip("PostgreSQL is required for SKIP LOCKED acceptance")

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (
        ConnectionRefusedError,
        OSError,
        OperationalError,
        asyncpg.CannotConnectNowError,
        asyncpg.InvalidAuthorizationSpecificationError,
        asyncpg.InvalidCatalogNameError,
        asyncpg.InvalidPasswordError,
    ):
        await engine.dispose()
        pytest.skip("PostgreSQL smoke path unavailable")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    retry_item_uid: str | None = None
    try:
        async with session_factory() as setup_db:
            retry_item_uid = await schedule_provider_writeback_retry(
                setup_db,
                organization_id="org-skip-locked-acceptance",
                workspace_id="workspace-skip-locked-acceptance",
                command={
                    "action": "write_webdav",
                    "source_id": "webdav_skip_locked_acceptance",
                    "target_path": "/Naruon/Notes/skip-locked.md",
                },
                error_code="runner_not_connected",
                runner_request_id="runner_req_skip_locked_acceptance",
                retry_delay_seconds=0,
            )
            assert retry_item_uid is not None
            retry_item = await setup_db.get(ProviderWritebackRetryItem, retry_item_uid)
            assert retry_item is not None
            retry_item.next_retry_at = datetime.datetime(
                2000, 1, 1, tzinfo=datetime.timezone.utc
            )
            await setup_db.commit()

        cutoff = datetime.datetime(2026, 9, 11, tzinfo=datetime.timezone.utc)
        async with session_factory() as first_worker_db, session_factory() as second_worker_db:
            first_result = await first_worker_db.execute(_due_retry_query(cutoff, 1))
            first_claim = list(first_result.scalars().all())
            assert [item.retry_item_uid for item in first_claim] == [retry_item_uid]

            second_result = await asyncio.wait_for(
                second_worker_db.execute(_due_retry_query(cutoff, 1)),
                timeout=2,
            )
            second_claim = list(second_result.scalars().all())
            assert retry_item_uid not in {
                item.retry_item_uid for item in second_claim
            }
            await second_worker_db.rollback()
            await first_worker_db.rollback()
    finally:
        if retry_item_uid is not None:
            async with session_factory() as cleanup_db:
                await cleanup_db.execute(
                    delete(ProviderWritebackRetryItem).where(
                        ProviderWritebackRetryItem.retry_item_uid == retry_item_uid
                    )
                )
                await cleanup_db.commit()
        await engine.dispose()
