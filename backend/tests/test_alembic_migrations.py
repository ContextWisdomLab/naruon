import importlib.util
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_revision_module(revision_filename: str):
    # Revision filenames start with a digit and aren't valid module names,
    # so they can't be imported with a normal `import` statement.
    path = BACKEND_ROOT / "alembic" / "versions" / revision_filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_pre_0020_email_records(
    sync_conn, *, legacy_identity_as_constraint: bool
) -> None:
    sync_conn.execute(text("DROP TABLE IF EXISTS email_records CASCADE"))
    sync_conn.execute(
        text(
            "CREATE TABLE email_records ("
            "id serial primary key, user_id varchar, "
            "organization_id varchar, message_id varchar)"
        )
    )
    if legacy_identity_as_constraint:
        sync_conn.execute(
            text(
                "ALTER TABLE email_records ADD CONSTRAINT "
                "uq_email_records_owner_message_id "
                "UNIQUE (user_id, organization_id, message_id)"
            )
        )
    else:
        sync_conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_email_records_owner_message_id "
                "ON email_records (user_id, organization_id, message_id)"
            )
        )


def _run_0020_upgrade(sync_conn) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    module = _load_revision_module("0020_email_workspace_scope.py")
    context = MigrationContext.configure(sync_conn, opts={"target_metadata": None})
    with Operations.context(context):
        module.upgrade()


def _run_0021_upgrade(sync_conn) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    module = _load_revision_module("0021_calendar_correction_rationale.py")
    context = MigrationContext.configure(sync_conn, opts={"target_metadata": None})
    with Operations.context(context):
        module.upgrade()


def _run_0001_upgrade(sync_conn) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    module = _load_revision_module("0001_initial_control_plane.py")
    context = MigrationContext.configure(sync_conn, opts={"target_metadata": None})
    with Operations.context(context):
        module.upgrade()


def test_alembic_scaffold_exists_with_model_metadata_target():
    alembic_ini = BACKEND_ROOT / "alembic.ini"
    env_py = BACKEND_ROOT / "alembic" / "env.py"

    assert alembic_ini.exists()
    assert env_py.exists()

    alembic_ini_text = alembic_ini.read_text()
    env_text = env_py.read_text()

    assert "script_location = alembic" in alembic_ini_text
    assert "sqlalchemy.url =" in alembic_ini_text
    assert "from db.models import Base" in env_text
    assert "target_metadata = Base.metadata" in env_text
    assert "settings.DATABASE_URL" in env_text


def test_initial_alembic_revision_records_current_schema_path():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revisions = sorted(versions_dir.glob("*.py"))

    assert revisions
    revision_text = "\n".join(path.read_text() for path in revisions)

    assert 'revision = "0001_initial_control_plane"' in revision_text
    assert "down_revision = None" in revision_text
    assert "CREATE EXTENSION IF NOT EXISTS vector" in revision_text
    assert "Base.metadata.create_all" in revision_text
    # Must delegate to the guarded execute_schema_backfill (which skips
    # legacy-table-only statements when the table doesn't exist yet on a
    # fresh database) rather than iterating schema_backfill_sql() directly.
    assert "execute_schema_backfill" in revision_text


def test_email_workspace_migration_replaces_owner_only_identity_constraint():
    revision_text = (
        BACKEND_ROOT / "alembic" / "versions" / "0020_email_workspace_scope.py"
    ).read_text()

    assert 'down_revision = "0019_attachment_uid"' in revision_text
    assert '"uq_emails_owner_message_id"' in revision_text
    assert '"uq_emails_workspace_message"' in revision_text
    assert "op.drop_constraint(" in revision_text
    assert "op.create_unique_constraint(" in revision_text
    assert (
        '["user_id", "organization_id", "workspace_id", "message_id"]' in revision_text
    )
    assert "sa.text(" not in revision_text


def test_calendar_correction_rationale_uses_append_only_rename_migration():
    original_revision = (
        BACKEND_ROOT / "alembic" / "versions" / "0018_calendar_conflict_judgments.py"
    ).read_text()
    rename_revision = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "0021_calendar_correction_rationale.py"
    ).read_text()

    assert 'sa.Column("rationale"' in original_revision
    assert 'down_revision = "0020_email_workspace_scope"' in rename_revision
    assert 'new_column_name="correction_rationale"' in rename_revision
    assert "op.alter_column(" in rename_revision
    assert "sa.text(" not in rename_revision


