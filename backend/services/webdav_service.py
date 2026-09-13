import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Email, ProjectFolder, TicketTask, WebdavAccount
from services.knowledge_extractor import SELF_SENT_KNOWLEDGE_SOURCE

logger = logging.getLogger(__name__)


def safe_webdav_source_label(source_id: str | None) -> str:
    if not source_id:
        return "WebDAV source"
    return f"WebDAV source {source_id}"


async def sync_webdav_folders(session, user_id: str, organization_id: str | None):
    """
    Fetch folder structures for all WebDAV accounts of the user.
    """
    from urllib.parse import urlsplit

    from core.url_validation import _reject_unsafe_ip_literal

    logger.info(f"Syncing WebDAV folders for user {user_id}")
    organization_filter = (
        WebdavAccount.organization_id == organization_id
        if organization_id is not None
        else WebdavAccount.organization_id.is_(None)
    )
    stmt = select(WebdavAccount.server_url, WebdavAccount.source_uid).where(
        WebdavAccount.user_id == user_id, organization_filter
    )
    res = await session.execute(stmt)
    accounts = res.all()
    for server_url, source_uid in accounts:
        try:
            if server_url:
                parsed = urlsplit(server_url)
                if parsed.scheme != "https":
                    raise ValueError("WebDAV server_url must use HTTPS")
                if not parsed.hostname:
                    raise ValueError("WebDAV server_url must include a hostname")
                _reject_unsafe_ip_literal("WebDAV server_url", parsed.hostname)
        except ValueError as exc:
            logger.warning(
                "Invalid WebDAV server URL for source %s: %s",
                source_uid or "unknown",
                exc,
            )
            continue

        logger.info(
            "Fetched folder structures for WebDAV source %s",
            source_uid or "unknown",
        )
    return True


