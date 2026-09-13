"""rename the calendar correction rationale column

Revision ID: 0021_calendar_rationale
Revises: 0020_email_workspace_scope
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa

revision = "0021_calendar_rationale"
down_revision = "0020_email_workspace_scope"

_CORRECTION_TABLE = "calendar_conflict_corrections"


def _is_offline_mode() -> bool:
    """Detect SQL-only execution without requiring an EnvironmentContext proxy."""
    try:
        return bool(context.is_offline_mode())
    except (AttributeError, NameError):
        # Focused migration tests invoke upgrade/downgrade with an Operations
        # proxy but no Alembic EnvironmentContext. That path is online and
        # supplies either a real or deliberately mocked bind.
        return False


def upgrade() -> None:
    if _is_offline_mode():
        op.alter_column(
            _CORRECTION_TABLE,
            "rationale",
            new_column_name="correction_rationale",
        )
        return

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_CORRECTION_TABLE):
        return

    columns = {column["name"] for column in inspector.get_columns(_CORRECTION_TABLE)}
    if "rationale" in columns and "correction_rationale" not in columns:
        op.alter_column(
            _CORRECTION_TABLE,
            "rationale",
            new_column_name="correction_rationale",
        )


def downgrade() -> None:
    if _is_offline_mode():
        op.alter_column(
            _CORRECTION_TABLE,
            "correction_rationale",
            new_column_name="rationale",
        )
        return

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_CORRECTION_TABLE):
        return

    columns = {column["name"] for column in inspector.get_columns(_CORRECTION_TABLE)}
    if "correction_rationale" in columns and "rationale" not in columns:
        op.alter_column(
            _CORRECTION_TABLE,
            "correction_rationale",
            new_column_name="rationale",
        )
