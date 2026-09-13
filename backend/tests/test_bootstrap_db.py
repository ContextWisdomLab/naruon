import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import settings
from db.models import Base
from scripts.bootstrap_db import (
    LEGACY_EMAILS_INDEX,
    execute_schema_backfill,
    schema_backfill_sql,
)
from db.models import (
    AgentRunRecord,
    CalendarWritebackSource,
    ConnectorSignalEvent,
    Email,
    ProjectFolder,
    PromptTemplate,
    SecurityAuditEvent,
    SenderRelationship,
    TenantConfig,
    TicketTask,
    WebdavAccount,
    WorkflowDefinition,
)


def _get_schema_statements(monkeypatch):
    monkeypatch.delenv("NARUON_IMPORT_USER_ID", raising=False)
    monkeypatch.delenv("NARUON_IMPORT_ORGANIZATION_ID", raising=False)
    return [str(statement).lower() for statement in schema_backfill_sql()]


def _execute_schema_backfill(sync_conn):
    execute_schema_backfill(sync_conn)


def test_schema_backfill_adds_email_columns(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table email_records add column if not exists reply_to" in statement
        for statement in statements
    )
    assert any(
        "alter table email_records add column if not exists user_id" in statement
        for statement in statements
    )
    assert any(
        "alter table email_records add column if not exists organization_id"
        in statement
        for statement in statements
    )
    assert any(
        "alter table email_records add column if not exists thread_id" in statement
        for statement in statements
    )
    assert any(
        "alter table email_records add column if not exists in_reply_to" in statement
        for statement in statements
    )
    assert any(
        'alter table email_records add column if not exists "references"' in statement
        for statement in statements
    )
    assert not any(
        "update email_records set user_id" in statement for statement in statements
    )
    assert not any(
        "update email_records set organization_id" in statement
        for statement in statements
    )
    assert any(
        "existing email_records require explicit non-default" in statement
        for statement in statements
    )


def test_schema_backfill_adds_sender_relationship_columns_and_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table sender_relationships add column if not exists source_message_id"
        in statement
        for statement in statements
    )
    assert any(
        "alter table sender_relationships add column if not exists source_thread_id"
        in statement
        for statement in statements
    )
    assert any(
        "drop constraint if exists uq_sender_relationships_user_email" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_sender_relationships_owner_source" in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_sender_relationships_scope_source"
        in statement
        for statement in statements
    )


def test_schema_backfill_adds_email_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "create index if not exists ix_email_records_user_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_email_records_organization_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_email_records_owner_date" in statement
        and "user_id, organization_id, date" in statement
        for statement in statements
    )
    assert any(
        "drop index if exists ix_email_records_message_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_email_records_message_id" in statement
        and "unique" not in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_emails_workspace_message" in statement
        for statement in statements
    )
    assert any(
        "user_id, organization_id, workspace_id, message_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_email_records_thread_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_email_records_date" in statement
        for statement in statements
    )


def test_schema_backfill_adds_llm_provider_columns_and_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table llm_providers add column if not exists user_id" in statement
        for statement in statements
    )
    assert any(
        "alter table llm_providers add column if not exists organization_id"
        in statement
        for statement in statements
    )
    assert any(
        "alter table llm_providers add column if not exists model_identifier"
        in statement
        for statement in statements
    )
    assert any(
        "alter table llm_providers add column if not exists embedding_model"
        in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_llm_providers_organization_id" in statement
        for statement in statements
    )
    assert any(
        "existing llm providers require explicit non-default" in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_llm_providers_org_name" in statement
        for statement in statements
    )
    assert any(
        "drop index if exists ix_llm_providers_name" in statement
        for statement in statements
    )


def test_schema_backfill_adds_prompt_template_scope_columns_and_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table prompt_templates add column if not exists prompt_uid" in statement
        for statement in statements
    )
    assert any(
        "alter table prompt_templates add column if not exists organization_id"
        in statement
        for statement in statements
    )
    assert any(
        "alter table prompt_templates add column if not exists workspace_id"
        in statement
        for statement in statements
    )
    assert any(
        "update prompt_templates set prompt_uid" in statement
        and "prompt_" in statement
        and "encode(sha256" in statement
        and "bytea" in statement
        and "hex" in statement
        for statement in statements
    )
    assert any(
        "alter table prompt_templates alter column prompt_uid set not null" in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_prompt_templates_prompt_uid" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_prompt_templates_owner_scope" in statement
        and "created_by, organization_id, workspace_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_prompt_templates_shared_scope" in statement
        and "organization_id, workspace_id, is_shared" in statement
        for statement in statements
    )


