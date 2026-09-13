"""add calendar conflict judgments and corrections

Revision ID: 0018_calendar_conflict_judgments
Revises: 0017_merge_newsdom_carddav_heads
Create Date: 2026-08-30 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa

revision = "0018_calendar_conflict_judgments"
down_revision = "0017_merge_newsdom_carddav_heads"

_JUDGMENT_TABLE = "calendar_conflict_judgments"
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


def _online_inspector():
    """Return a live schema inspector only when Alembic has a database bind."""
    if _is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _online_inspector()

    if inspector is None or not inspector.has_table(_JUDGMENT_TABLE):
        op.create_table(
            _JUDGMENT_TABLE,
            sa.Column("calendar_conflict_judgment_id", sa.Integer(), nullable=False),
            sa.Column("judgment_uid", sa.String(length=96), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("proposed_commitment_id", sa.String(length=256), nullable=False),
            sa.Column("source_thread_id", sa.String(), nullable=True),
            sa.Column("source_message_id", sa.String(), nullable=True),
            sa.Column("decision_code", sa.String(length=32), nullable=False),
            sa.Column("reason_code", sa.String(length=64), nullable=False),
            sa.Column("recommended_action", sa.Text(), nullable=False),
            sa.Column("policy_version", sa.String(length=32), nullable=False),
            sa.Column("conflicts_json", sa.JSON(), nullable=False),
            sa.Column("status_code", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("calendar_conflict_judgment_id"),
            sa.UniqueConstraint(
                "judgment_uid", name="uq_calendar_conflict_judgments_uid"
            ),
        )

    if inspector is None or not inspector.has_table(_CORRECTION_TABLE):
        op.create_table(
            _CORRECTION_TABLE,
            sa.Column("calendar_conflict_correction_id", sa.Integer(), nullable=False),
            sa.Column("correction_uid", sa.String(length=96), nullable=False),
            sa.Column("calendar_conflict_judgment_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), nullable=False),
            sa.Column("correction_action", sa.String(length=64), nullable=False),
            sa.Column("before_json", sa.JSON(), nullable=False),
            sa.Column("after_json", sa.JSON(), nullable=False),
            # 0018 intentionally records the historical column name; 0021
            # performs the released schema transition to correction_rationale.
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["calendar_conflict_judgment_id"],
                ["calendar_conflict_judgments.calendar_conflict_judgment_id"],
            ),
            sa.PrimaryKeyConstraint("calendar_conflict_correction_id"),
            sa.UniqueConstraint(
                "correction_uid", name="uq_calendar_conflict_corrections_uid"
            ),
        )

    for table_name, indexes in _calendar_conflict_indexes().items():
        for index_name, column_names in indexes:
            op.create_index(
                index_name,
                table_name,
                column_names,
                if_not_exists=True,
            )


def downgrade() -> None:
    inspector = _online_inspector()

    for table_name in (_CORRECTION_TABLE, _JUDGMENT_TABLE):
        if inspector is None or inspector.has_table(table_name):
            for index_name, _column_names in reversed(
                _calendar_conflict_indexes()[table_name]
            ):
                op.drop_index(index_name, table_name=table_name, if_exists=True)
            op.drop_table(table_name)


def _calendar_conflict_indexes() -> dict[str, list[tuple[str, list[str]]]]:
    return {
        _JUDGMENT_TABLE: [
            (
                "ix_calendar_conflict_judgments_scope_thread",
                ["user_id", "organization_id", "workspace_id", "source_thread_id"],
            ),
        ],
        _CORRECTION_TABLE: [
            (
                "ix_calendar_conflict_corrections_judgment",
                ["calendar_conflict_judgment_id"],
            ),
        ],
    }
