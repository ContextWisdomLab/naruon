"""add organization scope to workspace documents

Revision ID: 0016_document_org_scope
Revises: 0015_merge_newsdom_email_heads
Create Date: 2026-07-13 00:00:00.000000

Workspace documents gain a nullable ``organization_id`` so the NewsDOM PDF
recognition worker can resolve the owning organization's provider without
joining through the (organization-less) workspace entity. Nullable and additive
so existing rows and personal-scope documents are unaffected.

A database that has never had ``workspace_documents`` at all (one that ran
``0001_initial_control_plane`` before ``Workspace``/``Document`` existed in
``db/models.py``, and has only applied incremental migrations since) has no
table for this revision to alter. This revision is a no-op for that case;
``0018_workspace_registry`` creates the table later in the chain, already
including this column.
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_document_org_scope"
down_revision = "0015_merge_newsdom_email_heads"

_DOCUMENTS_TABLE = "workspace_documents"
_ORG_COLUMN = "organization_id"
_ORG_INDEX = "ix_workspace_documents_organization_id"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(_DOCUMENTS_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_DOCUMENTS_TABLE)}
    if _ORG_COLUMN not in columns:
        op.add_column(
            _DOCUMENTS_TABLE,
            sa.Column(_ORG_COLUMN, sa.String(), nullable=True),
        )
    op.create_index(
        _ORG_INDEX,
        _DOCUMENTS_TABLE,
        [_ORG_COLUMN],
        if_not_exists=True,
    )


def downgrade() -> None:
    # 0018 can create this table and column after 0016 was a no-op. Alembic
    # cannot distinguish that case from a table altered by this revision, so
    # dropping the column here could destroy later organization assignments.
    return None
