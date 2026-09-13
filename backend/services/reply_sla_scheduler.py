import asyncio
import logging
import random

from sqlalchemy import bindparam, func, or_, select
from sqlalchemy.exc import DBAPIError

from db.models import Email, TenantConfig
from db.session import AsyncSessionLocal, engine
from services.reply_sla_escalation_service import create_reply_sla_escalation_tasks

logger = logging.getLogger(__name__)
_sysrand = random.SystemRandom()
DEFAULT_REPLY_SLA_INTERVAL_SECONDS = 15 * 60
DEFAULT_REPLY_SLA_OVERDUE_HOURS = 48
DEFAULT_REPLY_SLA_LIMIT = 10
REPLY_SLA_SWEEP_LOCK_NAMESPACE = "naruon-reply-sla-sweep"
MAX_STARTUP_JITTER_SECONDS = 60


def _session_uses_postgresql(session) -> bool:
    """Identify PostgreSQL coordination without assuming a development bind."""
    try:
        bind = session.get_bind()
    except Exception:
        return False
    return getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"


_SWEEP_LOCK_PARAMS = {
    "namespace_key": REPLY_SLA_SWEEP_LOCK_NAMESPACE,
    "sweep_key": "sweep",
}


async def _try_acquire_sweep_lease(session) -> bool | None:
    """Try to become the sweep leader for this cycle.

    Returns ``None`` when the session is not PostgreSQL (single-process dev and
    test runs need no coordination), otherwise whether the non-blocking
    advisory lock was acquired. With multiple replicas, only the lease holder
    sweeps; the rest skip the cycle instead of duplicating escalation work.
    """
    if not _session_uses_postgresql(session):
        return None
    acquired = await session.scalar(
        select(
            func.pg_try_advisory_lock(
                func.hashtext(bindparam("namespace_key")),
                func.hashtext(bindparam("sweep_key")),
            )
        ),
        _SWEEP_LOCK_PARAMS,
    )
    return bool(acquired)


async def _release_sweep_lease(session) -> None:
    """Require confirmed release on the connection that acquired the lease."""
    released = await session.scalar(
        select(
            func.pg_advisory_unlock(
                func.hashtext(bindparam("namespace_key")),
                func.hashtext(bindparam("sweep_key")),
            )
        ),
        _SWEEP_LOCK_PARAMS,
    )
    if released is not True:
        raise RuntimeError("Reply SLA sweep lease release was not confirmed.")


class ReplySlaScheduler:
    """Schedule owner-scoped overdue reply tasks under a database sweep lease."""

    def __init__(
        self,
        *,
        interval_seconds: int = DEFAULT_REPLY_SLA_INTERVAL_SECONDS,
        overdue_hours: int = DEFAULT_REPLY_SLA_OVERDUE_HOURS,
        limit: int = DEFAULT_REPLY_SLA_LIMIT,
    ):
        """Set the cycle interval and existing escalation policy limits."""
        self.interval_seconds = interval_seconds
        self.overdue_hours = overdue_hours
        self.limit = limit
        self._task = None
        self._is_running = False

    async def start(self):
        """Start at most one local scheduling task."""
        if self._is_running:
            logger.warning("ReplySlaScheduler is already running.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ReplySlaScheduler started.")

    async def stop(self):
        """Cancel the scheduling task and await its cleanup."""
        if not self._is_running:
            return

        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug(
                    "ReplySlaScheduler cancellation acknowledged during shutdown."
                )
        logger.info("ReplySlaScheduler stopped.")

    async def _run_loop(self):
        """Jitter replica startup and retry failed cycles on the normal interval."""
        # Startup jitter de-synchronizes replicas started by the same deploy
        # so they do not contend for the sweep lease at the same instant.
        try:
            await asyncio.sleep(
                _sysrand.uniform(
                    0, min(self.interval_seconds / 10, MAX_STARTUP_JITTER_SECONDS)
                )
            )
        except asyncio.CancelledError:
            return

        while self._is_running:
            try:
                await self._sync()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Error in ReplySlaScheduler loop.", exc_info=True)

            if self._is_running:
                try:
                    await asyncio.sleep(self.interval_seconds)
                except asyncio.CancelledError:
                    break

    async def _sync(self):
        """Keep one physical lease connection across escalation transactions."""
        async with (
            engine.connect() as connection,
            AsyncSessionLocal(bind=connection) as session,
        ):
            try:
                lease = await _try_acquire_sweep_lease(session)
                if lease is False:
                    logger.debug(
                        "Reply SLA sweep skipped: another replica holds the lease."
                    )
                    return
                await self._sweep_configured_owners(session)
                if lease is True:
                    await session.rollback()
                    await _release_sweep_lease(session)
            except BaseException:
                # Invalidate before AsyncSession's shielded close/rollback can wait.
                await connection.invalidate()
                raise

    async def _sweep_configured_owners(self, session):
        """Reload owner records after rollback without replacing the lease backend."""
        result = await session.execute(
            select(TenantConfig.id).where(
                or_(
                    TenantConfig.smtp_username.isnot(None),
                    TenantConfig.imap_username.isnot(None),
                )
            )
        )
        config_ids = result.scalars().all()

        for config_id in config_ids:
            try:
                config = await session.get(
                    TenantConfig, config_id, populate_existing=True
                )
                if config is None:
                    continue
                workspace_ids = await session.scalars(
                    select(Email.workspace_id)
                    .where(
                        Email.user_id == config.user_id,
                        Email.organization_id == config.organization_id,
                    )
                    .distinct()
                )
                for workspace_id in workspace_ids:
                    # Bypass cached state after commit, and expired state after
                    # conflict rollback, before authorizing another workspace.
                    config = await session.get(
                        TenantConfig, config_id, populate_existing=True
                    )
                    if config is None:
                        break
                    await create_reply_sla_escalation_tasks(
                        session,
                        user_id=config.user_id,
                        organization_id=config.organization_id,
                        workspace_id=workspace_id,
                        overdue_hours=self.overdue_hours,
                        limit=self.limit,
                        tenant_config=config,
                    )
            except Exception as exc:
                if isinstance(exc, DBAPIError) and exc.connection_invalidated:
                    raise
                await session.rollback()
                logger.error(
                    "Overdue reply follow-up failed for a configured owner (%s).",
                    type(exc).__name__,
                )
