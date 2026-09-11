"""Persist email metadata provenance used by import deduplication.

Revision ID: email_metadata_provenance_1086
Revises: 0017_merge_newsdom_carddav_heads
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "email_metadata_provenance_1086"
down_revision = "0017_merge_newsdom_carddav_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_records",
        sa.Column("date_evidence", sa.String(), nullable=True),
    )
    op.add_column(
        "email_records",
        sa.Column("message_id_evidence", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_records", "message_id_evidence")
    op.drop_column("email_records", "date_evidence")
