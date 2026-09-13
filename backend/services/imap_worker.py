import asyncio
import datetime
import logging
from collections.abc import Iterable
from dataclasses import dataclass

import aioimaplib
from sqlalchemy import select

from db.models import Email, TenantConfig
from db.session import AsyncSessionLocal
from services.email_client import validate_imap_destination
from services.email_dedupe_service import strong_email_fingerprint
from services.email_parser import EmailData, parse_eml_bytes
from services.exceptions import EmailParseError
from services.knowledge_extractor import (
    extract_knowledge_from_self_sent,
    is_self_sent_email,
)
from services.threading_service import assign_thread_id, generate_email_fingerprint


async def process_fetched_email(
    session,
    email_data: EmailData,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    owner_addresses: Iterable[str] | None = None,
    is_read: bool = True,
):
    subject = email_data.get("subject", "")
    date_obj = email_data.get("date")
    if hasattr(date_obj, "isoformat"):
        date_str = date_obj.isoformat()
    else:
        date_str = str(date_obj) if date_obj else ""
    if isinstance(date_obj, datetime.datetime):
        persisted_date = (
            date_obj.astimezone(datetime.timezone.utc)
            if date_obj.tzinfo is not None
            else date_obj.replace(tzinfo=datetime.timezone.utc)
        )
    else:
        persisted_date = datetime.datetime.now(datetime.timezone.utc)
    sender = email_data.get("sender", "")
    recipients_list = email_data.get("recipients", [])
    recipients = (
        ",".join(recipients_list)
        if isinstance(recipients_list, list)
        else str(recipients_list or "")
    )

    fingerprint = strong_email_fingerprint(
        sender=sender,
        subject=subject,
        date=persisted_date,
        body=email_data.get("body", ""),
    ) or generate_email_fingerprint(subject, date_str, sender, recipients)

    # Check if duplicate
    stmt = select(Email).where(
        *Email.owner_filters(user_id, organization_id, workspace_id),
        Email.fingerprint == fingerprint,
    )
    result = await session.execute(stmt)
    existing_email = result.scalar_one_or_none()

    if existing_email:
        logger.info(
            "Email with fingerprint %s already exists. Skipping duplicate insertion.",
            fingerprint,
        )
        return existing_email

    thread_id = await assign_thread_id(
        session,
        email_data,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )

    new_email = Email(
        user_id=user_id,
        organization_id=organization_id or None,
        # Mirrors the workspace_id convention used across this codebase
        # (services/email_import_service.py, services/project_graph/):
        # workspace-<organization_id>, falling back to workspace-<user_id>
        # for an org-less/personal scope.
        workspace_id=workspace_id,
        message_id=email_data.get("message_id", ""),
        thread_id=thread_id,
        fingerprint=fingerprint,
        sender=sender,
        recipients=recipients,
        subject=subject,
        date=persisted_date,
        body=email_data.get("body", ""),
        is_read=is_read,
        embedding=[0.0] * 1536,
    )

    session.add(new_email)
    if is_self_sent_email(new_email, owner_addresses):
        await session.flush()
        await extract_knowledge_from_self_sent(session, new_email, owner_addresses)
    return new_email


logger = logging.getLogger(__name__)
MAX_IMAP_FETCH_MESSAGES = 10


async def resolve_unambiguous_workspace_id(
    session, user_id: str, organization_id: str | None
) -> str | None:
    """Resolve the single workspace an owner's already-imported mail belongs to.

    Background mail sync (IMAP, POP3) has no signed session and therefore no
    independently authoritative workspace claim to thread through -- the only
    evidence available is whatever workspace this owner's mail has already
    been imported under. Returns ``None`` (fail closed; the caller must skip
    the sync) when zero or more than one distinct workspace is found, so a
    first-run or genuinely multi-workspace mailbox is never guessed at.
    """
    workspace_ids = list(
        await session.scalars(
            select(Email.workspace_id)
            .where(
                Email.user_id == user_id,
                Email.organization_id == organization_id,
            )
            .distinct()
            .limit(2)
        )
    )
    if len(workspace_ids) != 1:
        return None
    return workspace_ids[0]


