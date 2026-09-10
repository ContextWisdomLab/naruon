"""initial control plane schema

Revision ID: 0001_initial_control_plane
Revises:
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
from sqlalchemy import text

from db.models import Base
from scripts.bootstrap_db import execute_schema_backfill

revision = "0001_initial_control_plane"
down_revision = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(connection)
    execute_schema_backfill(connection)


def downgrade() -> None:
    # Baseline migration: production rollbacks should restore from backup or a
    # later explicit down revision rather than dropping customer-owned metadata.
    return None
