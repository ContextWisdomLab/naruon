"""Regression contract for durable security-audit schema migration."""

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND_ROOT / "alembic" / "versions" / "0018_security_audit_events.py"
)


def test_security_audit_events_have_structured_incremental_revision() -> None:
    """Alembic upgrades must create the durable audit table used by runtime gates."""
    assert MIGRATION_PATH.exists()
    revision_text = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision = "0018_security_audit_events"' in revision_text
    assert 'down_revision = "0017_merge_newsdom_carddav_heads"' in revision_text
    assert '"security_audit_events"' in revision_text
    for column_name in (
        "event_uid",
        "actor_user_id",
        "actor_role",
        "organization_id",
        "workspace_id",
        "event_action",
        "resource_type",
        "resource_uid",
        "evidence_source",
        "detail_text",
        "observed_at",
    ):
        assert f'"{column_name}"' in revision_text

    assert "op.create_table(" in revision_text
    assert "has_table" in revision_text
    assert "ix_security_audit_events_scope_time" in revision_text
    assert "ix_security_audit_events_actor_scope" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "Base.metadata.create_all" not in revision_text
