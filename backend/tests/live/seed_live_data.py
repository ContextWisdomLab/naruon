"""Seed deterministic data for the live Docker E2E stack."""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.models import (  # noqa: E402
    ConnectorSignalEvent,
    Document,
    Email,
    ProjectFolder,
    TenantConfig,
    WebdavAccount,
    Workspace,
)
from db.session import AsyncSessionLocal  # noqa: E402

THREAD_ID = "<live-e2e-root@example.test>"
LIVE_E2E_USER_ID = "testuser"
LIVE_E2E_ORGANIZATION_ID = "org-acme"
LIVE_E2E_WORKSPACE_ID = "workspace-org-acme"
LIVE_E2E_WEBDAV_SOURCE_UID = "webdav_src_live_primary"
LIVE_E2E_PROJECT_FOLDER_UID = "webdav_folder_live_roadmap"
LIVE_E2E_DOCUMENT_ID = "doc_repository_ready"
LIVE_E2E_CONNECTOR_EVENT_UID = "connector_evt_live_data"
MESSAGE_IDS = [
    "<live-e2e-root@example.test>",
    "<live-e2e-reply@example.test>",
]
LIVE_E2E_OPENAI_API_KEY = "ollama"


async def _cleanup_existing_data(session: AsyncSession) -> None:
    await session.execute(
        delete(ConnectorSignalEvent).where(
            ConnectorSignalEvent.event_uid == LIVE_E2E_CONNECTOR_EVENT_UID
        )
    )
    await session.execute(
        delete(Document).where(Document.document_id == LIVE_E2E_DOCUMENT_ID)
    )
    await session.execute(
        delete(ProjectFolder).where(
            ProjectFolder.folder_uid == LIVE_E2E_PROJECT_FOLDER_UID
        )
    )
    await session.execute(
        delete(WebdavAccount).where(
            WebdavAccount.source_uid == LIVE_E2E_WEBDAV_SOURCE_UID
        )
    )
    await session.execute(delete(Email).where(Email.message_id.in_(MESSAGE_IDS)))


async def _setup_workspace(session: AsyncSession) -> None:
    workspace_result = await session.execute(
        select(Workspace).where(Workspace.workspace_id == LIVE_E2E_WORKSPACE_ID)
    )
    workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(
            workspace_id=LIVE_E2E_WORKSPACE_ID,
            workspace_name="Live E2E Workspace",
            workspace_domain="example.test",
        )
        session.add(workspace)


async def _setup_tenant_config(session: AsyncSession) -> None:
    result = await session.execute(
        select(TenantConfig).where(
            TenantConfig.user_id == LIVE_E2E_USER_ID,
            TenantConfig.organization_id == LIVE_E2E_ORGANIZATION_ID,
        )
    )
    tenant_config = result.scalar_one_or_none()
    if tenant_config is None:
        tenant_config = TenantConfig(
            user_id=LIVE_E2E_USER_ID,
            organization_id=LIVE_E2E_ORGANIZATION_ID,
        )
        session.add(tenant_config)
    tenant_config.openai_api_key = LIVE_E2E_OPENAI_API_KEY


def _seed_emails(session: AsyncSession) -> None:
    session.add_all(
        [
            Email(
                user_id=LIVE_E2E_USER_ID,
                organization_id=LIVE_E2E_ORGANIZATION_ID,
                workspace_id=LIVE_E2E_WORKSPACE_ID,
                message_id=MESSAGE_IDS[0],
                thread_id=THREAD_ID,
                fingerprint="sha256:live-e2e-root",
                sender="ops@example.test",
                recipients="swe@example.test",
                subject="Live E2E Release",
                date=dt.datetime(2026, 5, 11, 12, 0, tzinfo=dt.timezone.utc),
                body="Root live release evidence message.",
                embedding=[0.0] * 1536,
            ),
            Email(
                user_id=LIVE_E2E_USER_ID,
                organization_id=LIVE_E2E_ORGANIZATION_ID,
                workspace_id=LIVE_E2E_WORKSPACE_ID,
                message_id=MESSAGE_IDS[1],
                thread_id=THREAD_ID,
                fingerprint="sha256:live-e2e-reply",
                sender="swe@example.test",
                recipients="ops@example.test",
                subject="Live E2E Release",
                in_reply_to=MESSAGE_IDS[0],
                references=MESSAGE_IDS[0],
                date=dt.datetime(2026, 5, 11, 12, 1, tzinfo=dt.timezone.utc),
                body="Reply live release evidence message.",
                embedding=[0.0] * 1536,
            ),
        ]
    )


def _seed_other_entities(session: AsyncSession) -> None:
    session.add(
        WebdavAccount(
            source_uid=LIVE_E2E_WEBDAV_SOURCE_UID,
            user_id=LIVE_E2E_USER_ID,
            organization_id=LIVE_E2E_ORGANIZATION_ID,
            workspace_id=LIVE_E2E_WORKSPACE_ID,
            server_url="https://files.example.test/dav",
            username="live-e2e@example.test",
            credentials_encrypted="live-e2e-webdav-secret",
            writeback_enabled=True,
            etag_value="etag-live-data",
        )
    )
    session.add(
        ProjectFolder(
            folder_uid=LIVE_E2E_PROJECT_FOLDER_UID,
            user_id=LIVE_E2E_USER_ID,
            organization_id=LIVE_E2E_ORGANIZATION_ID,
            project_name="Live Data Project",
            webdav_path="/Projects/Live_Data",
        )
    )
    session.add(
        Document(
            document_id=LIVE_E2E_DOCUMENT_ID,
            workspace_id=LIVE_E2E_WORKSPACE_ID,
            document_name="roadmap.md",
            document_type="text/markdown",
            document_content="# Live roadmap\n\nSeeded document for full-stack E2E.",
            document_status="uploaded",
        )
    )
    session.add(
        ConnectorSignalEvent(
            event_uid=LIVE_E2E_CONNECTOR_EVENT_UID,
            organization_id=LIVE_E2E_ORGANIZATION_ID,
            workspace_id=LIVE_E2E_WORKSPACE_ID,
            signal_key="connector_heartbeat",
            state_code="heartbeat",
            detail_text="outbound connector heartbeat received",
            observed_at=dt.datetime(2026, 5, 11, 12, 2, tzinfo=dt.timezone.utc),
        )
    )


async def seed_live_data() -> None:
    async with AsyncSessionLocal() as session:
        await _cleanup_existing_data(session)
        await _setup_workspace(session)
        await _setup_tenant_config(session)
        _seed_emails(session)
        _seed_other_entities(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_live_data())
