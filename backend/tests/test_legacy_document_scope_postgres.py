"""PostgreSQL regression for legacy workspace documents with no organization id.

Revision 0016 intentionally left pre-existing ``workspace_documents.organization_id``
values NULL. Organization-scoped sessions still need to reach those rows when the
signed workspace claim is the canonical ``workspace-<organization_id>`` value,
without making the same NULL row visible to a different organization that presents
the same workspace string.
"""

import subprocess
import secrets
import sys
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
from asyncpg.exceptions import InvalidAuthorizationSpecificationError, InvalidPasswordError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import AuthContext, get_auth_context
from core.config import settings
from db.session import get_db, get_readonly_db
from main import app

pytestmark = pytest.mark.postgres

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ORGANIZATION_ID = "legacy-document-org"
_WORKSPACE_ID = f"workspace-{_ORGANIZATION_ID}"
_DOCUMENT_ID = "document_legacy_org_scope"


def _run_migrations(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, str(_BACKEND_ROOT / "scripts" / "migrate_db.py"), "head"],
        cwd=_BACKEND_ROOT,
        env={
            "DATABASE_URL": database_url,
            "AUTH_SESSION_HMAC_SECRET": secrets.token_urlsafe(48),
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert not any(
        status in output for status in ("Timeout", "Fatal", "Warn", "Denied")
    ), output


@pytest.mark.asyncio
async def test_legacy_null_org_document_is_visible_only_to_matching_signed_org() -> None:
    base_url = make_url(settings.DATABASE_URL)
    database_name = f"test_legacy_doc_scope_{uuid.uuid4().hex[:12]}"

    async def admin(sql: str) -> None:
        connection = await asyncpg.connect(
            host=base_url.host,
            port=base_url.port,
            user=base_url.username,
            password=base_url.password,
            database="postgres",
        )
        try:
            await connection.execute(sql)
        finally:
            await connection.close()

    try:
        await admin(f'CREATE DATABASE "{database_name}"')
    except (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
        OSError,
        ConnectionError,
    ) as exc:
        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")

    database_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with session_factory() as session:
            yield session

    async def matching_auth() -> AuthContext:
        return AuthContext(
            user_id="legacy-document-user",
            role="member",
            organization_id=_ORGANIZATION_ID,
            group_ids=(),
            workspace_id=_WORKSPACE_ID,
        )

    async def other_org_same_workspace_auth() -> AuthContext:
        return AuthContext(
            user_id="other-user",
            role="member",
            organization_id="other-organization",
            group_ids=(),
            workspace_id=_WORKSPACE_ID,
        )

    try:
        _run_migrations(database_url)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO workspace_entities
                        (workspace_id, workspace_name, workspace_domain, created_at)
                    VALUES (:workspace_id, :workspace_name, NULL, now())
                    ON CONFLICT (workspace_id) DO NOTHING
                    """
                ),
                {"workspace_id": _WORKSPACE_ID, "workspace_name": _WORKSPACE_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO workspace_documents
                        (document_id, workspace_id, organization_id, document_name,
                         document_type, document_content, document_status, created_at)
                    VALUES
                        (:document_id, :workspace_id, NULL, :document_name,
                         'text/markdown', '# Legacy', 'uploaded', now())
                    """
                ),
                {
                    "document_id": _DOCUMENT_ID,
                    "workspace_id": _WORKSPACE_ID,
                    "document_name": "legacy.md",
                },
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_readonly_db] = override_db
        app.dependency_overrides[get_auth_context] = matching_auth

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            reparse_response = await client.post(
                f"/api/data/documents/{_DOCUMENT_ID}/reparse"
            )
            assert reparse_response.status_code == 200, reparse_response.text

            quality_response = await client.get("/api/data/quality-surface")
            assert quality_response.status_code == 200, quality_response.text
            assert _DOCUMENT_ID in {
                asset["asset_key"] for asset in quality_response.json()["repository_assets"]
            }

            app.dependency_overrides[get_auth_context] = other_org_same_workspace_auth
            denied_response = await client.post(
                f"/api/data/documents/{_DOCUMENT_ID}/reparse"
            )
            assert denied_response.status_code == 404

            other_quality_response = await client.get("/api/data/quality-surface")
            assert other_quality_response.status_code == 200, other_quality_response.text
            assert _DOCUMENT_ID not in {
                asset["asset_key"]
                for asset in other_quality_response.json()["repository_assets"]
            }
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_readonly_db, None)
        app.dependency_overrides.pop(get_auth_context, None)
        await engine.dispose()
        try:
            await admin(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        except (OSError, ConnectionError):
            # Best-effort teardown: a transient connectivity error here must not
            # mask the test's actual assertions.
            pass