def test_calendar_correction_rationale_upgrade_renames_legacy_column(monkeypatch):
    module = _load_revision_module("0021_calendar_correction_rationale.py")
    calls = []

    class Inspector:
        @staticmethod
        def has_table(table_name):
            return table_name == "calendar_conflict_corrections"

        @staticmethod
        def get_columns(_table_name):
            return [{"name": "rationale"}]

    def _fake_bind():
        return object()

    monkeypatch.setattr(module.op, "get_bind", _fake_bind)
    monkeypatch.setattr(module.sa, "inspect", lambda _connection: Inspector())
    monkeypatch.setattr(
        module.op,
        "alter_column",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    module.upgrade()

    assert calls == [
        (
            ("calendar_conflict_corrections", "rationale"),
            {"new_column_name": "correction_rationale"},
        )
    ]


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_calendar_correction_rationale_real_postgres_smoke():
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TEMP TABLE calendar_conflict_corrections ("
                    "rationale text) ON COMMIT DROP"
                )
            )
            await conn.run_sync(_run_0021_upgrade)

            def _column_names(sync_conn):
                return {
                    column["name"]
                    for column in inspect(sync_conn).get_columns(
                        "calendar_conflict_corrections"
                    )
                }

            column_names = await conn.run_sync(_column_names)
            assert "correction_rationale" in column_names
            assert "rationale" not in column_names
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
    except Exception:
        await engine.dispose()
        raise
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_0001_initial_upgrade_succeeds_against_a_fresh_database():
    # 0001_initial_control_plane.py::upgrade() is what a genuinely fresh
    # `alembic upgrade head` runs first. Base.metadata.create_all() never
    # creates a table named "emails" (only "email_records" is ORM-modeled),
    # so if this migration bypasses execute_schema_backfill's guard and
    # blindly executes every schema_backfill_sql() statement itself, the
    # legacy "ix_emails_owner_date" index statement raises
    # 'relation "emails" does not exist' and a fresh install can never
    # migrate at all.
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_run_0001_upgrade)
            result = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'email_records' "
                    "AND indexname = 'ix_email_records_owner_date'"
                )
            )
            assert result.scalar_one() == "ix_email_records_owner_date"
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
    except Exception:
        await engine.dispose()
        raise
    finally:
        await engine.dispose()


