import asyncio
import os
from collections.abc import Sequence

from sqlalchemy import Executable, inspect, text
from sqlalchemy.engine import Connection

from db.models import Base
from db.session import engine

INVALID_EMAIL_BACKFILL_OWNER_IDS = {None, "", "default"}
LEGACY_EMAILS_INDEX = text(
    "CREATE INDEX IF NOT EXISTS ix_emails_owner_date "
    "ON emails (user_id, organization_id, date)"
)


def _static_bootstrap_sql(statement: str) -> Executable:
    # ponytail: repo-authored static bootstrap SQL only; bind params before runtime input.
    return text(statement)


def _explicit_email_backfill_owner_ids() -> tuple[str | None, str | None]:
    user_id = os.environ.get("NARUON_IMPORT_USER_ID")
    organization_id = os.environ.get("NARUON_IMPORT_ORGANIZATION_ID")
    if (
        user_id in INVALID_EMAIL_BACKFILL_OWNER_IDS
        or organization_id in INVALID_EMAIL_BACKFILL_OWNER_IDS
    ):
        return None, None
    return user_id, organization_id


def _get_add_columns_statements() -> list[Executable]:
    return [
        text("ALTER TABLE email_records ADD COLUMN IF NOT EXISTS thread_id varchar"),
        text("ALTER TABLE email_records ADD COLUMN IF NOT EXISTS user_id varchar"),
        text(
            "ALTER TABLE email_records ADD COLUMN IF NOT EXISTS organization_id varchar"
        ),
        text("ALTER TABLE email_records ADD COLUMN IF NOT EXISTS in_reply_to varchar"),
        text('ALTER TABLE email_records ADD COLUMN IF NOT EXISTS "references" varchar'),
        text("ALTER TABLE email_records ADD COLUMN IF NOT EXISTS reply_to varchar"),
        text("ALTER TABLE email_records ADD COLUMN IF NOT EXISTS workspace_id varchar"),
        text(
            "ALTER TABLE email_attachments "
            "ADD COLUMN IF NOT EXISTS attachment_uid varchar"
        ),
        text("ALTER TABLE llm_providers ADD COLUMN IF NOT EXISTS user_id varchar"),
        text(
            "ALTER TABLE llm_providers ADD COLUMN IF NOT EXISTS organization_id varchar"
        ),
        text(
            "ALTER TABLE llm_providers "
            "ADD COLUMN IF NOT EXISTS model_identifier varchar"
        ),
        text(
            "ALTER TABLE llm_providers ADD COLUMN IF NOT EXISTS embedding_model varchar"
        ),
        text("ALTER TABLE webdav_accounts ADD COLUMN IF NOT EXISTS source_uid varchar"),
        text(
            "ALTER TABLE webdav_accounts "
            "ADD COLUMN IF NOT EXISTS organization_id varchar"
        ),
        text(
            "ALTER TABLE webdav_accounts ADD COLUMN IF NOT EXISTS workspace_id varchar"
        ),
        text(
            "ALTER TABLE webdav_accounts "
            "ADD COLUMN IF NOT EXISTS writeback_enabled boolean "
            "NOT NULL DEFAULT false"
        ),
        text("ALTER TABLE webdav_accounts ADD COLUMN IF NOT EXISTS etag_value varchar"),
        text("ALTER TABLE project_folders ADD COLUMN IF NOT EXISTS folder_uid varchar"),
        text(
            "ALTER TABLE project_folders "
            "ADD COLUMN IF NOT EXISTS organization_id varchar"
        ),
        text(
            "ALTER TABLE tenant_configs "
            "ADD COLUMN IF NOT EXISTS organization_id varchar"
        ),
        text(
            "ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS pop3_username varchar"
        ),
        text(
            "ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS pop3_password varchar"
        ),
        text(
            "ALTER TABLE sender_relationships "
            "ADD COLUMN IF NOT EXISTS source_message_id varchar"
        ),
        text(
            "ALTER TABLE sender_relationships "
            "ADD COLUMN IF NOT EXISTS source_thread_id varchar"
        ),
        _static_bootstrap_sql(
            "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS prompt_uid varchar"
        ),
        _static_bootstrap_sql(
            "ALTER TABLE prompt_templates "
            "ADD COLUMN IF NOT EXISTS organization_id varchar"
        ),
        _static_bootstrap_sql(
            "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS workspace_id varchar"
        ),
    ]