def test_schema_backfill_creates_calendar_writeback_sources_table(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "create table if not exists calendar_writeback_sources" in statement
        for statement in statements
    )
    assert any(
        "source_uid varchar primary key" in statement for statement in statements
    )
    assert any("workspace_id varchar not null" in statement for statement in statements)
    assert any(
        "provider_name varchar not null" in statement for statement in statements
    )
    assert any(
        "source_protocol varchar not null" in statement for statement in statements
    )
    assert any("source_host varchar not null" in statement for statement in statements)
    assert any(
        "writeback_enabled boolean not null default false" in statement
        for statement in statements
    )
    assert any("etag_value varchar" in statement for statement in statements)
    assert any(
        "create index if not exists ix_calendar_writeback_sources_scope" in statement
        for statement in statements
    )


def test_schema_backfill_creates_security_audit_events_table(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "create table if not exists security_audit_events" in statement
        for statement in statements
    )
    assert any(
        "actor_user_id varchar not null" in statement for statement in statements
    )
    assert any("event_action varchar not null" in statement for statement in statements)
    assert any("resource_uid varchar" in statement for statement in statements)


def test_schema_backfill_creates_ai_hub_workflow_tables(monkeypatch):
    statements = _get_schema_statements(monkeypatch)

    assert any(
        "create table if not exists workflow_definitions" in statement
        for statement in statements
    )
    assert any(
        "workflow_uid varchar primary key" in statement for statement in statements
    )
    assert any("steps_json json not null" in statement for statement in statements)
    assert any(
        "create table if not exists agent_run_records" in statement
        for statement in statements
    )
    assert any("run_uid varchar primary key" in statement for statement in statements)
    assert any(
        "references workflow_definitions(workflow_uid)" in statement
        for statement in statements
    )
    assert any(
        "ix_workflow_definitions_scope_time" in statement for statement in statements
    )
    assert any(
        "ix_workflow_definitions_owner_scope" in statement
        and "user_id, organization_id, workspace_id, updated_at" in statement
        for statement in statements
    )
    assert any(
        "ix_agent_run_records_scope_time" in statement for statement in statements
    )
    assert any(
        "ix_agent_run_records_workflow_uid" in statement and "workflow_uid" in statement
        for statement in statements
    )
    assert any(
        "ix_agent_run_records_owner_scope" in statement
        and "user_id, organization_id, workspace_id, started_at" in statement
        for statement in statements
    )
    assert any(
        "ix_agent_run_records_workflow_time" in statement for statement in statements
    )


def test_schema_backfill_adds_webdav_account_columns_and_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table webdav_accounts add column if not exists source_uid" in statement
        for statement in statements
    )
    assert any(
        "alter table webdav_accounts add column if not exists organization_id"
        in statement
        for statement in statements
    )
    assert any(
        "alter table webdav_accounts add column if not exists workspace_id" in statement
        for statement in statements
    )
    assert any(
        "alter table webdav_accounts add column if not exists writeback_enabled"
        in statement
        for statement in statements
    )
    assert any(
        "alter table webdav_accounts add column if not exists etag_value" in statement
        for statement in statements
    )
    assert any(
        "update webdav_accounts set source_uid" in statement
        and "webdav_src_" in statement
        and "encode(sha256" in statement
        and "bytea" in statement
        and "hex" in statement
        and "random()::text" in statement
        and "clock_timestamp()::text" in statement
        for statement in statements
    )
    assert not any("account_id::text" in statement for statement in statements)
    assert any(
        "update webdav_accounts set workspace_id" in statement
        and "'workspace-' || organization_id" in statement
        for statement in statements
    )
    assert any(
        "alter table webdav_accounts alter column source_uid set not null" in statement
        for statement in statements
    )
    assert any(
        "alter table webdav_accounts alter column workspace_id set not null"
        in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_webdav_accounts_source_uid" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_webdav_accounts_organization_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_webdav_accounts_workspace_scope" in statement
        and "user_id, organization_id, workspace_id" in statement
        for statement in statements
    )