def flags_indicate_seen(fetch_data) -> bool:
    """True when an IMAP FETCH response's FLAGS envelope contains ``\\Seen``.

    Defensive by design: a message is only reported read when an explicit
    ``FLAGS (... \\Seen ...)`` section is present, so a parse miss falls back to
    unread rather than silently marking mail read.
    """
    for item in fetch_data or []:
        parts = item if isinstance(item, (tuple, list)) else (item,)
        for part in parts:
            raw = (
                part
                if isinstance(part, bytes)
                else str(part).encode("utf-8", "replace")
            )
            upper = raw.upper()
            if b"FLAGS" in upper and b"\\SEEN" in upper:
                return True
    return False


@dataclass(frozen=True, slots=True)
class ImapSyncConfig:
    user_id: str
    organization_id: str | None
    workspace_id: str
    imap_server: str
    imap_port: int
    imap_username: str | None
    imap_password: str | None


class ImapSyncWorker:
    def __init__(self):
        self._task = None
        self._is_running = False

    async def start(self):
        if self._is_running:
            logger.warning("ImapSyncWorker is already running.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ImapSyncWorker started.")

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
        logger.info("ImapSyncWorker stopped.")

    async def _run_loop(self):
        while self._is_running:
            try:
                await self._sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ImapSyncWorker loop: {e}", exc_info=True)

            # Sleep for 1 minute before the next sync
            if self._is_running:
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    break

    async def _sync(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    TenantConfig.user_id,
                    TenantConfig.organization_id,
                    TenantConfig.imap_server,
                    TenantConfig.imap_port,
                    TenantConfig.imap_username,
                    TenantConfig.imap_password,
                ).where(
                    TenantConfig.imap_server.isnot(None),
                    TenantConfig.imap_port.isnot(None),
                )
            )
            tenant_configs = [
                ImapSyncConfig(
                    user_id=row.user_id,
                    organization_id=row.organization_id,
                    workspace_id="",
                    imap_server=str(row.imap_server),
                    imap_port=int(row.imap_port),
                    imap_username=row.imap_username,
                    imap_password=row.imap_password,
                )
                for row in result
            ]
            configs = []
            for config in tenant_configs:
                workspace_id = await resolve_unambiguous_workspace_id(
                    session, config.user_id, config.organization_id
                )
                if workspace_id is None:
                    logger.info(
                        "Skipping IMAP sync because an unambiguous workspace is unavailable"
                    )
                    continue
                configs.append(
                    ImapSyncConfig(
                        user_id=config.user_id,
                        organization_id=config.organization_id,
                        workspace_id=workspace_id,
                        imap_server=config.imap_server,
                        imap_port=config.imap_port,
                        imap_username=config.imap_username,
                        imap_password=config.imap_password,
                    )
                )

        tasks = []
        for config in configs:
            tasks.append(self._sync_tenant(config))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _sync_tenant(self, config: TenantConfig | ImapSyncConfig):
        imap_server = str(config.imap_server)
        imap_port = int(config.imap_port)  # type: ignore[arg-type]
        try:
            imap_server, imap_port = validate_imap_destination(imap_server, imap_port)
        except ValueError:
            logger.info(
                "Skipping IMAP sync for user %s due to mail destination policy",
                config.user_id,
            )
            return 0

        logger.info(
            "Connecting to IMAP server %s:%s for user %s",
            imap_server,
            imap_port,
            config.user_id,
        )
        try:
            messages = await self._fetch_messages(config, imap_server, imap_port)
            imported_count = await self._import_messages(config, messages)
            logger.info(
                "Successfully synced IMAP server for user %s with %s imported messages.",
                config.user_id,
                imported_count,
            )
            return imported_count
        except Exception as e:
            logger.error(
                "Failed to connect or sync with IMAP server for user %s: %s",
                config.user_id,
                type(e).__name__,
            )
            raise Exception(
                f"IMAP Sync failed for user {config.user_id}: {type(e).__name__}"
            ) from e

    async def _fetch_messages(
        self,
        config: TenantConfig,
        imap_server: str | None = None,
        imap_port: int | None = None,
    ) -> list[bytes]:
        if imap_server is None or imap_port is None:
            imap_server, imap_port = self._validated_destination(config)
        import ssl

        ssl_context = ssl.create_default_context()
        imap_client = aioimaplib.IMAP4_SSL(
            imap_server, imap_port, ssl_context=ssl_context
        )
        try:
            await imap_client.wait_hello_from_server()
            logger.info(
                "Successfully connected to IMAP server for user %s.",
                config.user_id,
            )
            if not config.imap_username or not config.imap_password:
                logger.error(
                    "IMAP account configuration incomplete for user %s.",
                    config.user_id,
                )
                raise RuntimeError(
                    f"IMAP account configuration incomplete for user {config.user_id}"
                )

            resp, _data = await imap_client.login(
                config.imap_username, config.imap_password
            )
            if resp != "OK":
                raise RuntimeError("IMAP authentication failed")

            select_resp, _select_data = await imap_client.select("INBOX")
            if select_resp != "OK":
                raise RuntimeError("IMAP mailbox selection failed")

            search_resp, search_data = await imap_client.search("ALL")
            if search_resp != "OK":
                raise RuntimeError("IMAP message search failed")

            messages: list[tuple[bytes, bool]] = []
            message_numbers = self._message_numbers_from_search(search_data)
            for message_number in message_numbers[-MAX_IMAP_FETCH_MESSAGES:]:
                fetch_resp, fetch_data = await imap_client.fetch(
                    message_number, "(RFC822 FLAGS)"
                )
                if fetch_resp != "OK":
                    continue
                is_read = flags_indicate_seen(fetch_data)
                for raw in self._extract_rfc822_messages(fetch_data):
                    messages.append((raw, is_read))
            return messages
        finally:
            try:
                if hasattr(imap_client, "protocol") and imap_client.protocol:
                    await imap_client.logout()
            except Exception as logout_err:
                logger.warning(
                    "Error during IMAP logout for user %s: %s",
                    config.user_id,
                    type(logout_err).__name__,
                )

    async def _import_messages(
        self, config: TenantConfig, messages: list[tuple[bytes, bool]]
    ) -> int:
        if not messages:
            return 0

        imported_count = 0
        owner_addresses = [config.imap_username] if config.imap_username else None
        workspace_id = getattr(config, "workspace_id", "")
        if not workspace_id:
            logger.info(
                "Skipping IMAP sync because an authoritative workspace is unavailable"
            )
            return 0
        async with AsyncSessionLocal() as session:
            try:
                for raw_message, is_read in messages:
                    try:
                        email_data = parse_eml_bytes(raw_message)
                    except EmailParseError:
                        logger.info(
                            "Skipping unparsable IMAP message for user %s.",
                            config.user_id,
                        )
                        continue
                    await process_fetched_email(
                        session,
                        email_data,
                        config.user_id,
                        config.organization_id,
                        workspace_id,
                        owner_addresses=owner_addresses,
                        is_read=is_read,
                    )
                    imported_count += 1
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return imported_count

    def _validated_destination(self, config: TenantConfig) -> tuple[str, int]:
        return validate_imap_destination(
            str(config.imap_server),
            int(config.imap_port),  # type: ignore[arg-type]
        )

    def _message_numbers_from_search(self, search_data) -> list[str]:
        message_numbers: list[str] = []
        for item in search_data or []:
            raw_item = (
                item.decode("ascii", errors="ignore")
                if isinstance(item, bytes)
                else str(item)
            )
            for token in raw_item.split():
                if token.isdigit():
                    message_numbers.append(token)
        return message_numbers

    def _extract_rfc822_messages(self, fetch_data) -> list[bytes]:
        messages: list[bytes] = []
        for item in fetch_data or []:
            messages.extend(self._extract_rfc822_parts(item))
        return messages

    def _extract_rfc822_parts(self, item) -> list[bytes]:
        if isinstance(item, tuple):
            messages: list[bytes] = []
            for part in item:
                messages.extend(self._extract_rfc822_parts(part))
            return messages
        if isinstance(item, list):
            messages: list[bytes] = []
            for part in item:
                messages.extend(self._extract_rfc822_parts(part))
            return messages
        if isinstance(item, str):
            item = item.encode("utf-8", errors="replace")
        if isinstance(item, bytes) and self._looks_like_rfc822_message(item):
            return [item]
        return []

    def _looks_like_rfc822_message(self, value: bytes) -> bool:
        header_block = value.split(b"\r\n\r\n", maxsplit=1)[0]
        if header_block == value:
            header_block = value.split(b"\n\n", maxsplit=1)[0]
        return b":" in header_block and (b"\r\n\r\n" in value or b"\n\n" in value)