def _get_create_tables_statements() -> list[Executable]:
    return [
        text(
            "CREATE TABLE IF NOT EXISTS calendar_writeback_sources ("
            "source_uid varchar PRIMARY KEY, "
            "user_id varchar NOT NULL, "
            "organization_id varchar, "
            "workspace_id varchar NOT NULL, "
            "account_ref varchar, "
            "provider_name varchar NOT NULL, "
            "source_protocol varchar NOT NULL, "
            "source_host varchar NOT NULL, "
            "writeback_enabled boolean NOT NULL DEFAULT false, "
            "etag_value varchar, "
            "created_at timestamptz DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        text(
            "CREATE TABLE IF NOT EXISTS connector_signal_events ("
            "event_uid varchar PRIMARY KEY, "
            "organization_id varchar NOT NULL, "
            "workspace_id varchar NOT NULL, "
            "signal_key varchar NOT NULL, "
            "state_code varchar NOT NULL, "
            "detail_text text, "
            "observed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        text(
            "CREATE TABLE IF NOT EXISTS security_audit_events ("
            "event_uid varchar PRIMARY KEY, "
            "actor_user_id varchar NOT NULL, "
            "actor_role varchar NOT NULL, "
            "organization_id varchar, "
            "workspace_id varchar NOT NULL, "
            "event_action varchar NOT NULL, "
            "resource_type varchar NOT NULL, "
            "resource_uid varchar, "
            "evidence_source varchar NOT NULL, "
            "detail_text text, "
            "observed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        text(
            "CREATE TABLE IF NOT EXISTS workflow_definitions ("
            "workflow_uid varchar PRIMARY KEY, "
            "organization_id varchar NOT NULL, "
            "workspace_id varchar NOT NULL, "
            "user_id varchar NOT NULL, "
            "workflow_name varchar NOT NULL, "
            "workflow_description text, "
            "steps_json json NOT NULL DEFAULT '[]'::json, "
            "state_code varchar NOT NULL DEFAULT 'draft', "
            "created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        text(
            "CREATE TABLE IF NOT EXISTS agent_run_records ("
            "run_uid varchar PRIMARY KEY, "
            "workflow_uid varchar NOT NULL REFERENCES workflow_definitions(workflow_uid), "
            "organization_id varchar NOT NULL, "
            "workspace_id varchar NOT NULL, "
            "user_id varchar NOT NULL, "
            "status_code varchar NOT NULL DEFAULT 'pending', "
            "started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "completed_at timestamptz, "
            "result_summary text"
            ")"
        ),
    ]


def _get_create_indexes_statements() -> list[Executable]:
    return [
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_user_id "
            "ON email_records (user_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_organization_id "
            "ON email_records (organization_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_owner_date "
            "ON email_records (user_id, organization_id, date)"
        ),
        LEGACY_EMAILS_INDEX,
        text(
            "CREATE INDEX IF NOT EXISTS ix_sender_relationships_owner_source "
            "ON sender_relationships "
            "(user_id, organization_id, source_message_id, source_thread_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_llm_providers_user_id "
            "ON llm_providers (user_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_llm_providers_organization_id "
            "ON llm_providers (organization_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_calendar_writeback_sources_scope "
            "ON calendar_writeback_sources "
            "(user_id, organization_id, source_protocol)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_connector_signal_events_scope_time "
            "ON connector_signal_events "
            "(organization_id, workspace_id, observed_at)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_security_audit_events_scope_time "
            "ON security_audit_events "
            "(organization_id, workspace_id, observed_at)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_security_audit_events_actor_scope "
            "ON security_audit_events "
            "(actor_user_id, organization_id, workspace_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_templates_owner_scope "
            "ON prompt_templates (created_by, organization_id, workspace_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_templates_shared_scope "
            "ON prompt_templates (organization_id, workspace_id, is_shared)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_workflow_definitions_scope_time "
            "ON workflow_definitions (organization_id, workspace_id, updated_at)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_workflow_definitions_owner_scope "
            "ON workflow_definitions "
            "(user_id, organization_id, workspace_id, updated_at)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_run_records_scope_time "
            "ON agent_run_records (organization_id, workspace_id, started_at)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_run_records_workflow_uid "
            "ON agent_run_records (workflow_uid)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_run_records_owner_scope "
            "ON agent_run_records "
            "(user_id, organization_id, workspace_id, started_at)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_run_records_workflow_time "
            "ON agent_run_records (workflow_uid, started_at)"
        ),
    ]