def test_schema_backfill_adds_project_folder_columns_and_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table project_folders add column if not exists folder_uid" in statement
        for statement in statements
    )
    assert any(
        "alter table project_folders add column if not exists organization_id"
        in statement
        for statement in statements
    )
    assert any(
        "update project_folders set folder_uid" in statement
        and "webdav_folder_" in statement
        and "encode(sha256" in statement
        and "bytea" in statement
        and "hex" in statement
        and "random()::text" in statement
        and "clock_timestamp()::text" in statement
        for statement in statements
    )
    assert any(
        "alter table project_folders alter column folder_uid set not null" in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_project_folders_folder_uid" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_project_folders_owner_scope" in statement
        and "user_id, organization_id" in statement
        for statement in statements
    )


def test_schema_backfill_adds_email_workspace_column_and_index(monkeypatch):
    """A pre-existing database bootstrapped via create_all/backfill (not Alembic)
    must gain email_records.workspace_id too, or every workspace-scoped email
    query fails after deployment (see Alembic 0020_email_workspace_scope)."""
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table email_records add column if not exists workspace_id" in statement
        for statement in statements
    )
    assert any(
        "update email_records set workspace_id" in statement
        and "'workspace-' || organization_id" in statement
        for statement in statements
    )
    assert any(
        "alter table email_records alter column workspace_id set not null" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_email_records_workspace_id" in statement
        and "email_records (workspace_id)" in statement
        for statement in statements
    )


def test_schema_backfill_replaces_owner_only_email_uniqueness_with_workspace_scope(
    monkeypatch,
):
    """uq_email_records_owner_message_id (user_id, organization_id, message_id)
    predates workspace scoping and is stricter than Alembic 0020's replacement
    identity: it silently forbids the same message_id from ever existing in two
    different workspaces of the same owner, which Alembic 0020 now explicitly
    allows via uq_emails_workspace_message. A bootstrap-provisioned database
    must drop the owner-only shape (as either a plain index or a named
    constraint, since historical bootstrap runs may have produced either) and
    replace it with the same workspace-scoped identity, or it silently diverges
    from the Alembic-managed schema it exists to mirror."""
    statements = _get_schema_statements(monkeypatch)

    workspace_not_null = next(
        i
        for i, statement in enumerate(statements)
        if "alter table email_records alter column workspace_id set not null"
        in statement
    )
    drop_constraint_index = next(
        i
        for i, statement in enumerate(statements)
        if "alter table email_records drop constraint if exists "
        "uq_email_records_owner_message_id" in statement
    )
    drop_index_index = next(
        i
        for i, statement in enumerate(statements)
        if statement
        == "drop index if exists uq_email_records_owner_message_id"
    )
    new_create_index = next(
        i
        for i, statement in enumerate(statements)
        if "create unique index if not exists "
        "uq_emails_workspace_message" in statement
        and "user_id, organization_id, workspace_id, message_id" in statement
    )

    # The owner-only index must still exist earlier (validation runs before
    # workspace_id is guaranteed populated) but must be dropped and replaced
    # only after workspace_id is backfilled and non-null.
    assert workspace_not_null < drop_constraint_index
    assert drop_index_index != new_create_index

    # uq_emails_owner_message_id is the DIFFERENT owner-only identity name
    # Alembic's own ORM metadata (and 0020_email_workspace_scope.py) used
    # before workspace scoping -- a database provisioned via
    # Base.metadata.create_all() (0001_initial_control_plane.py) before the
    # workspace-scoped model landed carries this name, not the bootstrap
    # script's own uq_email_records_owner_message_id. Bootstrap must drop
    # both legacy names (constraint and index forms) or such a database
    # keeps the stricter 3-column identity forever.
    drop_alembic_constraint_index = next(
        i
        for i, statement in enumerate(statements)
        if "alter table email_records drop constraint if exists "
        "uq_emails_owner_message_id" in statement
    )
    drop_alembic_index_index = next(
        i
        for i, statement in enumerate(statements)
        if statement == "drop index if exists uq_emails_owner_message_id"
    )
    assert workspace_not_null < drop_alembic_constraint_index
    assert drop_alembic_index_index != new_create_index
    assert workspace_not_null < new_create_index


