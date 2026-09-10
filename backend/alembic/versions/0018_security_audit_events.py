"""Formalize durable security audit events in the Alembic upgrade path.

Revision ID: 0018_security_audit_events
Revises: 0017_merge_newsdom_carddav_heads
Create Date: 2026-09-05 00:00:00.000000

Older installations can already contain ``security_audit_events`` because the
legacy bootstrap path created it outside Alembic. This revision is therefore
idempotent: it creates the table when absent and reconciles the model-owned
indexes when the table already exists. Downgrade intentionally preserves the
durable audit table and its evidence rather than deleting security history that
may predate this revision.
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_security_audit_events"
down_revision = "0017_merge_newsdom_carddav_heads"
branch_labels = None
depends_on = None

_TABLE = "security_audit_events"
_INDEXES: tuple[tuple[str, list[str]], ...] = (
    ("ix_security_audit_events_actor_user_id", ["actor_user_id"]),
    ("ix_security_audit_events_actor_role", ["actor_role"]),
    ("ix_security_audit_events_organization_id", ["organization_id"]),
    ("ix_security_audit_events_workspace_id", ["workspace_id"]),
    ("ix_security_audit_events_event_action", ["event_action"]),
    ("ix_security_audit_events_resource_type", ["resource_type"]),
    ("ix_security_audit_events_resource_uid", ["resource_uid"]),
    ("ix_security_audit_events_observed_at", ["observed_at"]),
    (
        "ix_security_audit_events_scope_time",
        ["organization_id", "workspace_id", "observed_at"],
    ),
    (
        "ix_security_audit_events_actor_scope",
        ["actor_user_id", "organization_id", "workspace_id"],
    ),
)


def upgrade() -> None:
    """Create the audit schema missing from Alembic-managed upgrades."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("event_uid", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), nullable=False),
            sa.Column("actor_role", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("event_action", sa.String(), nullable=False),
            sa.Column("resource_type", sa.String(), nullable=False),
            sa.Column("resource_uid", sa.String(), nullable=True),
            sa.Column("evidence_source", sa.String(), nullable=False),
            sa.Column("detail_text", sa.Text(), nullable=True),
            sa.Column(
                "observed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("event_uid"),
        )

    for index_name, column_names in _INDEXES:
        op.create_index(
            index_name,
            _TABLE,
            column_names,
            if_not_exists=True,
        )


def downgrade() -> None:
    """Preserve durable security evidence created before or after this revision."""
    # This revision reconciles a table that may predate Alembic ownership.
    # Dropping it on downgrade could destroy security evidence owned by the
    # earlier bootstrap path, so schema rollback deliberately leaves it intact.