def _get_update_webdav_accounts_statements() -> list[Executable]:
    return [
        text(
            "UPDATE webdav_accounts "
            "SET source_uid = 'webdav_src_' || encode(sha256(("
            "random()::text || ':' || clock_timestamp()::text || ':' || "
            "user_id || ':' || server_url"
            ")::bytea), 'hex') "
            "WHERE source_uid IS NULL OR source_uid = ''"
        ),
        text(
            "UPDATE webdav_accounts "
            "SET workspace_id = CASE "
            "WHEN organization_id IS NOT NULL "
            "THEN 'workspace-' || organization_id "
            "ELSE 'workspace-' || user_id END "
            "WHERE workspace_id IS NULL OR workspace_id = ''"
        ),
        text("ALTER TABLE webdav_accounts ALTER COLUMN source_uid SET NOT NULL"),
        text("ALTER TABLE webdav_accounts ALTER COLUMN workspace_id SET NOT NULL"),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_webdav_accounts_source_uid "
            "ON webdav_accounts (source_uid)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_webdav_accounts_organization_id "
            "ON webdav_accounts (organization_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_webdav_accounts_workspace_scope "
            "ON webdav_accounts (user_id, organization_id, workspace_id)"
        ),
    ]


def _get_update_project_folders_statements() -> list[Executable]:
    return [
        text(
            "UPDATE project_folders "
            "SET folder_uid = 'webdav_folder_' || encode(sha256(("
            "random()::text || ':' || clock_timestamp()::text || ':' || "
            "user_id || ':' || project_name || ':' || webdav_path"
            ")::bytea), 'hex') "
            "WHERE folder_uid IS NULL OR folder_uid = ''"
        ),
        text("ALTER TABLE project_folders ALTER COLUMN folder_uid SET NOT NULL"),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_project_folders_folder_uid "
            "ON project_folders (folder_uid)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_project_folders_owner_scope "
            "ON project_folders (user_id, organization_id)"
        ),
    ]


def _get_update_email_workspace_statements() -> list[Executable]:
    return [
        text(
            "UPDATE email_records "
            "SET workspace_id = 'workspace-' || organization_id "
            "WHERE workspace_id IS NULL OR workspace_id = ''"
        ),
        text("ALTER TABLE email_records ALTER COLUMN workspace_id SET NOT NULL"),
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_workspace_id "
            "ON email_records (workspace_id)"
        ),
        # uq_email_records_owner_message_id (created earlier by validation,
        # before workspace_id is guaranteed populated) is stricter than
        # Alembic 0020's uq_emails_workspace_message: it forbids the same
        # message_id from ever existing in two different workspaces of the
        # same owner. Drop it now that workspace_id is backfilled and
        # non-null, and replace it with the same workspace-scoped identity so
        # a bootstrap-provisioned database doesn't silently diverge from the
        # Alembic-managed schema it exists to mirror. Historical bootstrap
        # runs always created this as a plain index (see
        # _get_validation_and_final_indexes_statements), but a constraint
        # drop is included too in case an even older schema shape used one.
        text(
            "ALTER TABLE email_records "
            "DROP CONSTRAINT IF EXISTS uq_email_records_owner_message_id"
        ),
        text("DROP INDEX IF EXISTS uq_email_records_owner_message_id"),
        # uq_emails_owner_message_id is the DIFFERENT owner-only identity name
        # Alembic's own ORM metadata (and 0020_email_workspace_scope.py, as
        # _OLD_EMAIL_IDENTITY) used before workspace scoping. A database
        # provisioned via Base.metadata.create_all()
        # (0001_initial_control_plane.py) before the workspace-scoped model
        # landed carries this name instead of the bootstrap-specific one
        # above -- drop it too, or such a database keeps the stricter
        # 3-column identity forever.
        text(
            "ALTER TABLE email_records "
            "DROP CONSTRAINT IF EXISTS uq_emails_owner_message_id"
        ),
        text("DROP INDEX IF EXISTS uq_emails_owner_message_id"),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_emails_workspace_message "
            "ON email_records (user_id, organization_id, workspace_id, message_id)"
        ),
    ]