def test_schema_backfill_adds_attachment_uid_column_and_index(monkeypatch):
    """A pre-existing database bootstrapped via create_all/backfill (not Alembic)
    must gain email_attachments.attachment_uid too, or every opaque-id
    attachment lookup fails after deployment (see Alembic 0019_attachment_uid)."""
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table email_attachments add column if not exists attachment_uid"
        in statement
        for statement in statements
    )
    assert any(
        "update email_attachments set attachment_uid" in statement
        and "attachment_" in statement
        and "encode(sha256" in statement
        and "bytea" in statement
        and "hex" in statement
        and "random()::text" in statement
        and "clock_timestamp()::text" in statement
        for statement in statements
    )
    assert any(
        "alter table email_attachments alter column attachment_uid set not null"
        in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_email_attachments_uid" in statement
        for statement in statements
    )


def test_schema_backfill_adds_tenant_config_columns_and_indexes(monkeypatch):
    statements = _get_schema_statements(monkeypatch)
    assert any(
        "alter table tenant_configs add column if not exists pop3_username" in statement
        for statement in statements
    )
    assert any(
        "alter table tenant_configs add column if not exists pop3_password" in statement
        for statement in statements
    )
    assert any(
        "alter table tenant_configs add column if not exists organization_id"
        in statement
        for statement in statements
    )
    assert any(
        "alter table tenant_configs drop constraint if exists tenant_configs_user_id_key"
        in statement
        for statement in statements
    )
    assert any(
        "drop index if exists ix_tenant_configs_user_id" in statement
        for statement in statements
    )
    assert any(
        "create index if not exists ix_tenant_configs_owner_scope" in statement
        and "user_id, organization_id" in statement
        for statement in statements
    )
    assert any(
        "create unique index if not exists uq_tenant_configs_owner_scope" in statement
        and "coalesce(organization_id, '')" in statement
        for statement in statements
    )


def test_schema_backfill_uses_only_explicit_non_default_owner_ids(monkeypatch):
    monkeypatch.setenv("NARUON_IMPORT_USER_ID", "import-user")
    monkeypatch.setenv("NARUON_IMPORT_ORGANIZATION_ID", "import-org")

    statements = [str(statement).lower() for statement in schema_backfill_sql()]

    assert any(
        "update email_records" in statement
        and "set user_id" in statement
        and "organization_id = :organization_id" in statement
        and "where user_id is null and organization_id is null" in statement
        for statement in statements
    )
    # email_records also gets a separate, unrelated workspace_id backfill
    # (see test_schema_backfill_adds_email_workspace_column_and_index), so
    # this counts only the owner-backfill statement specifically, not every
    # "update email_records" statement.
    assert (
        sum(
            "update email_records" in statement
            and "set user_id" in statement
            and "organization_id = :organization_id" in statement
            and "where user_id is null and organization_id is null" in statement
            for statement in statements
        )
        == 1
    )
    assert any(
        "update llm_providers" in statement
        and "set user_id" in statement
        and "organization_id = :organization_id" in statement
        and "where user_id is null and organization_id is null" in statement
        for statement in statements
    )
    assert sum("update llm_providers" in statement for statement in statements) == 1
    assert any(
        "update tenant_configs" in statement
        and "set organization_id = :organization_id" in statement
        and "where user_id = :user_id and organization_id is null" in statement
        for statement in statements
    )
    assert sum("update tenant_configs" in statement for statement in statements) == 1


def test_schema_backfill_stops_partially_owned_legacy_rows(monkeypatch):
    monkeypatch.setenv("NARUON_IMPORT_USER_ID", "import-user")
    monkeypatch.setenv("NARUON_IMPORT_ORGANIZATION_ID", "import-org")

    statements = [str(statement).lower() for statement in schema_backfill_sql()]

    assert any(
        "where user_id is null and organization_id is null" in statement
        for statement in statements
    )
    assert any(
        "existing email_records require explicit non-default" in statement
        for statement in statements
    )


def test_schema_backfill_rejects_default_owner_ids(monkeypatch):
    monkeypatch.setenv("NARUON_IMPORT_USER_ID", "default")
    monkeypatch.setenv("NARUON_IMPORT_ORGANIZATION_ID", "default")

    statements = [str(statement).lower() for statement in schema_backfill_sql()]

    assert not any(
        "update email_records set user_id" in statement for statement in statements
    )
    assert not any(
        "update email_records set organization_id" in statement
        for statement in statements
    )


def test_sender_relationship_model_declares_source_unique_index():
    indexes = {index.name: index for index in SenderRelationship.__table__.indexes}

    source_index = indexes["uq_sender_relationships_scope_source"]

    assert source_index.unique is True
    expression_text = " ".join(
        str(expression).lower() for expression in source_index.expressions
    )
    assert "user_id" in expression_text
    assert "coalesce" in expression_text
    assert "organization_id" in expression_text
    assert "sender_email" in expression_text
    assert "source_message_id" in expression_text
    assert "source_thread_id" in expression_text


def test_email_model_declares_owner_date_index():
    indexes = {index.name: index for index in Email.__table__.indexes}

    owner_date_index = indexes["ix_email_records_owner_date"]

    assert owner_date_index.unique is False
    assert [column.name for column in owner_date_index.columns] == [
        "user_id",
        "organization_id",
        "date",
    ]


def test_tenant_config_model_declares_owner_scope_unique_index():
    indexes = {index.name: index for index in TenantConfig.__table__.indexes}

    source_index = indexes["uq_tenant_configs_owner_scope"]

    assert source_index.unique is True
    expression_text = " ".join(
        str(expression).lower() for expression in source_index.expressions
    )
    assert "user_id" in expression_text
    assert "coalesce" in expression_text
    assert "organization_id" in expression_text


def test_ticket_task_reply_sla_unique_index_is_bootstrapped():
    statements = [str(statement).lower() for statement in schema_backfill_sql()]
    indexes = {index.name: index for index in TicketTask.__table__.indexes}
    dedupe_statement_index = next(
        index
        for index, statement in enumerate(statements)
        if "with ranked_tasks as" in statement
        and "delete from ticket_tasks" in statement
        and "source_type = 'reply_sla'" in statement
        and "task_id desc" in statement
        and "row_rank > 1" in statement
    )
    unique_index_statement_index = next(
        index
        for index, statement in enumerate(statements)
        if "create unique index if not exists uq_ticket_tasks_reply_sla_email"
        in statement
    )

    assert "uq_ticket_tasks_reply_sla_email" in indexes
    assert indexes["uq_ticket_tasks_reply_sla_email"].unique is True
    assert dedupe_statement_index < unique_index_statement_index
    assert any(
        "create unique index if not exists uq_ticket_tasks_reply_sla_email" in statement
        and "where source_type = 'reply_sla'" in statement
        for statement in statements
    )


def test_calendar_writeback_source_model_uses_two_word_names():
    assert CalendarWritebackSource.__tablename__ == "calendar_writeback_sources"
    column_names = {column.name for column in CalendarWritebackSource.__table__.columns}

    assert column_names == {
        "source_uid",
        "user_id",
        "organization_id",
        "workspace_id",
        "account_ref",
        "provider_name",
        "source_protocol",
        "source_host",
        "writeback_enabled",
        "etag_value",
        "created_at",
    }
    assert all("_" in column_name for column_name in column_names)


def test_webdav_account_model_exposes_opaque_source_uid():
    column_names = {column.name for column in WebdavAccount.__table__.columns}

    assert "source_uid" in column_names
    assert "organization_id" in column_names
    assert "writeback_enabled" in column_names
    assert WebdavAccount.__table__.c.source_uid.nullable is False
    assert WebdavAccount.__table__.c.source_uid.unique is True
    assert WebdavAccount.__table__.c.writeback_enabled.nullable is False


def test_project_folder_model_exposes_opaque_folder_uid():
    column_names = {column.name for column in ProjectFolder.__table__.columns}

    assert "folder_uid" in column_names
    assert "organization_id" in column_names
    assert ProjectFolder.__table__.c.folder_uid.nullable is False
    assert ProjectFolder.__table__.c.folder_uid.unique is True


def test_prompt_template_model_declares_scope_and_opaque_uid():
    column_names = {column.name for column in PromptTemplate.__table__.columns}
    index_names = {index.name for index in PromptTemplate.__table__.indexes}

    assert "prompt_uid" in column_names
    assert "organization_id" in column_names
    assert "workspace_id" in column_names
    assert PromptTemplate.__table__.c.prompt_uid.nullable is False
    assert PromptTemplate.__table__.c.prompt_uid.unique is True
    assert "ix_prompt_templates_owner_scope" in index_names
    assert "ix_prompt_templates_shared_scope" in index_names


