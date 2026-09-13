import pytest
import datetime
from unittest.mock import patch, AsyncMock
from sqlalchemy.dialects import postgresql
from scripts.import_fixtures import process_zip_file
import import_fixtures
import scripts.import_fixtures as scripts_import_fixtures


@pytest.mark.asyncio
async def test_process_zip_file():
    with patch("scripts.import_fixtures.extract_backup_async") as mock_extract:
        with patch("scripts.import_fixtures.parse_eml"):
            with patch("scripts.import_fixtures.generate_embeddings"):
                mock_extract.return_value = []
                # Ensure it doesn't crash on an empty zip
                await process_zip_file("dummy.zip", AsyncMock())


@pytest.mark.asyncio
async def test_process_zip_file_batch_insert_includes_workspace_id():
    # Email.workspace_id is NOT NULL (0020_email_workspace_scope); this batch
    # insert built its own values dict independently of the root importer's
    # email_obj = Email(...) construction (already fixed) and was missed --
    # any nonempty archive would fail at commit without it.
    captured_batch_values = []

    class _RecordingSession:
        async def scalar(self, *args, **kwargs):
            return None

        async def execute(self, statement, batch_values=None):
            if batch_values is not None:
                captured_batch_values.extend(batch_values)

        async def commit(self):
            pass

    email_data = {
        "message_id": "msg-1",
        "sender": "sender@example.com",
        "reply_to": None,
        "recipients": ["recipient@example.com"],
        "subject": "Subject",
        "in_reply_to": None,
        "references": None,
        "date": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        "body": "body text",
    }

    with (
        patch("scripts.import_fixtures.extract_backup_async") as mock_extract,
        patch("scripts.import_fixtures.parse_eml", return_value=email_data),
        patch("scripts.import_fixtures.chunk_text", return_value=[]),
        patch(
            "scripts.import_fixtures.assign_thread_id",
            new=AsyncMock(return_value="thread-1"),
        ),
    ):
        mock_extract.return_value = ["fixture.eml"]
        await process_zip_file("dummy.zip", _RecordingSession())

    assert len(captured_batch_values) == 1
    batch_row = captured_batch_values[0]
    assert "workspace_id" in batch_row
    assert batch_row["workspace_id"] == (
        f"workspace-{scripts_import_fixtures.IMPORT_ORGANIZATION_ID}"
        if scripts_import_fixtures.IMPORT_ORGANIZATION_ID
        else f"workspace-{scripts_import_fixtures.IMPORT_USER_ID}"
    )


@pytest.mark.asyncio
async def test_process_zip_file_upsert_targets_workspace_scoped_identity():
    # Alembic 0020_email_workspace_scope drops the 3-column
    # uq_emails_owner_message_id constraint and replaces it with the 4-column
    # uq_emails_workspace_message (user_id, organization_id, workspace_id,
    # message_id). An ON CONFLICT target that still names only the old
    # 3-column shape matches no constraint on a real PostgreSQL database and
    # PostgreSQL rejects the statement outright -- every nonempty ZIP import
    # would fail. SQLite (this test's default) is lenient about this, which is
    # exactly why the mismatch survived undetected; compile against the
    # PostgreSQL dialect to actually exercise the constraint-matching rule.
    captured_statement = {}

    class _RecordingSession:
        async def scalar(self, *args, **kwargs):
            return None

        async def execute(self, statement, batch_values=None):
            captured_statement["statement"] = statement

        async def commit(self):
            pass

    email_data = {
        "message_id": "msg-1",
        "sender": "sender@example.com",
        "reply_to": None,
        "recipients": ["recipient@example.com"],
        "subject": "Subject",
        "in_reply_to": None,
        "references": None,
        "date": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        "body": "body text",
    }

    with (
        patch("scripts.import_fixtures.extract_backup_async") as mock_extract,
        patch("scripts.import_fixtures.parse_eml", return_value=email_data),
        patch("scripts.import_fixtures.chunk_text", return_value=[]),
        patch(
            "scripts.import_fixtures.assign_thread_id",
            new=AsyncMock(return_value="thread-1"),
        ),
    ):
        mock_extract.return_value = ["fixture.eml"]
        await process_zip_file("dummy.zip", _RecordingSession())

    compiled = str(
        captured_statement["statement"].compile(dialect=postgresql.dialect())
    )
    assert (
        "ON CONFLICT (user_id, organization_id, workspace_id, message_id)"
        in compiled
    )


