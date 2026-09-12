import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import services.email_import_service as email_import_module


@pytest.mark.asyncio
async def test_import_single_eml_requires_review_when_parsed_date_lacks_fingerprint_evidence(
    monkeypatch, tmp_path
):
    eml_path = tmp_path / "message.eml"
    eml_path.write_bytes(b"raw message")
    parsed = {
        "message_id": "",
        "date": datetime.datetime(2026, 9, 11, tzinfo=datetime.timezone.utc),
        "date_evidence": "parsed",
        "message_id_evidence": "missing",
        "sender": "sender@example.com",
        "subject": "",
        "recipients": "owner@example.com",
        "body": "body",
        "attachments": [],
    }
    email_object = MagicMock()

    monkeypatch.setattr(
        email_import_module, "_read_and_parse_eml", lambda _: (b"raw message", parsed)
    )
    monkeypatch.setattr(
        email_import_module,
        "_find_existing_email",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        email_import_module,
        "assign_thread_id",
        AsyncMock(return_value="thread-1"),
    )
    monkeypatch.setattr(
        email_import_module,
        "_extract_and_generate_embeddings",
        AsyncMock(return_value=([], [[0.0] * email_import_module.EMBEDDING_DIMENSION])),
    )
    monkeypatch.setattr(
        email_import_module,
        "_build_email_object",
        lambda **_: (email_object, 0),
    )
    monkeypatch.setattr(
        email_import_module,
        "_persist_project_graph_projection",
        AsyncMock(),
    )

    result = await email_import_module._import_single_eml(
        AsyncMock(spec=AsyncSession),
        eml_path=eml_path,
        display_filename="message.eml",
        user_id="user-1",
        organization_id="org-1",
    )

    assert result.status == "imported"
    assert result.reason_code == "dedupe_review_required"


def test_email_metadata_provenance_migration_declares_each_column_nullable():
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "email_metadata_provenance_1086.py"
    )
    revision_text = revision_path.read_text()

    assert 'sa.Column("date_evidence", sa.String(), nullable=True)' in revision_text
    assert 'sa.Column("message_id_evidence", sa.String(), nullable=True)' in revision_text