def test_connector_signal_event_model_uses_two_word_names():
    assert ConnectorSignalEvent.__tablename__ == "connector_signal_events"
    column_names = {column.name for column in ConnectorSignalEvent.__table__.columns}

    assert column_names == {
        "event_uid",
        "organization_id",
        "workspace_id",
        "signal_key",
        "state_code",
        "detail_text",
        "observed_at",
    }
    assert all("_" in column_name for column_name in column_names)


def test_security_audit_event_model_uses_two_word_names():
    assert SecurityAuditEvent.__tablename__ == "security_audit_events"
    column_names = {column.name for column in SecurityAuditEvent.__table__.columns}
    index_names = {index.name for index in SecurityAuditEvent.__table__.indexes}

    assert column_names == {
        "event_uid",
        "actor_user_id",
        "actor_role",
        "organization_id",
        "workspace_id",
        "event_action",
        "resource_type",
        "resource_uid",
        "evidence_source",
        "detail_text",
        "observed_at",
    }
    assert all("_" in column_name for column_name in column_names)
    assert "ix_security_audit_events_scope_time" in index_names
    assert "ix_security_audit_events_actor_scope" in index_names


def test_ai_hub_workflow_models_use_opaque_two_word_names():
    assert WorkflowDefinition.__tablename__ == "workflow_definitions"
    workflow_column_names = {
        column.name for column in WorkflowDefinition.__table__.columns
    }
    workflow_index_names = {
        index.name for index in WorkflowDefinition.__table__.indexes
    }

    assert workflow_column_names == {
        "workflow_uid",
        "organization_id",
        "workspace_id",
        "user_id",
        "workflow_name",
        "workflow_description",
        "steps_json",
        "state_code",
        "created_at",
        "updated_at",
    }
    assert all("_" in column_name for column_name in workflow_column_names)
    assert WorkflowDefinition.__table__.c.workflow_uid.primary_key is True
    assert "ix_workflow_definitions_scope_time" in workflow_index_names
    assert "ix_workflow_definitions_owner_scope" in workflow_index_names

    assert AgentRunRecord.__tablename__ == "agent_run_records"
    run_column_names = {column.name for column in AgentRunRecord.__table__.columns}
    run_index_names = {index.name for index in AgentRunRecord.__table__.indexes}

    assert run_column_names == {
        "run_uid",
        "workflow_uid",
        "organization_id",
        "workspace_id",
        "user_id",
        "status_code",
        "started_at",
        "completed_at",
        "result_summary",
    }
    assert all("_" in column_name for column_name in run_column_names)
    assert AgentRunRecord.__table__.c.run_uid.primary_key is True
    assert "ix_agent_run_records_workflow_uid" in run_index_names
    assert "ix_agent_run_records_scope_time" in run_index_names
    assert "ix_agent_run_records_owner_scope" in run_index_names
    assert "ix_agent_run_records_workflow_time" in run_index_names