def test_email_workspace_migration_also_drops_bootstrap_created_owner_only_index():
    """backend/scripts/bootstrap_db.py's owner-only identity predates this
    migration's own uq_emails_owner_message_id and uses a different name
    (uq_email_records_owner_message_id) and a different catalog shape (a
    plain index, not a named unique constraint). A database that was
    bootstrap-initialized before bootstrap_db.py's own fix landed and is
    later migrated via Alembic would keep that stricter 3-column identity
    forever -- this migration's own get_unique_constraints()-only check can
    never see it (wrong name, and get_unique_constraints never returns plain
    indexes at all)."""
    revision_text = (
        BACKEND_ROOT / "alembic" / "versions" / "0020_email_workspace_scope.py"
    ).read_text()

    assert '"uq_email_records_owner_message_id"' in revision_text
    assert "get_indexes(" in revision_text
    assert "op.drop_index(" in revision_text


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.parametrize("legacy_identity_as_constraint", [True, False])
async def test_email_workspace_migration_real_postgres_smoke(
    legacy_identity_as_constraint,
):
    """inspector.get_indexes() also reports the backing index of a unique
    constraint under the same name (PostgreSQL implements a unique
    constraint via a unique index), so a check that only looks at
    get_indexes() before get_unique_constraints() would try `DROP INDEX` on
    a constraint's own backing index -- PostgreSQL rejects that outright
    ("cannot drop index ... because constraint ... requires it"), aborting
    the whole migration. bootstrap_db.py has only ever produced the legacy
    identity as a plain index, but this proves the migration itself handles
    either catalog shape without relying on that assumption."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as probe_conn:
            original_email_records_oid = (
                await probe_conn.execute(
                    text(
                        "SELECT oid FROM pg_class "
                        "WHERE oid = to_regclass('email_records')"
                    )
                )
            ).scalar_one_or_none()
        assert original_email_records_oid is not None

        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:

                def _setup(sync_conn):
                    _setup_pre_0020_email_records(
                        sync_conn,
                        legacy_identity_as_constraint=legacy_identity_as_constraint,
                    )

                await conn.run_sync(_setup)
                await conn.run_sync(_run_0020_upgrade)

                def _inspect(sync_conn):
                    insp = inspect(sync_conn)
                    return (
                        {i["name"] for i in insp.get_indexes("email_records")},
                        {
                            c["name"]
                            for c in insp.get_unique_constraints("email_records")
                        },
                    )

                index_names, constraint_names = await conn.run_sync(_inspect)
            finally:
                await transaction.rollback()

        async with engine.connect() as probe_conn:
            restored_email_records_oid = (
                await probe_conn.execute(
                    text(
                        "SELECT oid FROM pg_class "
                        "WHERE oid = to_regclass('email_records')"
                    )
                )
            ).scalar_one_or_none()
        assert restored_email_records_oid == original_email_records_oid
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
    except Exception:
        await engine.dispose()
        raise
    finally:
        await engine.dispose()

    assert "uq_email_records_owner_message_id" not in index_names
    assert "uq_email_records_owner_message_id" not in constraint_names
    assert "uq_emails_workspace_message" in constraint_names


def test_provider_writeback_retry_queue_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0002_provider_writeback_retry_queue.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0002_provider_retry_queue"' in revision_text
    assert 'down_revision = "0001_initial_control_plane"' in revision_text
    assert "op.create_table(" in revision_text
    assert '"provider_writeback_retry_items"' in revision_text
    assert '"retry_item_uid"' in revision_text
    assert '"command_payload_encrypted"' in revision_text
    assert '"retry_state"' in revision_text
    assert "ix_provider_writeback_retry_items_scope_state" in revision_text
    assert "has_table" in revision_text
    assert "op.create_index(" in revision_text
    assert "sa.text(" not in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_prompt_template_scope_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0003_prompt_template_scope.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0003_prompt_template_scope"' in revision_text
    assert 'down_revision = "0002_provider_retry_queue"' in revision_text
    assert '"prompt_templates"' in revision_text
    assert '"prompt_uid"' in revision_text
    assert '"organization_id"' in revision_text
    assert '"workspace_id"' in revision_text
    assert "ix_prompt_templates_owner_scope" in revision_text
    assert "ix_prompt_templates_shared_scope" in revision_text
    assert "uq_prompt_templates_prompt_uid" in revision_text
    assert "has_table" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_ai_hub_workflow_runs_have_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0004_ai_hub_workflow_runs.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0004_ai_hub_workflow_runs"' in revision_text
    assert 'down_revision = "0003_prompt_template_scope"' in revision_text
    assert '"workflow_definitions"' in revision_text
    assert '"agent_run_records"' in revision_text
    assert '"workflow_uid"' in revision_text
    assert '"run_uid"' in revision_text
    assert '"steps_json"' in revision_text
    assert '"status_code"' in revision_text
    assert "ix_workflow_definitions_scope_time" in revision_text
    assert "ix_workflow_definitions_owner_scope" in revision_text
    assert "ix_agent_run_records_workflow_uid" in revision_text
    assert "ix_agent_run_records_scope_time" in revision_text
    assert "ix_agent_run_records_owner_scope" in revision_text
    assert "ForeignKeyConstraint" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_content_graph_records_have_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0005_content_graph_records.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0005_content_graph_records"' in revision_text
    assert 'down_revision = "0004_ai_hub_workflow_runs"' in revision_text
    assert '"content_nodes"' in revision_text
    assert '"content_segments"' in revision_text
    assert '"content_node_uid"' in revision_text
    assert '"content_segment_uid"' in revision_text
    assert '"content_node_id"' in revision_text
    assert '"content_segment_id"' in revision_text
    assert '"word_count"' in revision_text
    assert '"token_count"' not in revision_text
    assert '"email_id"' in revision_text
    assert '"attachment_id"' in revision_text
    assert "ix_content_nodes_email_source" in revision_text
    assert "ix_content_segments_email_source" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_knowledge_graph_edges_have_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0006_knowledge_graph_edges.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0006_knowledge_graph_edges"' in revision_text
    assert 'down_revision = "0005_content_graph_records"' in revision_text
    assert '"knowledge_graph_edges"' in revision_text
    assert '"knowledge_graph_edge_id"' in revision_text
    assert '"edge_uid"' in revision_text
    assert '"email_id"' in revision_text
    assert '"attachment_id"' in revision_text
    assert '"source_node_id"' in revision_text
    assert '"target_node_id"' in revision_text
    assert '"source_segment_id"' in revision_text
    assert '"target_segment_id"' in revision_text
    assert '"content_nodes.content_node_id"' in revision_text
    assert '"content_segments.content_segment_id"' in revision_text
    assert '"source_kind"' in revision_text
    assert '"source_record_uid"' in revision_text
    assert '"edge_kind"' in revision_text
    assert '"edge_path"' in revision_text
    assert "ix_knowledge_graph_edges_email_kind" in revision_text
    assert "ix_knowledge_graph_edges_source_segment" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_attachment_parse_metadata_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0007_attachment_parse_metadata.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0007_attachment_parse_metadata"' in revision_text
    assert 'down_revision = "0006_knowledge_graph_edges"' in revision_text
    assert '"email_attachments"' in revision_text
    assert '"content_type"' in revision_text
    assert '"parse_status"' in revision_text
    assert '"parse_error_code"' in revision_text
    assert "has_column" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.drop_column(" in revision_text


def test_project_graph_projection_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0009_project_graph_projection.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0009_project_graph_projection"' in revision_text
    assert 'down_revision = "0008_attachment_parser_audit"' in revision_text
    assert '"project_graph_objects"' in revision_text
    assert '"project_graph_edges"' in revision_text
    assert '"project_graph_corrections"' in revision_text
    assert '"object_uid"' in revision_text
    assert '"edge_uid"' in revision_text
    assert '"correction_uid"' in revision_text
    assert '"workspace_id"' in revision_text
    assert '"source_segment_uids"' in revision_text
    assert '"attributes_json"' in revision_text
    assert '"before_json"' in revision_text
    assert '"after_json"' in revision_text
    assert '"content_segments.content_segment_id"' in revision_text
    assert "ix_project_graph_objects_scope_type_status" in revision_text
    assert "ix_project_graph_edges_scope_type" in revision_text
    assert "ix_project_graph_corrections_scope_time" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_llm_batch_orchestrator_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0012_llm_batch_orchestrator.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0012_llm_batch_orchestrator"' in revision_text
    assert 'down_revision = "0011_email_model_reconciliation"' in revision_text
    assert '"llm_batch_jobs"' in revision_text
    assert '"llm_batch_items"' in revision_text
    assert '"batch_job_uid"' in revision_text
    assert '"batch_item_uid"' in revision_text
    assert '"routing_mode"' in revision_text
    assert '"orchestrator_batch_uid"' in revision_text
    assert '"cost_micro_usd"' in revision_text
    assert '"batch_orchestrator_base_url"' in revision_text
    assert '"batch_orchestrator_token"' in revision_text
    assert '"batch_local_dsn"' in revision_text
    assert "sa.ForeignKeyConstraint(" in revision_text
    assert 'ondelete="CASCADE"' in revision_text
    assert "ix_llm_batch_jobs_scope_status" in revision_text
    assert "ix_llm_batch_items_job_sequence" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text
    assert "op.drop_column(" in revision_text


def test_scopeweave_promotion_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0013_scopeweave_promotion.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0013_scopeweave_promotion"' in revision_text
    assert 'down_revision = "0012_llm_batch_orchestrator"' in revision_text
    assert '"scopeweave_promotion_target"' in revision_text
    assert '"scopeweave_promotion_link"' in revision_text
    assert '"base_url"' in revision_text
    assert '"access_token"' in revision_text
    assert '"scopeweave_work_item_id"' in revision_text
    assert '"scopeweave_work_item_url"' in revision_text
    assert "uq_scopeweave_promotion_target_scope" in revision_text
    assert "uq_scopeweave_promotion_link_object" in revision_text
    assert "ix_scopeweave_promotion_link_scope" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_migration_runner_uses_alembic_upgrade_head_not_bootstrap_create_all():
    migration_runner = BACKEND_ROOT / "scripts" / "migrate_db.py"

    assert migration_runner.exists()
    runner_text = migration_runner.read_text()

    assert "command.upgrade" in runner_text
    assert '"head"' in runner_text
    assert "script_location" in runner_text
    assert "bootstrap_db" not in runner_text
    assert "create_all" not in runner_text


def test_backend_requirements_include_alembic():
    requirements = (BACKEND_ROOT / "requirements.txt").read_text()

    assert any(
        line.split("==", maxsplit=1)[0] == "alembic"
        for line in requirements.splitlines()
    )


def test_language_agnostic_search_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0010_language_agnostic_search.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0010_language_agnostic_search"' in revision_text
    assert 'down_revision = "0009_project_graph_projection"' in revision_text
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in revision_text
    assert "CREATE EXTENSION IF NOT EXISTS unaccent" in revision_text
    assert "search_normalized_text" in revision_text
    assert "normalize(coalesce(input_text, ''), NFC)" in revision_text
    assert "regdictionary" in revision_text
    assert "IMMUTABLE" in revision_text
    assert "gist_trgm_ops(siglen=256)" in revision_text
    assert "ix_email_records_search_document_trgm" in revision_text
    assert "ix_email_attachments_content_trgm" in revision_text
    assert "ix_content_segments_safe_text_trgm" in revision_text
    assert "ix_project_graph_objects_search_document_trgm" in revision_text
    assert "IF NOT EXISTS" in revision_text
    assert "DROP INDEX IF EXISTS" in revision_text


def test_revision_identifiers_fit_alembic_version_column():
    """alembic_version.version_num is VARCHAR(32); longer revision ids
    make ``alembic upgrade head`` fail on fresh databases (regression:
    the original 38-char 0008 revision id)."""
    import re

    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    for revision_path in sorted(versions_dir.glob("*.py")):
        revision_text = revision_path.read_text()
        match = re.search(r'^revision = "([^"]+)"', revision_text, re.MULTILINE)
        assert match, f"no revision id in {revision_path.name}"
        revision_id = match.group(1)
        assert len(revision_id) <= 32, (
            f"{revision_path.name}: revision id {revision_id!r} is "
            f"{len(revision_id)} chars; alembic_version.version_num "
            "holds at most 32"
        )


def test_email_model_reconciliation_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0011_email_model_reconciliation.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0011_email_model_reconciliation"' in revision_text
    assert 'down_revision = "0010_language_agnostic_search"' in revision_text
    for retired_table_name in (
        "email_thread_edges",
        "email_instances",
        "email_raws",
        "email_messages",
        "email_threads",
        "provider_accounts",
        "user_accounts",
    ):
        assert f"DROP TABLE IF EXISTS {retired_table_name}" in revision_text
    # Dependents must drop before their FK targets.
    assert revision_text.index("email_thread_edges") < revision_text.index(
        "DROP TABLE IF EXISTS email_messages"
    )
    assert "Intentionally a no-op" in revision_text


def _collect_revision_graph() -> tuple[set[str], set[str]]:
    """Return (all revision ids, all referenced down_revision ids).

    Parses the ``revision``/``down_revision`` assignments textually (no alembic
    import, matching the rest of this module). Handles both the single-string
    ``down_revision = "x"`` form and the merge tuple
    ``down_revision = ("x", "y")`` form, as long as the assignment is on one
    line (the convention this repo follows).
    """
    import re

    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revisions: set[str] = set()
    referenced: set[str] = set()
    for revision_path in sorted(versions_dir.glob("*.py")):
        text = revision_path.read_text()
        rev = re.search(r'^revision = "([^"]+)"', text, re.MULTILINE)
        assert rev, f"no revision id in {revision_path.name}"
        revisions.add(rev.group(1))
        down = re.search(r"^down_revision = (.+)$", text, re.MULTILINE)
        if down:
            referenced.update(re.findall(r'"([^"]+)"', down.group(1)))
    return revisions, referenced


def test_alembic_migration_graph_has_a_single_head():
    """``alembic upgrade head`` (scripts/migrate_db.py) is ambiguous and fails
    with "Multiple head revisions are present" whenever the migration graph has
    more than one head. Two parallel branches from 0009 (the 0010→0013 mainline
    and the 0011_email_read_state branch) once left develop with two heads; this
    guard prevents that regression. A new branch must be reconciled with a merge
    revision before it lands."""
    revisions, referenced = _collect_revision_graph()
    heads = revisions - referenced
    assert len(heads) == 1, (
        f"expected exactly one alembic head, found {sorted(heads)}; add a merge "
        "revision (down_revision tuple of the heads) so `alembic upgrade head` "
        "is unambiguous"
    )


def test_merge_revision_reconciles_email_read_state_branch():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0014_merge_email_read_state.py"
    )
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0014_merge_email_read_state"' in revision_text
    # A merge revision carries a tuple down_revision unifying both prior heads.
    assert "down_revision = (" in revision_text
    assert '"0011_email_read_state"' in revision_text
    assert '"0013_scopeweave_promotion"' in revision_text
    # It is a pure graph merge: no schema operations.
    assert "op.create_table(" not in revision_text
    assert "op.add_column(" not in revision_text
    assert "op.drop_column(" not in revision_text


def test_legacy_email_read_state_branch_defers_check_to_sql(monkeypatch):
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0011_email_read_state.py"
    )
    revision_text = revision_path.read_text()

    # The legacy-table check must be evaluated in SQL (at apply time), not in
    # Python at generation time: offline SQL generation (`alembic upgrade
    # --sql`, a real flag `scripts/migrate_db.py` exposes) has no live
    # connection to introspect with, and the one generated script is meant to
    # later be applied against whichever database a DBA chooses -- a
    # Python-side sa.inspect(op.get_bind()) check can only ever bake in one
    # fixed answer, which is wrong for whichever kind of target it didn't
    # assume (silently skips the real column on a legacy target while
    # `alembic_version` still advances, or crashes outright against a fresh
    # one). upgrade()/downgrade() themselves must contain no such check --
    # only op.execute(<static SQL>) calls -- so this can't regress into
    # either failure mode.
    assert "def upgrade" in revision_text
    upgrade_and_after = revision_text.split("def upgrade", 1)[1]
    assert "sa.inspect(op.get_bind())" not in upgrade_and_after
    assert "context.is_offline_mode()" not in upgrade_and_after

    module = _load_revision_module("0011_email_read_state.py")
    # to_regclass('emails'), not information_schema.tables by bare
    # table_name: the latter ignores search_path and can match an unrelated
    # same-named table in a different accessible schema than the one the
    # unqualified ALTER TABLE below actually resolves to. Checked on the
    # loaded module's own SQL constants, not the raw file text, so this
    # can't be fooled by a comment mentioning either string for context.
    assert "DO $$" in module._UPGRADE_SQL
    assert "DO $$" in module._DOWNGRADE_SQL
    assert "to_regclass('emails')" in module._UPGRADE_SQL
    assert "to_regclass('emails')" in module._DOWNGRADE_SQL
    assert "information_schema.tables" not in module._UPGRADE_SQL
    assert "information_schema.tables" not in module._DOWNGRADE_SQL
    assert "ALTER TABLE emails ADD COLUMN is_read" in module._UPGRADE_SQL
    # CodeRabbit (naruon#1501): downgrade must drop emails.is_read only when
    # this revision's own upgrade created it, not whenever the column merely
    # happens to be present -- an unconditional DROP would also destroy a
    # pre-existing, unrelated is_read column and its data. upgrade() tags the
    # column it creates with a provenance marker comment; downgrade() checks
    # that exact marker via col_description before dropping.
    assert "COMMENT ON COLUMN emails.is_read" in module._UPGRADE_SQL
    assert module._IS_READ_PROVENANCE_MARKER in module._UPGRADE_SQL
    assert "col_description" in module._DOWNGRADE_SQL
    assert module._IS_READ_PROVENANCE_MARKER in module._DOWNGRADE_SQL

    calls = []
    monkeypatch.setattr(module.op, "execute", lambda sql: calls.append(sql))
    module.upgrade()
    module.downgrade()
    assert len(calls) == 2
    assert "ADD COLUMN is_read" in calls[0]
    assert "DROP COLUMN IF EXISTS is_read" in calls[1]


def _run_0011_upgrade(sync_conn) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    module = _load_revision_module("0011_email_read_state.py")
    context = MigrationContext.configure(sync_conn, opts={"target_metadata": None})
    with Operations.context(context):
        module.upgrade()


def _run_0011_downgrade(sync_conn) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    module = _load_revision_module("0011_email_read_state.py")
    context = MigrationContext.configure(sync_conn, opts={"target_metadata": None})
    with Operations.context(context):
        module.downgrade()


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_legacy_email_read_state_real_postgres_smoke():
    """Both directions this migration must get right against a real database:
    a legacy target (still has the ``emails`` table) gets the column added and
    later removed; a fresh-baseline target (no ``emails`` table at all, the
    now-common case) is left untouched rather than erroring.
    """
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        try:
            async with engine.connect() as probe_conn:
                await probe_conn.execute(text("SELECT 1"))
        except (
            ConnectionRefusedError,
            OSError,
            OperationalError,
            asyncpg.CannotConnectNowError,
            asyncpg.InvalidAuthorizationSpecificationError,
            asyncpg.InvalidCatalogNameError,
            asyncpg.InvalidPasswordError,
        ):
            pytest.skip("PostgreSQL smoke path unavailable")

        async with engine.begin() as conn:
            # Fresh-baseline case first, on a connection with no "emails"
            # table anywhere in scope: must no-op, not raise.
            await conn.run_sync(_run_0011_upgrade)

            await conn.execute(
                text("CREATE TEMP TABLE emails (id serial primary key) ON COMMIT DROP")
            )

            def _has_is_read(sync_conn):
                return any(
                    column["name"] == "is_read"
                    for column in inspect(sync_conn).get_columns("emails")
                )

            assert not await conn.run_sync(_has_is_read)
            await conn.run_sync(_run_0011_upgrade)
            assert await conn.run_sync(_has_is_read)

            await conn.run_sync(_run_0011_downgrade)
            assert not await conn.run_sync(_has_is_read)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_legacy_email_read_state_downgrade_preserves_a_preexisting_column():
    """downgrade() must not drop an ``emails.is_read`` column (or its data)
    that predates this revision -- CodeRabbit flagged the earlier
    unconditional ``DROP COLUMN IF EXISTS`` on naruon#1501: since upgrade()'s
    ``NOT EXISTS`` guard already leaves a pre-existing column untouched
    (never adding its own provenance marker to it), downgrade() must
    symmetrically leave it alone too, distinguishing "this revision added it"
    from "it merely happens to be present" via the marker set on the
    ``COMMENT ON COLUMN`` this revision's own upgrade() applies.
    """
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        try:
            async with engine.connect() as probe_conn:
                await probe_conn.execute(text("SELECT 1"))
        except (
            ConnectionRefusedError,
            OSError,
            OperationalError,
            asyncpg.CannotConnectNowError,
            asyncpg.InvalidAuthorizationSpecificationError,
            asyncpg.InvalidCatalogNameError,
            asyncpg.InvalidPasswordError,
        ):
            pytest.skip("PostgreSQL smoke path unavailable")

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TEMP TABLE emails (id serial primary key, "
                    "is_read boolean NOT NULL DEFAULT false) ON COMMIT DROP"
                )
            )
            await conn.execute(text("INSERT INTO emails (is_read) VALUES (false)"))

            def _has_is_read(sync_conn):
                return any(
                    column["name"] == "is_read"
                    for column in inspect(sync_conn).get_columns("emails")
                )

            # upgrade() must be a no-op here: the column already exists, so
            # its NOT EXISTS guard skips both the ADD COLUMN and the marker
            # COMMENT -- this pre-existing column is never tagged as "added
            # by this revision".
            assert await conn.run_sync(_has_is_read)
            await conn.run_sync(_run_0011_upgrade)
            assert await conn.run_sync(_has_is_read)

            # downgrade() must leave the untagged, pre-existing column (and
            # its data) alone rather than dropping it.
            await conn.run_sync(_run_0011_downgrade)
            assert await conn.run_sync(_has_is_read)
            preserved_value = (
                await conn.execute(text("SELECT is_read FROM emails"))
            ).scalar_one()
            assert preserved_value is False
    finally:
        await engine.dispose()


def test_merge_revision_reconciles_newsdom_provider_branch():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0015_merge_newsdom_email_heads.py"
    )
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0015_merge_newsdom_email_heads"' in revision_text
    assert "down_revision = (" in revision_text
    assert '"0010_newsdom_providers"' in revision_text
    assert '"0014_merge_email_read_state"' in revision_text
    assert "op.create_table(" not in revision_text
    assert "op.add_column(" not in revision_text
    assert "op.drop_column(" not in revision_text


def test_merge_revision_reconciles_newsdom_document_and_carddav_heads():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0017_merge_newsdom_carddav_heads.py"
    )
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0017_merge_newsdom_carddav_heads"' in revision_text
    assert "down_revision = (" in revision_text
    assert '"0016_document_org_scope"' in revision_text
    assert '"0015_merge_carddav_accounts"' in revision_text
    assert "op.create_table(" not in revision_text
    assert "op.add_column(" not in revision_text
    assert "op.drop_column(" not in revision_text
