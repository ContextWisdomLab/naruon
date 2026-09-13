"""add noema contextual-orchestrator gateway columns to tenant_configs

Revision ID: 0022_noema_orchestrator_gateway
Revises: 0021_calendar_rationale
Create Date: 2026-09-02 00:00:00.000000

The general-purpose Noema workspace agent (``services/noema_agent.py``) must
route every chat-completion call through ``contextual-orchestrator`` -- the
org's routing/cost hub -- rather than a tenant's own direct LLM-provider key.
This migration adds the per-tenant gateway credential columns on
``tenant_configs``, mirroring the ``batch_orchestrator_*`` columns
(0012_llm_batch_orchestrator) already used for batch embedding routing
through the same orchestrator. All new config is resolved from the Fernet DB
at runtime, never from ``os.getenv``.
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_noema_orchestrator_gateway"
down_revision = "0021_calendar_rationale"
branch_labels = None
depends_on = None

_TENANT_TABLE = "tenant_configs"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if inspector.has_table(_TENANT_TABLE):
        for column in _tenant_noema_gateway_columns():
            if not _has_column(inspector, _TENANT_TABLE, column.name):
                op.add_column(_TENANT_TABLE, column)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if inspector.has_table(_TENANT_TABLE):
        for column in reversed(_tenant_noema_gateway_columns()):
            if _has_column(inspector, _TENANT_TABLE, column.name):
                op.drop_column(_TENANT_TABLE, column.name)


def _tenant_noema_gateway_columns() -> list["sa.Column"]:
    return [
        sa.Column("noema_orchestrator_base_url", sa.String(), nullable=True),
        sa.Column("noema_orchestrator_token", sa.String(), nullable=True),
    ]


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )
