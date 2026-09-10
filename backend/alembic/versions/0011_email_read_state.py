"""Add is_read to email_records (IMAP \\Seen read state).

Existing rows default to read so historical/file imports do not surface as unread.

Checks both "email_records" (the real, current table -- a database whose own
0001_initial_control_plane ran before ``is_read`` was added to the ``Email``
model has this table without the column, and needs it added) and "emails"
(a legacy name that, per 0011_email_model_reconciliation's docstring, no
migration in this repo's history ever actually created for a real managed
database, but is checked defensively in case one somehow exists). Guarded by
column existence, not just table existence, so it is safely idempotent.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0011_email_read_state"
down_revision = "0009_project_graph_projection"
branch_labels = None
depends_on = None

_CANDIDATE_TABLES = ("email_records", "emails")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in _CANDIDATE_TABLES:
        if inspector.has_table(table_name) and not _has_column(
            inspector, table_name, "is_read"
        ):
            op.add_column(
                table_name,
                sa.Column(
                    "is_read",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                ),
            )


def downgrade() -> None:
    # Same ownership-ambiguity problem as 0018_workspace_registry's downgrade:
    # a fresh database gets email_records.is_read from 0001's live
    # Base.metadata.create_all, not from this revision, so there is no way to
    # tell "this revision added the column" apart from "the baseline already
    # had it" -- and is_read holds real per-message read/unread state, not
    # rebuildable derived data. As with 0001_initial_control_plane and
    # 0018_workspace_registry: production rollbacks should restore from
    # backup or a later explicit down revision rather than dropping
    # customer-owned data.
    return None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )
