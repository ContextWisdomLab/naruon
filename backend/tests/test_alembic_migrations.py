from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_scaffold_exists_with_model_metadata_target():
    alembic_ini = BACKEND_ROOT / "alembic.ini"
    env_py = BACKEND_ROOT / "alembic" / "env.py"

    assert alembic_ini.exists()
    assert env_py.exists()

    alembic_ini_text = alembic_ini.read_text()
    env_text = env_py.read_text()

    assert "script_location = alembic" in alembic_ini_text
    assert "sqlalchemy.url =" in alembic_ini_text
    assert "from db.models import Base" in env_text
    assert "target_metadata = Base.metadata" in env_text
    assert "settings.DATABASE_URL" in env_text


def test_initial_alembic_revision_records_current_schema_path():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revisions = sorted(versions_dir.glob("*.py"))

    assert revisions
    revision_text = "\n".join(path.read_text() for path in revisions)

    assert 'revision = "0001_initial_control_plane"' in revision_text
    assert "down_revision = None" in revision_text
    assert "CREATE EXTENSION IF NOT EXISTS vector" in revision_text
    assert "Base.metadata.create_all" in revision_text
    assert "execute_schema_backfill" in revision_text


def test_email_read_state_guards_both_legacy_and_current_table_names():
    """0011_email_read_state must add is_read to a genuinely historical
    email_records table missing it (a database whose own 0001 ran before
    is_read was added to the Email model), not just a legacy "emails" table
    that, per 0011_email_model_reconciliation's docstring, no migration in
    this repo's history ever actually created for a real managed database.
    The upgrade check must guard on column existence, not just table
    existence, so it stays idempotent against a table that already has the
    column. downgrade is a no-op: a fresh database's email_records.is_read
    comes from 0001's live create_all, not from this revision, so there is
    no way to tell "this revision added it" apart from "the baseline already
    had it" -- and is_read holds real read/unread state, not rebuildable
    derived data (same ownership-ambiguity reasoning as
    0018_workspace_registry's downgrade)."""
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0011_email_read_state.py"
    revision_text = revision_path.read_text()

    assert '"email_records"' in revision_text
    assert '"emails"' in revision_text
    assert "has_table" in revision_text
    assert "_has_column" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.drop_column(" not in revision_text


def test_document_org_scope_downgrade_preserves_later_assignments():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0016_document_org_scope.py"
    )

    assert "op.drop_column(" not in revision_path.read_text()


