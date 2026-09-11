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
    process_due_provider_writeback_retries,
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


@pytest.mark.asyncio
async def test_retry_worker_locks_only_the_row_being_dispatched():
    """Allow a second worker to claim later due work while provider I/O is blocked."""
    engine = create_async_engine(settings.DATABASE_URL)
    if engine.dialect.name != "postgresql":
        await engine.dispose()
        pytest.skip("PostgreSQL is required for retry-worker concurrency acceptance")

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
    retry_item_uids: list[str] = []
    first_dispatch_started = asyncio.Event()
    release_first_dispatch = asyncio.Event()
    first_task: asyncio.Task | None = None
    first_dispatched_sources: list[str] = []
    second_dispatched_sources: list[str] = []

    try:
        async with session_factory() as setup_db:
            for index, source_id in enumerate(
                ("webdav_concurrent_first", "webdav_concurrent_second")
            ):
                retry_item_uid = await schedule_provider_writeback_retry(
                    setup_db,
                    organization_id="org-retry-worker-concurrency",
                    workspace_id="workspace-retry-worker-concurrency",
                    command={
                        "action": "write_webdav",
                        "source_id": source_id,
                        "target_path": f"/Naruon/Notes/{source_id}.md",
                    },
                    error_code="runner_not_connected",
                    runner_request_id=f"runner_req_{source_id}",
                    retry_delay_seconds=0,
                )
                assert retry_item_uid is not None
                retry_item_uids.append(retry_item_uid)
                retry_item = await setup_db.get(
                    ProviderWritebackRetryItem, retry_item_uid
                )
                assert retry_item is not None
                retry_item.next_retry_at = datetime.datetime(
                    2000, 1, 1, tzinfo=datetime.timezone.utc
                ) + datetime.timedelta(seconds=index)
                await setup_db.commit()

        async def first_dispatch(
            organization_id,
            workspace_id,
            command,
            *,
            schedule_retry=True,
        ):
            first_dispatched_sources.append(command["source_id"])
            first_dispatch_started.set()
            await release_first_dispatch.wait()
            return {"provider_write_executed": True}

        async def second_dispatch(
            organization_id,
            workspace_id,
            command,
            *,
            schedule_retry=True,
        ):
            second_dispatched_sources.append(command["source_id"])
            return {"provider_write_executed": True}

        cutoff = datetime.datetime(2026, 9, 11, tzinfo=datetime.timezone.utc)
        async with session_factory() as first_worker_db, session_factory() as second_worker_db:
            first_task = asyncio.create_task(
                process_due_provider_writeback_retries(
                    first_worker_db,
                    first_dispatch,
                    now=cutoff,
                    batch_limit=2,
                )
            )
            await asyncio.wait_for(first_dispatch_started.wait(), timeout=2)

            second_summary = await asyncio.wait_for(
                process_due_provider_writeback_retries(
                    second_worker_db,
                    second_dispatch,
                    now=cutoff,
                    batch_limit=1,
                ),
                timeout=2,
            )

            assert second_summary["processed"] == 1
            assert second_dispatched_sources == ["webdav_concurrent_second"]

            release_first_dispatch.set()
            first_summary = await asyncio.wait_for(first_task, timeout=2)
            assert first_summary["processed"] == 1
            assert first_dispatched_sources == ["webdav_concurrent_first"]
    finally:
        release_first_dispatch.set()
        if first_task is not None and not first_task.done():
            try:
                await asyncio.wait_for(first_task, timeout=2)
            except Exception:
                first_task.cancel()
        if retry_item_uids:
            async with session_factory() as cleanup_db:
                await cleanup_db.execute(
                    delete(ProviderWritebackRetryItem).where(
                        ProviderWritebackRetryItem.retry_item_uid.in_(retry_item_uids)
                    )
                )
                await cleanup_db.commit()
        await engine.dispose()
