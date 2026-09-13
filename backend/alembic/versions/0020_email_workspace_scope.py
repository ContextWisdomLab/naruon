"""add workspace_id scope column to email_records

Revision ID: 0020_email_workspace_scope
Revises: 0019_attachment_uid
Create Date: 2026-08-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_email_workspace_scope"
down_revision = "0019_attachment_uid"

_EMAIL_TABLE = "email_records"
_EMAIL_WORKSPACE_INDEX = "ix_email_records_workspace_id"
_OLD_EMAIL_IDENTITY = "uq_emails_owner_message_id"
# backend/scripts/bootstrap_db.py's dev-compat path predates this migration
# and creates the owner-only identity under a different name and as a plain
# index rather than a named unique constraint; a database bootstrapped before
# that script's own fix landed and later migrated via Alembic needs this
# shape recognized too, or it keeps the stricter, non-workspace-scoped
# identity forever.
_BOOTSTRAP_OLD_EMAIL_IDENTITY = "uq_email_records_owner_message_id"
_EMAIL_WORKSPACE_IDENTITY = "uq_emails_workspace_message"


def _email_table_stub() -> sa.TableClause:
    return sa.table(
        _EMAIL_TABLE,
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.String()),
        sa.column("organization_id", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("message_id", sa.String()),
    )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(_EMAIL_TABLE):
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns(_EMAIL_TABLE)
    }
    if "workspace_id" not in existing_columns:
        op.add_column(
            _EMAIL_TABLE, sa.Column("workspace_id", sa.String(), nullable=True)
        )
        emails = _email_table_stub()
        # email_records.organization_id is NOT NULL, so every existing row has
        # a deterministic workspace under this codebase's established
        # convention (services/email_import_service.py, project_graph):
        # workspace-<organization_id>. There is no independent workspace
        # registry to join against -- Email carries no FK to any
        # account/mailbox table that itself has workspace_id (organization
        # config lives in FK-less tenant_configs/caldav_accounts/webdav_accounts).
        connection.execute(
            sa.update(emails)
            .where(emails.c.workspace_id.is_(None))
            .values(workspace_id=sa.func.concat("workspace-", emails.c.organization_id))
        )
        op.alter_column(_EMAIL_TABLE, "workspace_id", nullable=False)

    existing_indexes = {index["name"] for index in inspector.get_indexes(_EMAIL_TABLE)}
    if _EMAIL_WORKSPACE_INDEX not in existing_indexes:
        op.create_index(
            _EMAIL_WORKSPACE_INDEX,
            _EMAIL_TABLE,
            ["workspace_id"],
            if_not_exists=True,
        )

    existing_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(_EMAIL_TABLE)
    }
    unique_indexes = {
        index["name"]
        for index in inspector.get_indexes(_EMAIL_TABLE)
        if index.get("unique")
    }
    # get_indexes() also reports the backing index of a unique constraint
    # under the same name (PostgreSQL implements a unique constraint via a
    # unique index), so each identity's constraint case must be checked --
    # and handled -- before its index case: DROP INDEX on a constraint's own
    # backing index is rejected by PostgreSQL ("cannot drop index ...
    # because constraint ... requires it"), which would abort this
    # migration outright.
    if _OLD_EMAIL_IDENTITY in existing_constraints:
        op.drop_constraint(_OLD_EMAIL_IDENTITY, _EMAIL_TABLE, type_="unique")
    elif _OLD_EMAIL_IDENTITY in unique_indexes:
        op.drop_index(_OLD_EMAIL_IDENTITY, table_name=_EMAIL_TABLE)

    if _BOOTSTRAP_OLD_EMAIL_IDENTITY in existing_constraints:
        op.drop_constraint(
            _BOOTSTRAP_OLD_EMAIL_IDENTITY, _EMAIL_TABLE, type_="unique"
        )
    elif _BOOTSTRAP_OLD_EMAIL_IDENTITY in unique_indexes:
        op.drop_index(_BOOTSTRAP_OLD_EMAIL_IDENTITY, table_name=_EMAIL_TABLE)

    if _EMAIL_WORKSPACE_IDENTITY not in existing_constraints | unique_indexes:
        op.create_unique_constraint(
            _EMAIL_WORKSPACE_IDENTITY,
            _EMAIL_TABLE,
            ["user_id", "organization_id", "workspace_id", "message_id"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(_EMAIL_TABLE):
        return

    emails = _email_table_stub()
    duplicate_identity = connection.execute(
        sa.select(
            emails.c.user_id,
            emails.c.organization_id,
            emails.c.message_id,
        )
        .group_by(
            emails.c.user_id,
            emails.c.organization_id,
            emails.c.message_id,
        )
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate_identity is not None:
        raise RuntimeError(
            "Cannot downgrade email workspace identity while duplicate owner/message "
            "rows exist across workspaces"
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes(_EMAIL_TABLE)}
    if _EMAIL_WORKSPACE_INDEX in existing_indexes:
        op.drop_index(_EMAIL_WORKSPACE_INDEX, table_name=_EMAIL_TABLE, if_exists=True)

    existing_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(_EMAIL_TABLE)
    }
    unique_indexes = {
        index["name"]
        for index in inspector.get_indexes(_EMAIL_TABLE)
        if index.get("unique")
    }
    if _EMAIL_WORKSPACE_IDENTITY in existing_constraints:
        op.drop_constraint(_EMAIL_WORKSPACE_IDENTITY, _EMAIL_TABLE, type_="unique")
    elif _EMAIL_WORKSPACE_IDENTITY in unique_indexes:
        op.drop_index(_EMAIL_WORKSPACE_IDENTITY, table_name=_EMAIL_TABLE)
    if _OLD_EMAIL_IDENTITY not in existing_constraints | unique_indexes:
        op.create_unique_constraint(
            _OLD_EMAIL_IDENTITY,
            _EMAIL_TABLE,
            ["user_id", "organization_id", "message_id"],
        )

    existing_columns = {
        column["name"] for column in inspector.get_columns(_EMAIL_TABLE)
    }
    if "workspace_id" in existing_columns:
        op.drop_column(_EMAIL_TABLE, "workspace_id")
