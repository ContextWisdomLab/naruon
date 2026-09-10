"""create workspace registry and workspace document tables

Revision ID: 0018_workspace_registry
Revises: 0017_merge_newsdom_carddav_heads
Create Date: 2026-09-01 00:00:00.000000

``Workspace``/``Document`` (``workspace_entities``/``workspace_documents``) have
been declared in ``db/models.py`` since before this repository's incremental
migration history begins tracking them explicitly. A database that ran
``0001_initial_control_plane``'s ``Base.metadata.create_all`` after these
models existed already has both tables; a database that ran ``0001`` earlier
and has only applied incremental migrations since never got them, so
``/api/data/documents`` fails with an undefined-relation error the first time
it is hit. This revision is idempotent (``has_table`` guarded) so it is a
no-op for a database that already has the tables and a real fix for one that
does not.
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_workspace_registry"
down_revision = "0017_merge_newsdom_carddav_heads"

_ENTITIES_TABLE = "workspace_entities"
_DOCUMENTS_TABLE = "workspace_documents"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if not inspector.has_table(_ENTITIES_TABLE):
        op.create_table(
            _ENTITIES_TABLE,
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("workspace_name", sa.String(), nullable=False),
            sa.Column("workspace_domain", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("workspace_id"),
        )

    if not inspector.has_table(_DOCUMENTS_TABLE):
        op.create_table(
            _DOCUMENTS_TABLE,
            sa.Column("document_id", sa.String(), nullable=False),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("document_name", sa.String(), nullable=False),
            sa.Column("document_type", sa.String(), nullable=False),
            sa.Column("document_content", sa.Text(), nullable=True),
            sa.Column("document_status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id"], [f"{_ENTITIES_TABLE}.workspace_id"]
            ),
            sa.PrimaryKeyConstraint("document_id"),
        )

    for index_name, column_names in (
        ("ix_workspace_documents_workspace_id", ["workspace_id"]),
        ("ix_workspace_documents_organization_id", ["organization_id"]),
    ):
        op.create_index(
            index_name,
            _DOCUMENTS_TABLE,
            column_names,
            if_not_exists=True,
        )


def downgrade() -> None:
    # This revision's upgrade is a no-op whenever the tables already exist
    # (e.g. created by 0001's create_all), so a downgrade cannot tell "this
    # revision created these tables" apart from "they predate it" -- and
    # workspace_documents.document_content holds real uploaded content, not
    # rebuildable derived state. Unconditionally dropping it risks destroying
    # data this revision never created. As with 0001_initial_control_plane:
    # production rollbacks should restore from backup or a later explicit
    # down revision rather than dropping customer-owned data.
    return None