def _get_update_email_attachment_statements() -> list[Executable]:
    return [
        text(
            "UPDATE email_attachments "
            "SET attachment_uid = 'attachment_' || encode(sha256(("
            "random()::text || ':' || clock_timestamp()::text || ':' || "
            "id::text"
            ")::bytea), 'hex') "
            "WHERE attachment_uid IS NULL OR attachment_uid = ''"
        ),
        text("ALTER TABLE email_attachments ALTER COLUMN attachment_uid SET NOT NULL"),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_email_attachments_uid "
            "ON email_attachments (attachment_uid)"
        ),
    ]


def _get_update_prompt_template_statements() -> list[Executable]:
    return [
        _static_bootstrap_sql(
            "UPDATE prompt_templates "
            "SET prompt_uid = 'prompt_' || encode(sha256(("
            "random()::text || ':' || clock_timestamp()::text || ':' || "
            "created_by || ':' || title"
            ")::bytea), 'hex') "
            "WHERE prompt_uid IS NULL OR prompt_uid = ''"
        ),
        _static_bootstrap_sql(
            "ALTER TABLE prompt_templates ALTER COLUMN prompt_uid SET NOT NULL"
        ),
        _static_bootstrap_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompt_templates_prompt_uid "
            "ON prompt_templates (prompt_uid)"
        ),
    ]


def _get_drop_constraints_and_indexes_statements() -> list[Executable]:
    return [
        text(
            "ALTER TABLE email_records DROP CONSTRAINT IF EXISTS emails_message_id_key"
        ),
        text(
            "ALTER TABLE tenant_configs "
            "DROP CONSTRAINT IF EXISTS tenant_configs_user_id_key"
        ),
        text(
            "ALTER TABLE sender_relationships "
            "DROP CONSTRAINT IF EXISTS uq_sender_relationships_user_email"
        ),
        text(
            "ALTER TABLE llm_providers DROP CONSTRAINT IF EXISTS llm_providers_name_key"
        ),
        text("DROP INDEX IF EXISTS ix_llm_providers_name"),
        text("DROP INDEX IF EXISTS ix_tenant_configs_user_id"),
        text("DROP INDEX IF EXISTS ix_email_records_message_id"),
    ]


def _get_create_new_indexes_statements() -> list[Executable]:
    return [
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_message_id "
            "ON email_records (message_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_tenant_configs_user_id "
            "ON tenant_configs (user_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_tenant_configs_owner_scope "
            "ON tenant_configs (user_id, organization_id)"
        ),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_configs_owner_scope "
            "ON tenant_configs (user_id, coalesce(organization_id, ''))"
        ),
    ]


def _get_backfill_statements(
    backfill_user_id: str, backfill_organization_id: str
) -> list[Executable]:
    return [
        text(
            "UPDATE email_records "
            "SET user_id = :user_id, "
            "organization_id = :organization_id "
            "WHERE user_id IS NULL AND organization_id IS NULL"
        ).bindparams(
            user_id=backfill_user_id,
            organization_id=backfill_organization_id,
        ),
        text(
            "UPDATE llm_providers "
            "SET user_id = :user_id, "
            "organization_id = :organization_id "
            "WHERE user_id IS NULL AND organization_id IS NULL"
        ).bindparams(
            user_id=backfill_user_id,
            organization_id=backfill_organization_id,
        ),
        text(
            "UPDATE project_folders "
            "SET organization_id = :organization_id "
            "WHERE user_id = :user_id AND organization_id IS NULL"
        ).bindparams(
            user_id=backfill_user_id,
            organization_id=backfill_organization_id,
        ),
        text(
            "UPDATE tenant_configs "
            "SET organization_id = :organization_id "
            "WHERE user_id = :user_id AND organization_id IS NULL"
        ).bindparams(
            user_id=backfill_user_id,
            organization_id=backfill_organization_id,
        ),
    ]


def _get_validation_and_final_indexes_statements() -> list[Executable]:
    return [
        text(
            "DO $$ "
            "BEGIN "
            "IF EXISTS ("
            "SELECT 1 FROM email_records "
            "WHERE user_id IS NULL OR organization_id IS NULL"
            ") THEN "
            "RAISE EXCEPTION "
            "'Existing email_records require explicit non-default "
            "NARUON_IMPORT_USER_ID and NARUON_IMPORT_ORGANIZATION_ID "
            "before owner backfill'; "
            "END IF; "
            "END $$"
        ),
        text("ALTER TABLE email_records ALTER COLUMN user_id SET NOT NULL"),
        text("ALTER TABLE email_records ALTER COLUMN organization_id SET NOT NULL"),
        text(
            "DO $$ "
            "BEGIN "
            "IF EXISTS ("
            "SELECT 1 FROM llm_providers "
            "WHERE user_id IS NULL OR organization_id IS NULL"
            ") THEN "
            "RAISE EXCEPTION "
            "'Existing llm providers require explicit non-default "
            "NARUON_IMPORT_USER_ID and NARUON_IMPORT_ORGANIZATION_ID "
            "before owner backfill'; "
            "END IF; "
            "END $$"
        ),
        text("ALTER TABLE llm_providers ALTER COLUMN user_id SET NOT NULL"),
        text("ALTER TABLE llm_providers ALTER COLUMN organization_id SET NOT NULL"),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_providers_org_name "
            "ON llm_providers (organization_id, name)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_thread_id "
            "ON email_records (thread_id)"
        ),
        text(
            "CREATE INDEX IF NOT EXISTS ix_email_records_date ON email_records (date)"
        ),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_sender_relationships_scope_source "
            "ON sender_relationships "
            "(user_id, coalesce(organization_id, ''), sender_email, "
            "coalesce(source_message_id, ''), coalesce(source_thread_id, ''))"
        ),
        text(
            "WITH ranked_tasks AS ("
            "SELECT ctid, row_number() OVER ("
            "PARTITION BY user_id, coalesce(organization_id, ''), "
            "source_type, email_id "
            "ORDER BY updated_at DESC NULLS LAST, "
            "created_at DESC NULLS LAST, task_id DESC"
            ") AS row_rank "
            "FROM ticket_tasks "
            "WHERE source_type = 'reply_sla' AND email_id IS NOT NULL"
            ") "
            "DELETE FROM ticket_tasks "
            "USING ranked_tasks "
            "WHERE ticket_tasks.ctid = ranked_tasks.ctid "
            "AND ranked_tasks.row_rank > 1"
        ),
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_ticket_tasks_reply_sla_email "
            "ON ticket_tasks "
            "(user_id, coalesce(organization_id, ''), source_type, email_id) "
            "WHERE source_type = 'reply_sla' AND email_id IS NOT NULL"
        ),
    ]


def schema_backfill_sql() -> list[Executable]:
    statements: list[Executable] = []

    statements.extend(_get_add_columns_statements())
    statements.extend(_get_create_tables_statements())
    statements.extend(_get_create_indexes_statements())
    statements.extend(_get_update_webdav_accounts_statements())
    statements.extend(_get_update_project_folders_statements())
    statements.extend(_get_update_prompt_template_statements())
    statements.extend(_get_update_email_attachment_statements())
    statements.extend(_get_drop_constraints_and_indexes_statements())
    statements.extend(_get_create_new_indexes_statements())

    owner_ids = _explicit_email_backfill_owner_ids()
    backfill_user_id, backfill_organization_id = owner_ids
    if backfill_user_id is not None and backfill_organization_id is not None:
        statements.extend(
            _get_backfill_statements(backfill_user_id, backfill_organization_id)
        )

    statements.extend(_get_validation_and_final_indexes_statements())

    # email_records.organization_id is only guaranteed NOT NULL once the
    # validation above passes, so the workspace_id backfill (derived from
    # organization_id) must run after it, not alongside the other
    # independent per-table backfills above.
    statements.extend(_get_update_email_workspace_statements())

    return statements


def execute_schema_backfill(
    conn: Connection, statements: Sequence[Executable] | None = None
) -> None:
    statements = schema_backfill_sql() if statements is None else statements
    legacy_emails_exists = inspect(conn).has_table("emails")
    for statement in statements:
        if statement is LEGACY_EMAILS_INDEX and not legacy_emails_exists:
            continue
        conn.execute(statement)


async def bootstrap_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(execute_schema_backfill)


if __name__ == "__main__":
    asyncio.run(bootstrap_db())
