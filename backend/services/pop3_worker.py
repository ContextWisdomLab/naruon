import asyncio
import logging
import poplib
from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import TenantConfig
from services.email_client import validate_pop3_destination
from services.email_parser import parse_eml_bytes
from services.exceptions import EmailParseError
from services.imap_worker import process_fetched_email, resolve_unambiguous_workspace_id

logger = logging.getLogger(__name__)
MAX_POP3_FETCH_MESSAGES = 10


class Pop3SyncWorker:
    def __init__(self):
        self._task = None
        self._is_running = False

    async def start(self):
        if self._is_running:
            logger.warning("Pop3SyncWorker is already running.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Pop3SyncWorker started.")

    async def stop(self):
        if not self._is_running:
            return

        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Pop3SyncWorker stopped.")

    async def _run_loop(self):
        while self._is_running:
            try:
                await self._sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Pop3SyncWorker loop: {e}", exc_info=True)

            if self._is_running:
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    break

    async def _sync(self):
        resolved = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TenantConfig).where(TenantConfig.pop3_server.isnot(None))
            )
            configs = result.scalars().all()

            for config in configs:
                if not config.pop3_server or not config.pop3_port:
                    continue
                # TenantConfig has no workspace_id column; POP3 sync has no
                # signed session either, so the only evidence of this owner's
                # workspace is whatever workspace their already-imported mail
                # belongs to (same fail-closed resolution as ImapSyncWorker).
                workspace_id = await resolve_unambiguous_workspace_id(
                    session, config.user_id, config.organization_id
                )
                if workspace_id is None:
                    logger.info(
                        "Skipping POP3 sync because an unambiguous workspace is unavailable"
                    )
                    continue
                resolved.append((config, workspace_id))

        semaphore = asyncio.Semaphore(10)
        tasks = [
            self._sync_tenant(config, workspace_id, semaphore)
            for config, workspace_id in resolved
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _sync_tenant(
        self, config: TenantConfig, workspace_id: str, semaphore: asyncio.Semaphore
    ):
        async with semaphore:
            try:
                pop3_server, pop3_port = self._validated_destination(config)
            except ValueError:
                logger.info(
                    "Skipping POP3 sync for user %s due to mail destination policy",
                    config.user_id,
                )
                return
            logger.info(
                f"Connecting to POP3 server {pop3_server}:{pop3_port} for user {config.user_id}"
            )
            try:
                # We use asyncio.to_thread for synchronous poplib
                messages = await asyncio.to_thread(
                    self._do_pop3_sync, config, pop3_server, pop3_port
                )
                imported_count = await self._import_messages(
                    config, workspace_id, messages
                )
                logger.info(
                    "Successfully synced POP3 server for user %s with %s imported messages.",
                    config.user_id,
                    imported_count,
                )
            except Exception as e:
                logger.error(
                    "Failed to connect or sync with POP3 server for user %s: %s",
                    config.user_id,
                    type(e).__name__,
                )

    async def _import_messages(
        self, config: TenantConfig, workspace_id: str, messages: list[bytes]
    ) -> int:
        if not messages:
            return 0

        imported_count = 0
        owner_addresses = [config.pop3_username] if config.pop3_username else None
        async with AsyncSessionLocal() as session:
            try:
                for raw_message in messages:
                    try:
                        email_data = parse_eml_bytes(raw_message)
                    except EmailParseError:
                        logger.info(
                            "Skipping unparsable POP3 message for user %s.",
                            config.user_id,
                        )
                        continue
                    await process_fetched_email(
                        session,
                        email_data,
                        config.user_id,
                        config.organization_id,
                        workspace_id=workspace_id,
                        owner_addresses=owner_addresses,
                    )
                    imported_count += 1
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return imported_count

    def _validated_destination(self, config: TenantConfig) -> tuple[str, int]:
        return validate_pop3_destination(
            str(config.pop3_server),
            int(config.pop3_port),  # type: ignore[arg-type]
        )

    def _do_pop3_sync(
        self,
        config: TenantConfig,
        pop3_server: str | None = None,
        pop3_port: int | None = None,
    ) -> list[bytes]:
        if pop3_server is None or pop3_port is None:
            pop3_server, pop3_port = self._validated_destination(config)
        pop3_client = poplib.POP3_SSL(pop3_server, pop3_port)
        try:
            if not config.pop3_username:
                logger.error(
                    "POP3 account configuration incomplete for user %s.",
                    config.user_id,
                )
                raise RuntimeError(
                    f"POP3 account configuration incomplete for user {config.user_id}"
                )
            if not config.pop3_password:
                logger.error(
                    "POP3 account configuration incomplete for user %s.",
                    config.user_id,
                )
                raise RuntimeError(
                    f"POP3 account configuration incomplete for user {config.user_id}"
                )
            pop3_client.user(config.pop3_username)
            pop3_client.pass_(config.pop3_password)
            _response, listings, _octets = pop3_client.list()
            messages: list[bytes] = []
            for listing in listings[:MAX_POP3_FETCH_MESSAGES]:
                message_number = self._message_number_from_listing(listing)
                if message_number is None:
                    continue
                _retr_response, lines, _retr_octets = pop3_client.retr(message_number)
                messages.append(b"\r\n".join(self._bytes_line(line) for line in lines))
            return messages
        finally:
            pop3_client.quit()

    def _message_number_from_listing(self, listing: bytes | str) -> int | None:
        raw_listing = (
            listing.decode("ascii", errors="ignore")
            if isinstance(listing, bytes)
            else listing
        )
        candidate = (
            raw_listing.strip().split(maxsplit=1)[0] if raw_listing.strip() else ""
        )
        if not candidate.isdigit():
            return None
        return int(candidate)

    def _bytes_line(self, line: bytes | str) -> bytes:
        return (
            line if isinstance(line, bytes) else line.encode("utf-8", errors="replace")
        )
