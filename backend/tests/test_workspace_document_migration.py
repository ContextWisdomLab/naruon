"""Regression coverage for the missing ``workspace_entities``/``workspace_documents``
Alembic migration.

``Workspace``/``Document`` have been declared in ``db/models.py`` since before
this repository's incremental migration history tracked them explicitly (see
``alembic/versions/0018_workspace_registry.py``). No production code path ever
inserted a ``Workspace`` row for a real signed session either, so
``Document.workspace_id``'s foreign key could never be satisfied by a real
``/api/data/documents`` upload. A database missing these tables also used to
crash on ``0016_document_org_scope`` (``NoSuchTableError``) before ever
reaching ``0018_workspace_registry``; ``0016`` is now ``has_table``-guarded.

These tests exercise the actual documented production path
(``scripts/migrate_db.py`` -> ``alembic upgrade head``, never
``Base.metadata.create_all``) against a real, disposable PostgreSQL database,
then call the real ``/api/data/documents`` endpoints through the real FastAPI
app with only the database session swapped for one bound to that database.
"""

import asyncio
import subprocess
import secrets
import sys
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
import pytest_asyncio
from asyncpg.exceptions import (
    InvalidAuthorizationSpecificationError,
    InvalidPasswordError,
)
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import AuthContext, get_auth_context
from core.config import settings
from db.session import get_db, get_readonly_db
from main import app

pytestmark = pytest.mark.postgres

BACKEND_ROOT = Path(__file__).resolve().parents[1]
# The revision immediately before 0016_document_org_scope, which -- for a
# database missing workspace_documents -- is the first migration in the
# chain that touches the table at all. Stopping here (rather than at 0017,
# after 0016 has already run) is what actually exercises the real historical
# gap: 0016 must not crash before 0018_workspace_registry ever gets to run.
_PRE_REGISTRY_REVISION = "0015_merge_newsdom_email_heads"
_SMOKE_WORKSPACE_ID = "workspace-workspace-migration-smoke-org"


def _run_migrations(database_url: str, revision: str = "head") -> None:
    result = subprocess.run(
        [sys.executable, str(BACKEND_ROOT / "scripts" / "migrate_db.py"), revision],
        cwd=BACKEND_ROOT,
        env={
            "NARUON_ENV_FILE": "/dev/null",
            "DATABASE_URL": database_url,
            "AUTH_SESSION_HMAC_SECRET": secrets.token_urlsafe(48),
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"scripts/migrate_db.py {revision} failed "
        f"(exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert not any(
        status in result.stdout + result.stderr
        for status in ("Timeout", "Fatal", "Warn", "Denied")
    )


@pytest_asyncio.fixture
async def fresh_database_url():
    base_url = make_url(settings.DATABASE_URL)
    test_db_name = f"test_workspace_doc_{uuid.uuid4().hex[:16]}"

    async def _admin(sql: str) -> None:
        conn = await asyncpg.connect(
            host=base_url.host,
            port=base_url.port,
            user=base_url.username,
            password=base_url.password,
            database="postgres",
        )
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    try:
        await _admin(f'CREATE DATABASE "{test_db_name}"')
    except (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
        OSError,
        ConnectionError,
    ) as exc:
        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")

    try:
        yield base_url.set(database=test_db_name).render_as_string(
            hide_password=False
        )
    finally:
        await _admin(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)')


@pytest_asyncio.fixture
async def migrated_client(fresh_database_url):
    engine = create_async_engine(fresh_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with sessionmaker() as session:
            yield session

    async def override_auth_context() -> AuthContext:
        return AuthContext(
            user_id="workspace_migration_smoke_user",
            role="member",
            organization_id="workspace-migration-smoke-org",
            group_ids=(),
            workspace_id=_SMOKE_WORKSPACE_ID,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_readonly_db] = override_db
    app.dependency_overrides[get_auth_context] = override_auth_context
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_readonly_db, None)
        app.dependency_overrides.pop(get_auth_context, None)
        await engine.dispose()


async def _table_exists(database_url: str, name: str) -> bool:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
            )
            return bool(result.scalar())
    finally:
        await engine.dispose()


async def _drop_workspace_registry_tables(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS workspace_documents"))
            await conn.execute(text("DROP TABLE IF EXISTS workspace_entities"))
    finally:
        await engine.dispose()


async def _assert_document_upload_serves_cleanly(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/data/documents",
        json={
            "document_name": "roadmap.md",
            "document_type": "text/markdown",
            "document_content": "# Roadmap",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == _SMOKE_WORKSPACE_ID
    assert body["document_id"]

    # A second upload from the same signed workspace must not fail trying to
    # re-insert the already-provisioned Workspace row (workspace_id is its
    # primary key).
    second_response = await client.post(
        "/api/data/documents",
        json={
            "document_name": "notes.md",
            "document_type": "text/markdown",
            "document_content": "# Notes",
        },
    )
    assert second_response.status_code == 200, second_response.text


@pytest.mark.asyncio
async def test_document_upload_serves_after_full_head_migration_from_empty(
    fresh_database_url, migrated_client
):
    """A brand-new database migrated straight to head must be able to serve
    /api/data/documents without a missing-relation or FK-violation error."""
    _run_migrations(fresh_database_url)
    await _assert_document_upload_serves_cleanly(migrated_client)


@pytest.mark.asyncio
async def test_concurrent_first_uploads_provision_one_workspace(
    fresh_database_url, migrated_client
):
    """Concurrent first requests must not race on the workspace primary key."""
    _run_migrations(fresh_database_url)

    responses = await asyncio.gather(
        *(
            migrated_client.post(
                "/api/data/documents",
                json={
                    "document_name": f"concurrent-{index}.md",
                    "document_type": "text/markdown",
                    "document_content": "# Concurrent",
                },
            )
            for index in range(16)
        )
    )

    assert [response.status_code for response in responses] == [200] * 16


@pytest.mark.asyncio
async def test_document_upload_serves_after_upgrading_a_pre_registry_database(
    fresh_database_url, migrated_client
):
    """Reproduce the exact reported gap: a real, already-incrementally-migrated
    production database that was provisioned before ``Workspace``/``Document``
    existed in ``db/models.py`` never gets ``workspace_entities``/
    ``workspace_documents`` created by any migration prior to
    ``0018_workspace_registry`` (``0001_initial_control_plane``'s
    ``Base.metadata.create_all`` only reflects *today's* model metadata, so it
    cannot recreate that historical, pre-model-addition state on its own).
    Force that end state directly -- dropping the tables a stopped-at-0015
    database would never have had -- then migrate straight to head in one
    call, crossing 0016_document_org_scope (which used to crash with
    NoSuchTableError on a database in exactly this state) before
    0018_workspace_registry ever runs. Prove that both tables end up correct
    and /api/data/documents serves cleanly."""
    _run_migrations(fresh_database_url, revision=_PRE_REGISTRY_REVISION)

    await _drop_workspace_registry_tables(fresh_database_url)
    assert await _table_exists(fresh_database_url, "workspace_entities") is False
    assert await _table_exists(fresh_database_url, "workspace_documents") is False

    _run_migrations(fresh_database_url)

    assert await _table_exists(fresh_database_url, "workspace_entities") is True
    assert await _table_exists(fresh_database_url, "workspace_documents") is True
    await _assert_document_upload_serves_cleanly(migrated_client)