def test_schema_backfill_creates_connector_signal_events():
    statements = [str(statement).lower() for statement in schema_backfill_sql()]

    assert any(
        "create table if not exists connector_signal_events" in statement
        for statement in statements
    )
    assert any(
        "ix_connector_signal_events_scope_time" in statement for statement in statements
    )
    assert any(
        "ix_security_audit_events_scope_time" in statement for statement in statements
    )
    assert any(
        "ix_security_audit_events_actor_scope" in statement for statement in statements
    )


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_schema_backfill_creates_legacy_emails_index_when_table_exists():
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TEMP TABLE emails ("
                    "user_id varchar, organization_id varchar, date timestamptz"
                    ") ON COMMIT DROP"
                )
            )
            await conn.run_sync(execute_schema_backfill, [LEGACY_EMAILS_INDEX])
            result = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'emails' "
                    "AND indexname = 'ix_emails_owner_date'"
                )
            )
            assert result.scalar_one() == "ix_emails_owner_date"
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
async def test_schema_backfill_skips_legacy_emails_index_when_table_absent():
    # A genuinely fresh database (0001_initial_control_plane.py's own
    # Base.metadata.create_all()) never creates a table named "emails" --
    # only "email_records" is ORM-modeled. execute_schema_backfill's guard
    # must skip LEGACY_EMAILS_INDEX in exactly this case rather than raising
    # "relation \"emails\" does not exist" (Postgres's CREATE INDEX IF NOT
    # EXISTS only guards the index name, not the target table's existence).
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(execute_schema_backfill, [LEGACY_EMAILS_INDEX])
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
async def test_connector_signal_events_real_postgres_bootstrap_smoke():
    engine = create_async_engine(settings.DATABASE_URL)
    duplicate_count = 0
    kept_title = ""
    smoke_user_id = "reply-sla-bootstrap-smoke-user"
    smoke_organization_id = "reply-sla-bootstrap-smoke-org"
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text("DROP INDEX IF EXISTS uq_ticket_tasks_reply_sla_email")
            )
            await conn.execute(
                text("DELETE FROM ticket_tasks WHERE user_id = :user_id"),
                {"user_id": smoke_user_id},
            )
            await conn.execute(
                text("DELETE FROM email_records WHERE user_id = :user_id"),
                {"user_id": smoke_user_id},
            )
            email_result = await conn.execute(
                text("""
                    INSERT INTO email_records (
                        user_id, organization_id, workspace_id, message_id,
                        sender, recipients, subject, "date", body, is_read
                    )
                    VALUES (
                        :user_id, :organization_id, :workspace_id, :message_id,
                        :sender, :recipients, :subject, now(), :body, false
                    )
                    RETURNING id
                    """),
                {
                    "user_id": smoke_user_id,
                    "organization_id": smoke_organization_id,
                    "workspace_id": f"workspace-{smoke_organization_id}",
                    "message_id": "<reply-sla-bootstrap-smoke@example.com>",
                    "sender": "smoke@example.com",
                    "recipients": "owner@example.com",
                    "subject": "Bootstrap duplicate reply follow-up",
                    "body": "bootstrap duplicate smoke",
                },
            )
            email_id = email_result.scalar_one()
            await conn.execute(
                text("""
                    INSERT INTO ticket_tasks (
                        task_uid, user_id, organization_id, task_title,
                        status_code, priority_code, source_type, email_id,
                        thread_id, created_at, updated_at
                    )
                    VALUES
                    (
                        'reply_sla_bootstrap_old', :user_id, :organization_id,
                        'old duplicate', 'blocked', 'urgent', 'reply_sla',
                        :email_id, 'thread-bootstrap-smoke',
                        now() - interval '2 hours', now() - interval '2 hours'
                    ),
                    (
                        'reply_sla_bootstrap_new', :user_id, :organization_id,
                        'new duplicate', 'blocked', 'urgent', 'reply_sla',
                        :email_id, 'thread-bootstrap-smoke',
                        now() - interval '1 hour', now() - interval '1 hour'
                    )
                    """),
                {
                    "user_id": smoke_user_id,
                    "organization_id": smoke_organization_id,
                    "email_id": email_id,
                },
            )
            await conn.run_sync(_execute_schema_backfill)
            result = await conn.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'connector_signal_events'
                    """)
            )
            column_names = {row[0] for row in result.fetchall()}
            duplicate_result = await conn.execute(
                text("""
                    SELECT
                        count(*) OVER () AS task_count,
                        task_title
                    FROM ticket_tasks
                    WHERE user_id = :user_id
                        AND organization_id = :organization_id
                        AND source_type = 'reply_sla'
                        AND email_id = :email_id
                    ORDER BY updated_at DESC, task_id DESC
                    LIMIT 1
                    """),
                {
                    "user_id": smoke_user_id,
                    "organization_id": smoke_organization_id,
                    "email_id": email_id,
                },
            )
            duplicate_count, kept_title = duplicate_result.one()
            await conn.execute(
                text("DELETE FROM ticket_tasks WHERE user_id = :user_id"),
                {"user_id": smoke_user_id},
            )
            await conn.execute(
                text("DELETE FROM email_records WHERE user_id = :user_id"),
                {"user_id": smoke_user_id},
            )
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

    assert {
        "event_uid",
        "organization_id",
        "workspace_id",
        "signal_key",
        "state_code",
        "detail_text",
        "observed_at",
    }.issubset(column_names)
    assert duplicate_count == 1
    assert kept_title == "new duplicate"
