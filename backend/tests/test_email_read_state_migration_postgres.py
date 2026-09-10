"""PostgreSQL regression coverage for 0011_email_read_state.

String-matching the revision file's source (test_alembic_migrations.py)
cannot detect a destructive downgrade or prove the upgrade is actually
idempotent -- both require running the real migration against a real
database in each of the shapes it must handle.
"""

import subprocess
import secrets
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from asyncpg.exceptions import InvalidAuthorizationSpecificationError, InvalidPasswordError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import settings

pytestmark = pytest.mark.postgres

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PRE_READ_STATE_REVISION = "0009_project_graph_projection"


def _run_migrations(database_url: str, revision: str = "head") -> None:
    result = subprocess.run(
        [sys.executable, str(_BACKEND_ROOT / "scripts" / "migrate_db.py"), revision],
        cwd=_BACKEND_ROOT,
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
        f"(exit {result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert not any(
        status in result.stdout + result.stderr
        for status in ("Timeout", "Fatal", "Warn", "Denied")
    )


def _run_downgrade(database_url: str, revision: str) -> None:
    # scripts/migrate_db.py only wraps alembic's upgrade command; reuse its
    # alembic_config() but call command.downgrade() directly for this test.
    script = (
        "from scripts.migrate_db import alembic_config\n"
        "from alembic import command\n"
        f"command.downgrade(alembic_config(), {revision!r})\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_BACKEND_ROOT,
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
        f"alembic downgrade {revision} failed "
        f"(exit {result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert not any(
        status in result.stdout + result.stderr
        for status in ("Timeout", "Fatal", "Warn", "Denied")
    )


@pytest.fixture
def fresh_database_url():
    base_url = make_url(settings.DATABASE_URL)
    database_name = f"test_email_read_state_{uuid.uuid4().hex[:12]}"

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

    import asyncio

    try:
        asyncio.run(admin(f'CREATE DATABASE "{database_name}"'))
    except (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
        OSError,
        ConnectionError,
    ) as exc:
        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")

    try:
        yield base_url.set(database=database_name).render_as_string(hide_password=False)
    finally:
        asyncio.run(admin(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))


async def _column_exists(database_url: str, table_name: str, column_name: str) -> bool:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table_name AND column_name = :column_name"
                ),
                {"table_name": table_name, "column_name": column_name},
            )
            return result.first() is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_adds_is_read_to_a_historical_email_records_table(
    fresh_database_url,
):
    """A database whose own 0001 ran before is_read existed in the Email
    model has email_records without the column; upgrading to head must add
    it, not silently leave it missing."""
    _run_migrations(fresh_database_url, revision=_PRE_READ_STATE_REVISION)

    engine = create_async_engine(fresh_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE email_records DROP COLUMN IF EXISTS is_read")
            )
    finally:
        await engine.dispose()

    assert await _column_exists(fresh_database_url, "email_records", "is_read") is False

    _run_migrations(fresh_database_url)

    assert await _column_exists(fresh_database_url, "email_records", "is_read") is True


@pytest.mark.asyncio
async def test_upgrade_is_idempotent_against_a_legacy_emails_table_with_is_read(
    fresh_database_url,
):
    """A legacy "emails" table that already has is_read (e.g. from a partial
    earlier application) must not make upgrade() crash with a
    duplicate-column error."""
    _run_migrations(fresh_database_url, revision=_PRE_READ_STATE_REVISION)

    engine = create_async_engine(fresh_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE emails "
                    "(id serial primary key, is_read boolean not null default true)"
                )
            )
    finally:
        await engine.dispose()

    _run_migrations(fresh_database_url)


@pytest.mark.asyncio
async def test_downgrade_does_not_destroy_read_state_on_a_fresh_database(
    fresh_database_url,
):
    """A fresh database's email_records.is_read comes from 0001's live
    create_all, not from 0011_email_read_state -- downgrading past 0011 must
    not drop it (and, if it did, would destroy real per-message read/unread
    state along with it)."""
    _run_migrations(fresh_database_url)
    assert await _column_exists(fresh_database_url, "email_records", "is_read") is True

    _run_downgrade(fresh_database_url, _PRE_READ_STATE_REVISION)

    assert await _column_exists(fresh_database_url, "email_records", "is_read") is True


@pytest.mark.asyncio
async def test_upgrade_head_repairs_a_database_already_stamped_past_0011(
    fresh_database_url,
):
    """Alembic never re-runs a revision's upgrade() once that revision id is
    recorded as applied -- editing 0011_email_read_state.py cannot repair a
    database whose alembic_version history already includes it but is
    missing is_read regardless (e.g. an earlier broken version of that
    revision, a partial apply, manual intervention). 0019_email_read_state_
    repair is the real fix: it must add the column even though the database
    is already stamped through 0018 with 0011 long since applied, so only
    0019 itself -- not a re-run of 0011 -- is what's left to bring it to
    head."""
    _run_migrations(fresh_database_url, revision="0018_workspace_registry")
    assert await _column_exists(fresh_database_url, "email_records", "is_read") is True

    engine = create_async_engine(fresh_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE email_records DROP COLUMN IF EXISTS is_read")
            )
    finally:
        await engine.dispose()

    assert await _column_exists(fresh_database_url, "email_records", "is_read") is False

    _run_migrations(fresh_database_url)

    assert await _column_exists(fresh_database_url, "email_records", "is_read") is True