def test_provider_writeback_retry_queue_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0002_provider_writeback_retry_queue.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0002_provider_retry_queue"' in revision_text
    assert 'down_revision = "0001_initial_control_plane"' in revision_text
    assert "op.create_table(" in revision_text
    assert '"provider_writeback_retry_items"' in revision_text
    assert '"retry_item_uid"' in revision_text
    assert '"command_payload_encrypted"' in revision_text
    assert '"retry_state"' in revision_text
    assert "ix_provider_writeback_retry_items_scope_state" in revision_text
    assert "has_table" in revision_text
    assert "op.create_index(" in revision_text
    assert "sa.text(" not in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_prompt_template_scope_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0003_prompt_template_scope.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0003_prompt_template_scope"' in revision_text
    assert 'down_revision = "0002_provider_retry_queue"' in revision_text
    assert '"prompt_templates"' in revision_text
    assert '"prompt_uid"' in revision_text
    assert '"organization_id"' in revision_text
    assert '"workspace_id"' in revision_text
    assert "ix_prompt_templates_owner_scope" in revision_text
    assert "ix_prompt_templates_shared_scope" in revision_text
    assert "uq_prompt_templates_prompt_uid" in revision_text
    assert "has_table" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_ai_hub_workflow_runs_have_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0004_ai_hub_workflow_runs.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0004_ai_hub_workflow_runs"' in revision_text
    assert 'down_revision = "0003_prompt_template_scope"' in revision_text
    assert '"workflow_definitions"' in revision_text
    assert '"agent_run_records"' in revision_text
    assert '"workflow_uid"' in revision_text
    assert '"run_uid"' in revision_text
    assert '"steps_json"' in revision_text
    assert '"status_code"' in revision_text
    assert "ix_workflow_definitions_scope_time" in revision_text
    assert "ix_workflow_definitions_owner_scope" in revision_text
    assert "ix_agent_run_records_workflow_uid" in revision_text
    assert "ix_agent_run_records_scope_time" in revision_text
    assert "ix_agent_run_records_owner_scope" in revision_text
    assert "ForeignKeyConstraint" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_content_graph_records_have_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0005_content_graph_records.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0005_content_graph_records"' in revision_text
    assert 'down_revision = "0004_ai_hub_workflow_runs"' in revision_text
    assert '"content_nodes"' in revision_text
    assert '"content_segments"' in revision_text
    assert '"content_node_uid"' in revision_text
    assert '"content_segment_uid"' in revision_text
    assert '"content_node_id"' in revision_text
    assert '"content_segment_id"' in revision_text
    assert '"word_count"' in revision_text
    assert '"token_count"' not in revision_text
    assert '"email_id"' in revision_text
    assert '"attachment_id"' in revision_text
    assert "ix_content_nodes_email_source" in revision_text
    assert "ix_content_segments_email_source" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_knowledge_graph_edges_have_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0006_knowledge_graph_edges.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0006_knowledge_graph_edges"' in revision_text
    assert 'down_revision = "0005_content_graph_records"' in revision_text
    assert '"knowledge_graph_edges"' in revision_text
    assert '"knowledge_graph_edge_id"' in revision_text
    assert '"edge_uid"' in revision_text
    assert '"email_id"' in revision_text
    assert '"attachment_id"' in revision_text
    assert '"source_node_id"' in revision_text
    assert '"target_node_id"' in revision_text
    assert '"source_segment_id"' in revision_text
    assert '"target_segment_id"' in revision_text
    assert '"content_nodes.content_node_id"' in revision_text
    assert '"content_segments.content_segment_id"' in revision_text
    assert '"source_kind"' in revision_text
    assert '"source_record_uid"' in revision_text
    assert '"edge_kind"' in revision_text
    assert '"edge_path"' in revision_text
    assert "ix_knowledge_graph_edges_email_kind" in revision_text
    assert "ix_knowledge_graph_edges_source_segment" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_attachment_parse_metadata_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0007_attachment_parse_metadata.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0007_attachment_parse_metadata"' in revision_text
    assert 'down_revision = "0006_knowledge_graph_edges"' in revision_text
    assert '"email_attachments"' in revision_text
    assert '"content_type"' in revision_text
    assert '"parse_status"' in revision_text
    assert '"parse_error_code"' in revision_text
    assert "has_column" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.drop_column(" in revision_text


def test_project_graph_projection_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0009_project_graph_projection.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0009_project_graph_projection"' in revision_text
    assert 'down_revision = "0008_attachment_parser_audit"' in revision_text
    assert '"project_graph_objects"' in revision_text
    assert '"project_graph_edges"' in revision_text
    assert '"project_graph_corrections"' in revision_text
    assert '"object_uid"' in revision_text
    assert '"edge_uid"' in revision_text
    assert '"correction_uid"' in revision_text
    assert '"workspace_id"' in revision_text
    assert '"source_segment_uids"' in revision_text
    assert '"attributes_json"' in revision_text
    assert '"before_json"' in revision_text
    assert '"after_json"' in revision_text
    assert '"content_segments.content_segment_id"' in revision_text
    assert "ix_project_graph_objects_scope_type_status" in revision_text
    assert "ix_project_graph_edges_scope_type" in revision_text
    assert "ix_project_graph_corrections_scope_time" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_llm_batch_orchestrator_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0012_llm_batch_orchestrator.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0012_llm_batch_orchestrator"' in revision_text
    assert 'down_revision = "0011_email_model_reconciliation"' in revision_text
    assert '"llm_batch_jobs"' in revision_text
    assert '"llm_batch_items"' in revision_text
    assert '"batch_job_uid"' in revision_text
    assert '"batch_item_uid"' in revision_text
    assert '"routing_mode"' in revision_text
    assert '"orchestrator_batch_uid"' in revision_text
    assert '"cost_micro_usd"' in revision_text
    assert '"batch_orchestrator_base_url"' in revision_text
    assert '"batch_orchestrator_token"' in revision_text
    assert '"batch_local_dsn"' in revision_text
    assert "sa.ForeignKeyConstraint(" in revision_text
    assert 'ondelete="CASCADE"' in revision_text
    assert "ix_llm_batch_jobs_scope_status" in revision_text
    assert "ix_llm_batch_items_job_sequence" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.add_column(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text
    assert "op.drop_column(" in revision_text


def test_scopeweave_promotion_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0013_scopeweave_promotion.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0013_scopeweave_promotion"' in revision_text
    assert 'down_revision = "0012_llm_batch_orchestrator"' in revision_text
    assert '"scopeweave_promotion_target"' in revision_text
    assert '"scopeweave_promotion_link"' in revision_text
    assert '"base_url"' in revision_text
    assert '"access_token"' in revision_text
    assert '"scopeweave_work_item_id"' in revision_text
    assert '"scopeweave_work_item_url"' in revision_text
    assert "uq_scopeweave_promotion_target_scope" in revision_text
    assert "uq_scopeweave_promotion_link_object" in revision_text
    assert "ix_scopeweave_promotion_link_scope" in revision_text
    assert "has_table" in revision_text
    assert "op.create_table(" in revision_text
    assert "op.create_index(" in revision_text
    assert "if_not_exists=True" in revision_text
    assert "op.drop_index(" in revision_text
    assert "if_exists=True" in revision_text


def test_migration_runner_uses_alembic_upgrade_head_not_bootstrap_create_all():
    migration_runner = BACKEND_ROOT / "scripts" / "migrate_db.py"

    assert migration_runner.exists()
    runner_text = migration_runner.read_text()

    assert "command.upgrade" in runner_text
    assert '"head"' in runner_text
    assert "script_location" in runner_text
    assert "bootstrap_db" not in runner_text
    assert "create_all" not in runner_text


def test_backend_requirements_include_alembic():
    requirements = (BACKEND_ROOT / "requirements.txt").read_text()

    assert any(
        line.split("==", maxsplit=1)[0] == "alembic"
        for line in requirements.splitlines()
    )


def test_language_agnostic_search_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0010_language_agnostic_search.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0010_language_agnostic_search"' in revision_text
    assert 'down_revision = "0009_project_graph_projection"' in revision_text
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in revision_text
    assert "CREATE EXTENSION IF NOT EXISTS unaccent" in revision_text
    assert "search_normalized_text" in revision_text
    assert "normalize(coalesce(input_text, ''), NFC)" in revision_text
    assert "regdictionary" in revision_text
    assert "IMMUTABLE" in revision_text
    assert "gist_trgm_ops(siglen=256)" in revision_text
    assert "ix_email_records_search_document_trgm" in revision_text
    assert "ix_email_attachments_content_trgm" in revision_text
    assert "ix_content_segments_safe_text_trgm" in revision_text
    assert "ix_project_graph_objects_search_document_trgm" in revision_text
    assert "IF NOT EXISTS" in revision_text
    assert "DROP INDEX IF EXISTS" in revision_text


def test_revision_identifiers_fit_alembic_version_column():
    """alembic_version.version_num is VARCHAR(32); longer revision ids
    make ``alembic upgrade head`` fail on fresh databases (regression:
    the original 38-char 0008 revision id)."""
    import re

    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    for revision_path in sorted(versions_dir.glob("*.py")):
        revision_text = revision_path.read_text()
        match = re.search(r'^revision = "([^"]+)"', revision_text, re.MULTILINE)
        assert match, f"no revision id in {revision_path.name}"
        revision_id = match.group(1)
        assert len(revision_id) <= 32, (
            f"{revision_path.name}: revision id {revision_id!r} is "
            f"{len(revision_id)} chars; alembic_version.version_num "
            "holds at most 32"
        )


def test_email_model_reconciliation_has_incremental_revision():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revision_path = versions_dir / "0011_email_model_reconciliation.py"
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0011_email_model_reconciliation"' in revision_text
    assert 'down_revision = "0010_language_agnostic_search"' in revision_text
    for retired_table_name in (
        "email_thread_edges",
        "email_instances",
        "email_raws",
        "email_messages",
        "email_threads",
        "provider_accounts",
        "user_accounts",
    ):
        assert f"DROP TABLE IF EXISTS {retired_table_name}" in revision_text
    # Dependents must drop before their FK targets.
    assert revision_text.index("email_thread_edges") < revision_text.index(
        "DROP TABLE IF EXISTS email_messages"
    )
    assert "Intentionally a no-op" in revision_text


def _collect_revision_graph() -> tuple[set[str], set[str]]:
    """Return (all revision ids, all referenced down_revision ids).

    Parses the ``revision``/``down_revision`` assignments textually (no alembic
    import, matching the rest of this module). Handles both the single-string
    ``down_revision = "x"`` form and the merge tuple
    ``down_revision = ("x", "y")`` form, as long as the assignment is on one
    line (the convention this repo follows).
    """
    import re

    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    revisions: set[str] = set()
    referenced: set[str] = set()
    for revision_path in sorted(versions_dir.glob("*.py")):
        text = revision_path.read_text()
        rev = re.search(r'^revision = "([^"]+)"', text, re.MULTILINE)
        assert rev, f"no revision id in {revision_path.name}"
        revisions.add(rev.group(1))
        down = re.search(r"^down_revision = (.+)$", text, re.MULTILINE)
        if down:
            referenced.update(re.findall(r'"([^"]+)"', down.group(1)))
    return revisions, referenced


def test_alembic_migration_graph_has_a_single_head():
    """``alembic upgrade head`` (scripts/migrate_db.py) is ambiguous and fails
    with "Multiple head revisions are present" whenever the migration graph has
    more than one head. Two parallel branches from 0009 (the 0010→0013 mainline
    and the 0011_email_read_state branch) once left develop with two heads; this
    guard prevents that regression. A new branch must be reconciled with a merge
    revision before it lands."""
    revisions, referenced = _collect_revision_graph()
    heads = revisions - referenced
    assert len(heads) == 1, (
        f"expected exactly one alembic head, found {sorted(heads)}; add a merge "
        "revision (down_revision tuple of the heads) so `alembic upgrade head` "
        "is unambiguous"
    )


def test_merge_revision_reconciles_email_read_state_branch():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0014_merge_email_read_state.py"
    )
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0014_merge_email_read_state"' in revision_text
    # A merge revision carries a tuple down_revision unifying both prior heads.
    assert "down_revision = (" in revision_text
    assert '"0011_email_read_state"' in revision_text
    assert '"0013_scopeweave_promotion"' in revision_text
    # It is a pure graph merge: no schema operations.
    assert "op.create_table(" not in revision_text
    assert "op.add_column(" not in revision_text
    assert "op.drop_column(" not in revision_text


def test_merge_revision_reconciles_newsdom_provider_branch():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0015_merge_newsdom_email_heads.py"
    )
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0015_merge_newsdom_email_heads"' in revision_text
    assert "down_revision = (" in revision_text
    assert '"0010_newsdom_providers"' in revision_text
    assert '"0014_merge_email_read_state"' in revision_text
    assert "op.create_table(" not in revision_text
    assert "op.add_column(" not in revision_text
    assert "op.drop_column(" not in revision_text


def test_merge_revision_reconciles_newsdom_document_and_carddav_heads():
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0017_merge_newsdom_carddav_heads.py"
    )
    assert revision_path.exists()
    revision_text = revision_path.read_text()

    assert 'revision = "0017_merge_newsdom_carddav_heads"' in revision_text
    assert "down_revision = (" in revision_text
    assert '"0016_document_org_scope"' in revision_text
    assert '"0015_merge_carddav_accounts"' in revision_text
    assert "op.create_table(" not in revision_text
    assert "op.add_column(" not in revision_text
    assert "op.drop_column(" not in revision_text