@pytest.mark.asyncio
async def test_root_importer_persists_canonical_thread_id(tmp_path):
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        def __init__(self):
            self.added = None
            self.committed = False

        async def execute(self, _query):
            return MockResult()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            self.committed = True

    eml_file = tmp_path / "reply.eml"
    eml_file.write_text("Message-ID: <reply@example.com>\n\nBody")
    parsed = {
        "message_id": "<reply@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Re: Root",
        "in_reply_to": "<parent@example.com>",
        "references": "<root@example.com> <parent@example.com>",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": [],
    }
    session = MockSession()

    with (
        patch.object(import_fixtures, "parse_eml", return_value=parsed),
        patch.object(
            import_fixtures, "generate_embeddings", new_callable=AsyncMock
        ) as mock_embeddings,
        patch.object(
            import_fixtures, "assign_thread_id", new_callable=AsyncMock
        ) as mock_assign,
    ):
        mock_embeddings.return_value = [[0.0] * 1536]
        mock_assign.return_value = "canonical-thread"

        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is True
    assert session.added.thread_id == "canonical-thread"
    assert session.committed is True


@pytest.mark.asyncio
async def test_root_importer_duplicate_check_is_scoped_to_owner(tmp_path):
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        def __init__(self):
            self.queries = []
            self.added = None

        async def execute(self, query):
            self.queries.append(query)
            return MockResult()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            pass

    eml_file = tmp_path / "duplicate-scope.eml"
    eml_file.write_text("Message-ID: <duplicate-scope@example.com>\n\nBody")
    parsed = {
        "message_id": "<duplicate-scope@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Duplicate scope",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": [],
    }
    session = MockSession()

    with (
        patch.object(import_fixtures, "parse_eml", return_value=parsed),
        patch.object(
            import_fixtures, "generate_embeddings", new_callable=AsyncMock
        ) as mock_embeddings,
        patch.object(
            import_fixtures, "assign_thread_id", new_callable=AsyncMock
        ) as mock_assign,
    ):
        mock_embeddings.return_value = [[0.0] * 1536]
        mock_assign.return_value = "duplicate-scope-thread"

        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is True
    query_text = str(session.queries[0]).lower()
    where_clause = query_text.partition("where ")[2]
    assert "email_records.message_id = :message_id_1" in where_clause
    assert "email_records.user_id = :user_id_1" in where_clause
    assert "email_records.organization_id = :organization_id_1" in where_clause
    # Email's identity is scoped by workspace_id too (uq_emails_workspace_message);
    # omitting it from the WHERE clause (workspace_id is always in the SELECT
    # list simply because select(Email) selects every column, so checking for
    # its bare presence in the whole query proves nothing) would let a
    # duplicate lookup in one workspace find -- and wrongly skip re-importing
    # -- a row that only exists in another one.
    assert "email_records.workspace_id = :workspace_id_1" in where_clause
    mock_assign.assert_awaited_once_with(
        session,
        parsed,
        user_id=import_fixtures.IMPORT_USER_ID,
        organization_id=import_fixtures.IMPORT_ORGANIZATION_ID,
        workspace_id=import_fixtures.IMPORT_WORKSPACE_ID,
    )


@pytest.mark.asyncio
async def test_root_importer_stores_email_under_configured_workspace_id(
    tmp_path, monkeypatch
):
    # A custom NARUON_IMPORT_WORKSPACE_ID is threaded into assign_thread_id
    # (asserted above) but the stored Email row must land in that SAME
    # workspace -- otherwise thread assignment and email storage disagree on
    # which workspace a fixture belongs to, splitting or hiding the imported
    # conversation when queried by workspace.
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        def __init__(self):
            self.added = None

        async def execute(self, _query):
            return MockResult()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            pass

    monkeypatch.setattr(import_fixtures, "IMPORT_WORKSPACE_ID", "workspace-custom-fixture")

    eml_file = tmp_path / "custom-workspace.eml"
    eml_file.write_text("Message-ID: <custom-workspace@example.com>\n\nBody")
    parsed = {
        "message_id": "<custom-workspace@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Custom workspace",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": [],
    }
    session = MockSession()

    with (
        patch.object(import_fixtures, "parse_eml", return_value=parsed),
        patch.object(
            import_fixtures, "generate_embeddings", new_callable=AsyncMock
        ) as mock_embeddings,
        patch.object(
            import_fixtures, "assign_thread_id", new_callable=AsyncMock
        ) as mock_assign,
    ):
        mock_embeddings.return_value = [[0.0] * 1536]
        mock_assign.return_value = "custom-workspace-thread"

        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is True
    assert session.added.workspace_id == "workspace-custom-fixture"


@pytest.mark.asyncio
async def test_root_importer_uses_local_embedding_without_openai_key(
    tmp_path, monkeypatch
):
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        def __init__(self):
            self.added = None

        async def execute(self, _query):
            return MockResult()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            pass

    eml_file = tmp_path / "root.eml"
    eml_file.write_text("Message-ID: <root@example.com>\n\nBody")
    parsed = {
        "message_id": "<root@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Root",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": [],
    }
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    session = MockSession()

    with (
        patch.object(import_fixtures, "parse_eml", return_value=parsed),
        patch.object(
            import_fixtures,
            "generate_embeddings",
            side_effect=AssertionError("network call"),
        ),
    ):
        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is True
    assert session.added.embedding == [0.0] * 1536


@pytest.mark.asyncio
async def test_root_importer_handles_empty_embedding_provider_response(
    tmp_path, monkeypatch
):
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        def __init__(self):
            self.added = None

        async def execute(self, _query):
            return MockResult()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            pass

    eml_file = tmp_path / "empty-embedding.eml"
    eml_file.write_text("Message-ID: <empty-embedding@example.com>\n\nBody")
    parsed = {
        "message_id": "<empty-embedding@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Empty embedding",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": [],
    }
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    session = MockSession()

    with (
        patch.object(import_fixtures, "parse_eml", return_value=parsed),
        patch.object(
            import_fixtures, "generate_embeddings", new_callable=AsyncMock
        ) as mock_embeddings,
        patch.object(
            import_fixtures, "assign_thread_id", new_callable=AsyncMock
        ) as mock_assign,
    ):
        mock_embeddings.return_value = []
        mock_assign.return_value = "empty-embedding-thread"

        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is True
    assert session.added.embedding == [0.0] * 1536


@pytest.mark.asyncio
async def test_root_importer_rolls_back_and_returns_false_on_commit_failure(tmp_path):
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        def __init__(self):
            self.added = None
            self.rolled_back = False

        async def execute(self, _query):
            return MockResult()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            raise RuntimeError("commit failed")

        async def rollback(self):
            self.rolled_back = True

    eml_file = tmp_path / "commit-failure.eml"
    eml_file.write_text("Message-ID: <commit-failure@example.com>\n\nBody")
    parsed = {
        "message_id": "<commit-failure@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Commit failure",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": [],
    }
    session = MockSession()

    with (
        patch.object(import_fixtures, "parse_eml", return_value=parsed),
        patch.object(
            import_fixtures, "generate_embeddings", new_callable=AsyncMock
        ) as mock_embeddings,
        patch.object(
            import_fixtures, "assign_thread_id", new_callable=AsyncMock
        ) as mock_assign,
    ):
        mock_embeddings.return_value = [[0.0] * 1536]
        mock_assign.return_value = "commit-failure-thread"

        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is False
    assert session.added is not None
    assert session.rolled_back is True