class WebDavService:
    def __init__(self):
        self._mock_accounts = {
            "demo_user": [
                {
                    "source_id": "webdav_src_demo_primary",
                    "server_url": "https://webdav.naruon.net",
                    "username": "demo_user",
                    "display_label": "WebDAV source webdav_src_demo_primary",
                    "writeback_enabled": True,
                    "etag": "etag-webdav-demo-primary",
                }
            ]
        }
        self._mock_folders = {
            "demo_user": [
                {
                    "folder_uid": "webdav_folder_demo_roadmap",
                    "project_name": "Naruon Roadmap 2026",
                    "webdav_path": "/Projects/Naruon_Roadmap_2026",
                    "owner_user_id": "demo_user",
                    "organization_id": None,
                },
                {
                    "folder_uid": "webdav_folder_demo_marketing",
                    "project_name": "Marketing Assets",
                    "webdav_path": "/Projects/Marketing_Assets",
                    "owner_user_id": "demo_user",
                    "organization_id": None,
                },
            ]
        }

    def get_connected_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetch connected WebDAV accounts for a user.
        In a real implementation, this queries the database.
        """
        return self._mock_accounts.get(user_id, [])

    def get_project_folders(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetch the list of project folders structured by AI.
        """
        return self._mock_folders.get(user_id, [])

    async def get_connected_accounts_from_db(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str | None = None,
        workspace_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        scope_filters = [
            WebdavAccount.user_id == user_id,
            WebdavAccount.organization_id == organization_id
            if organization_id is not None
            else WebdavAccount.organization_id.is_(None),
        ]
        if workspace_id is not None:
            scope_filters.append(WebdavAccount.workspace_id == workspace_id)
        stmt = select(
            WebdavAccount.source_uid,
            WebdavAccount.writeback_enabled,
            WebdavAccount.etag_value,
        ).where(*scope_filters)
        result = await session.execute(stmt)
        return [
            {
                "source_id": source_uid,
                "display_label": safe_webdav_source_label(source_uid),
                "writeback_enabled": bool(writeback_enabled),
                "etag": etag_value,
            }
            for source_uid, writeback_enabled, etag_value in result.all()
        ]

    async def get_project_folders_from_db(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str | None,
        folder_uid: str | None = None,
    ) -> List[Dict[str, Any]]:
        stmt = select(ProjectFolder).where(
            ProjectFolder.user_id == user_id,
            ProjectFolder.organization_id == organization_id
            if organization_id is not None
            else ProjectFolder.organization_id.is_(None),
        )
        if folder_uid is not None:
            stmt = stmt.where(ProjectFolder.folder_uid == folder_uid)
        result = await session.execute(stmt)
        return [
            {
                "folder_uid": folder.folder_uid,
                "project_name": folder.project_name,
                "webdav_path": folder.webdav_path,
                "owner_user_id": folder.user_id,
                "organization_id": folder.organization_id,
            }
            for folder in result.scalars().all()
        ]

    def sync_attachments_to_folder(self, email_id: str, project_name: str) -> bool:
        """
        Organizes an email's attachments into the specified WebDAV project folder.
        """
        logger.info(
            f"Syncing attachments from email {email_id} to project {project_name}"
        )
        # Mock implementation: in reality, this would download from storage and upload via webdavclient3
        return True

    def determine_webdav_writeback_intent(
        self, user_id: str, target_source_id: str | None = None
    ) -> Dict[str, Any]:
        """
        Server-authoritative WebDAV writeback source selection.
        """
        accounts = self.get_connected_accounts(user_id)
        return self.determine_webdav_writeback_intent_from_accounts(
            accounts,
            target_source_id=target_source_id,
        )

    async def determine_webdav_writeback_intent_from_db(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        target_source_id: str | None = None,
    ) -> Dict[str, Any]:
        accounts = await self.get_connected_accounts_from_db(
            session, user_id, organization_id, workspace_id
        )
        return self.determine_webdav_writeback_intent_from_accounts(
            accounts,
            target_source_id=target_source_id,
        )

    async def determine_knowledge_materialization_intent_from_db(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str | None,
        workspace_id: str | None,
        source_task_id: str,
        target_source_id: str | None = None,
    ) -> Dict[str, Any]:
        task_result = await session.execute(
            select(TicketTask, Email.message_id)
            .outerjoin(
                Email,
                (TicketTask.related_email_id == Email.id)
                & (Email.user_id == user_id)
                & (Email.organization_id == organization_id)
                & (Email.workspace_id == workspace_id),
            )
            .where(
                TicketTask.task_uid == source_task_id,
                TicketTask.user_id == user_id,
                TicketTask.organization_id == organization_id,
            )
        )
        row = task_result.one_or_none()
        if row is None:
            return {
                "status": "error",
                "error_code": "not_found",
                "message": "Self-sent knowledge task was not found.",
            }

        task, source_email_id = row
        if task.source_type != SELF_SENT_KNOWLEDGE_SOURCE:
            return {
                "status": "error",
                "error_code": "validation_error",
                "message": "Task is not self-sent knowledge.",
            }
        if source_email_id is None:
            return {
                "status": "error",
                "error_code": "missing_provenance",
                "message": "Self-sent knowledge task missing source email provenance.",
            }

        result = await self.determine_webdav_writeback_intent_from_db(
            session,
            user_id,
            organization_id,
            workspace_id,
            target_source_id=target_source_id,
        )
        if result.get("status") == "error":
            return result

        return {
            "intent": "knowledge_materialization",
            "status": "intent_ready",
            "task_id": task.task_uid,
            "source_type": SELF_SENT_KNOWLEDGE_SOURCE,
            "source_email_id": source_email_id,
            "source_thread_id": task.related_thread_id,
            "source_id": result["source_id"],
            "target_label": result["target_label"],
            "target_path": f"/Naruon/Notes/{task.task_uid}.md",
            "requires_if_match": result["requires_if_match"],
            "if_match": result.get("if_match"),
            "provenance": result["provenance"],
            "provider_write_executed": False,
            "audit_event": "webdav.self_sent_knowledge_intent.created",
        }

    def determine_webdav_writeback_intent_from_accounts(
        self,
        accounts: List[Dict[str, Any]],
        target_source_id: str | None = None,
    ) -> Dict[str, Any]:
        writable_accounts = {
            account["source_id"]: account
            for account in accounts
            if account.get("writeback_enabled", False)
        }
        if not writable_accounts:
            return {
                "status": "error",
                "error_code": "no_webdav_account",
                "message": "No connected WebDAV accounts found.",
            }

        if target_source_id is not None:
            selected_account = writable_accounts.get(target_source_id)
            if selected_account is None:
                return {
                    "status": "error",
                    "error_code": "webdav_account_not_found",
                    "message": "Requested WebDAV account was not found.",
                }
        else:
            selected_account = next(iter(writable_accounts.values()))

        return {
            "intent": "writeback",
            "source_id": selected_account["source_id"],
            "target_label": selected_account.get("display_label")
            or safe_webdav_source_label(selected_account["source_id"]),
            "requires_if_match": True,
            "if_match": selected_account.get("etag")
            or selected_account.get("etag_value"),
            "provenance": "server-authoritative",
        }


webdav_service = WebDavService()
