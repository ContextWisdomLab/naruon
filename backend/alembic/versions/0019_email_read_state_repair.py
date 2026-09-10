"""idempotently ensure email_records has is_read

Revision ID: 0019_email_read_state_repair
Revises: 0018_workspace_registry
Create Date: 2026-09-01 00:00:00.000000

Alembic never re-runs a revision's ``upgrade()`` once that revision id is
recorded as applied for a database -- editing ``0011_email_read_state.py``'s
content cannot repair a database that already has "0011_email_read_state"
in its ``alembic_version`` history but never actually got
``email_records.is_read`` (whatever the reason: an earlier version of that
revision that targeted the wrong table, a partial/interrupted apply, manual
intervention). This revision is the real repair path for such a database:
appended after the current head, so it runs regardless of what 0011 already
did or didn't do. Idempotent (has_table/has_column guarded) so it is a
no-op for every database that already has the column, from any path.
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_email_read_state_repair"
down_revision = "0018_workspace_registry"

_EMAIL_TABLE = "email_records"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_EMAIL_TABLE) and not _has_column(
        inspector, _EMAIL_TABLE, "is_read"
    ):
        op.add_column(
            _EMAIL_TABLE,
            sa.Column(
                "is_read",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )


def downgrade() -> None:
    # Same ownership-ambiguity reasoning as 0011_email_read_state and
    # 0018_workspace_registry: this revision cannot tell whether it was the
    # one that added the column (repairing a stamped-but-incomplete
    # database) or the column already existed from another path, and
    # is_read holds real read/unread state, not rebuildable derived data.
    # No-op; production rollbacks should restore from backup.
    return None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )
