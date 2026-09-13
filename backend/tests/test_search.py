import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from db.models import LLMProvider
from db.session import get_db, get_readonly_db
from main import app
from services.exceptions import EmbeddingGenerationError
from services.hybrid_retrieval import FusionSettings
from services.llm_provider_selection import LOCAL_PROVIDER_API_KEY

pytestmark = pytest.mark.usefixtures("dev_auth_dependency_overrides")

_CANDIDATE_DATE = datetime.datetime(2026, 4, 27, 10, 0, tzinfo=datetime.timezone.utc)


class MockLexicalRow:
    def __init__(
        self,
        email_id,
        subject,
        sender,
        matched_text,
        word_similarity_score,
        result_kind="email_body",
    ):
        self.email_id = email_id
        self.source_message_id = "<test@example.com>"
        self.subject = subject
        self.sender = sender
        self.date = _CANDIDATE_DATE
        self.thread_key = "thread-123"
        self.matched_text = matched_text
        self.result_kind = result_kind
        self.word_similarity_score = word_similarity_score


class MockDenseRow:
    def __init__(
        self,
        email_id,
        subject,
        sender,
        matched_text,
        cosine_distance,
        result_kind="email_body",
    ):
        self.email_id = email_id
        self.source_message_id = "<test@example.com>"
        self.subject = subject
        self.sender = sender
        self.date = _CANDIDATE_DATE
        self.thread_key = "thread-123"
        self.matched_text = matched_text
        self.result_kind = result_kind
        self.cosine_distance = cosine_distance


class MockReplyCountRow:
    def __init__(self, thread_key, reply_count):
        self.thread_key = thread_key
        self.reply_count = reply_count


class MockRowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class MockTenantConfigResult:
    def __init__(self, config):
        self.config = config

    def scalar_one_or_none(self):
        return self.config


class MockScalars:
    def __init__(self, items):
        self.items = items

    def first(self):
        return self.items[0] if self.items else None


class MockProviderResult:
    def __init__(self, providers):
        self.providers = providers

    def scalars(self):
        return MockScalars(self.providers)


class MockTenantConfig:
    def __init__(self):
        self.openai_api_key = "test-key"


class MockSession:
    def __init__(self, providers=None):
        self.providers = providers or []

    async def execute(self, stmt):
        statement_text = str(stmt).lower()
        if "llm_providers" in statement_text:
            return MockProviderResult(self.providers)
        if "tenant_configs" in statement_text:
            return MockTenantConfigResult(MockTenantConfig())
        if "count(email_records.id)" in statement_text:
            return MockRowsResult([MockReplyCountRow("thread-123", 2)])
        if "word_similarity" in statement_text:
            return MockRowsResult(
                [MockLexicalRow(1, "Test Subject", "test@test.com", "Test Body", 0.9)]
            )
        if "<=>" in statement_text:
            return MockRowsResult(
                [MockDenseRow(1, "Test Subject", "test@test.com", "Test Body", 0.3)]
            )
        return MockRowsResult([])

    async def scalar(self, stmt):
        return MockTenantConfig()


async def override_get_db():
    yield MockSession()


class CapturingMockSession(MockSession):
    def __init__(self, providers=None):
        super().__init__(providers=providers)
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return await super().execute(stmt)


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_readonly_db] = override_get_db
    with TestClient(app, headers={"X-User-Id": "testuser"}) as c:
        yield c
    app.dependency_overrides.clear()


@patch("api.search.generate_embeddings", new_callable=AsyncMock)
def test_search_endpoint_success(mock_generate_embeddings, client):
    mock_generate_embeddings.return_value = [[0.1] * 1536]

    response = client.post("/api/search", json={"query": "test query"})

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == 1
    assert data["results"][0]["subject"] == "Test Subject"
    assert data["results"][0]["date"] == "2026-04-27T10:00:00Z"
    assert data["results"][0]["source_message_id"] == "<test@example.com>"
    assert data["results"][0]["thread_id"] == "thread-123"
    assert data["results"][0]["reply_count"] == 2
    assert data["results"][0]["result_kind"] == "email_body"
    assert data["results"][0]["evidence_kinds"] == ["email_body"]
    assert 0.0 <= data["results"][0]["score"] <= 1.0


@patch("api.search.generate_embeddings", new_callable=AsyncMock)
def test_search_endpoint_uses_active_provider_embedding_model(mock_generate_embeddings):
    provider = LLMProvider(
        id=4,
        user_id="admin",
        organization_id="org-acme",
        name="Local Gemma4",
        provider_type="ollama",
        base_url="http://ollama:11434/v1",
        model_identifier="gemma4",
        embedding_model="embeddinggemma",
        api_key=None,
        is_active=True,
    )
    mock_generate_embeddings.return_value = [[0.1] * 1536]
    session = MockSession(providers=[provider])

    async def override_scoped_db():
        yield session

    app.dependency_overrides[get_db] = override_scoped_db
    app.dependency_overrides[get_readonly_db] = override_scoped_db
    try:
        with TestClient(
            app,
            headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
        ) as client:
            response = client.post("/api/search", json={"query": "test query"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    mock_generate_embeddings.assert_awaited_once_with(
        ["test query"],
        LOCAL_PROVIDER_API_KEY,
        base_url="http://ollama:11434/v1",
        model="embeddinggemma",
    )


def test_thread_group_key_uses_trimmed_thread_then_message_id():
    from sqlalchemy.dialects import postgresql

    from api.search import thread_group_key

    compiled_sql = " ".join(
        str(
            thread_group_key().compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        .lower()
        .split()
    )
    expected_sql = (
        "coalesce("
        "nullif(btrim(btrim(email_records.thread_id), '<>'), ''), "
        "nullif(btrim(btrim(email_records.message_id), '<>'), '')"
        ")"
    )

    assert expected_sql in compiled_sql


@patch("api.search.generate_embeddings", new_callable=AsyncMock)
def test_search_endpoint_query_is_scoped_to_current_user(mock_generate_embeddings):
    mock_generate_embeddings.return_value = [[0.1] * 1536]
    session = CapturingMockSession()

    async def override_scoped_db():
        yield session

    app.dependency_overrides[get_db] = override_scoped_db
    app.dependency_overrides[get_readonly_db] = override_scoped_db
    try:
        with TestClient(
            app,
            headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
        ) as client:
            response = client.post("/api/search", json={"query": "test query"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    channel_statements = [
        stmt
        for stmt in session.statements
        if "word_similarity" in str(stmt).lower() or "<=>" in str(stmt).lower()
    ]
    assert channel_statements
    for channel_statement in channel_statements:
        statement_text = str(channel_statement).lower()
        assert "email_records.user_id" in statement_text
        assert "email_records.organization_id" in statement_text
        query_params = channel_statement.compile().params
        user_scope_params = {
            value for key, value in query_params.items() if key.startswith("user_id")
        }
        organization_scope_params = {
            value
            for key, value in query_params.items()
            if key.startswith("organization_id")
        }
        assert user_scope_params == {"testuser"}
        assert organization_scope_params == {"org-acme"}


@patch("api.search.generate_embeddings", new_callable=AsyncMock)
def test_search_falls_back_to_lexical_when_embedding_provider_fails(
    mock_generate_embeddings,
):
    mock_generate_embeddings.side_effect = EmbeddingGenerationError(
        "Failed to generate embeddings: invalid provider key"
    )
    session = CapturingMockSession()

    async def override_scoped_db():
        yield session

    app.dependency_overrides[get_db] = override_scoped_db
    app.dependency_overrides[get_readonly_db] = override_scoped_db
    try:
        with TestClient(
            app,
            headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
        ) as client:
            response = client.post("/api/search", json={"query": "test query"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    joined_statements = " ".join(str(stmt).lower() for stmt in session.statements)
    assert "word_similarity" in joined_statements
    assert "<=>" not in joined_statements


def test_search_runs_lexical_only_when_no_provider_is_configured():
    class NoProviderSession(CapturingMockSession):
        async def execute(self, stmt):
            statement_text = str(stmt).lower()
            if "tenant_configs" in statement_text:
                self.statements.append(stmt)
                return MockTenantConfigResult(None)
            return await super().execute(stmt)

        async def scalar(self, stmt):
            return None

    session = NoProviderSession()

    async def override_scoped_db():
        yield session

    app.dependency_overrides[get_db] = override_scoped_db
    app.dependency_overrides[get_readonly_db] = override_scoped_db
    try:
        with TestClient(
            app,
            headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
        ) as client:
            response = client.post("/api/search", json={"query": "test query"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    joined_statements = " ".join(str(stmt).lower() for stmt in session.statements)
    assert "word_similarity" in joined_statements
    assert "<=>" not in joined_statements


@patch("api.search.generate_embeddings", new_callable=AsyncMock)
def test_search_uses_primary_config_session_and_readonly_search_session(
    mock_generate_embeddings,
):
    provider = LLMProvider(
        id=4,
        user_id="admin",
        organization_id="org-acme",
        name="Local Gemma4",
        provider_type="ollama",
        base_url="http://ollama:11434/v1",
        model_identifier="gemma4",
        embedding_model="embeddinggemma",
        api_key=None,
        is_active=True,
    )
    mock_generate_embeddings.return_value = [[0.1] * 1536]
    config_session = CapturingMockSession(providers=[provider])
    search_session = CapturingMockSession()

    async def override_config_db():
        yield config_session

    async def override_search_db():
        yield search_session

    app.dependency_overrides[get_db] = override_config_db
    app.dependency_overrides[get_readonly_db] = override_search_db
    try:
        with TestClient(
            app,
            headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
        ) as client:
            response = client.post("/api/search", json={"query": "test query"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert config_session.statements
    assert search_session.statements
    assert any(
        "llm_providers" in str(stmt).lower() for stmt in config_session.statements
    )
    assert all(
        "word_similarity" not in str(stmt).lower() for stmt in config_session.statements
    )
    assert any(
        "word_similarity" in str(stmt).lower() for stmt in search_session.statements
    )


@patch("api.search.generate_embeddings", new_callable=AsyncMock)
def test_search_pads_local_embedding_dimension_for_vector_search(
    mock_generate_embeddings,
):
    mock_generate_embeddings.return_value = [[0.1] * 768]
    session = CapturingMockSession()

    async def override_scoped_db():
        yield session

    app.dependency_overrides[get_db] = override_scoped_db
    app.dependency_overrides[get_readonly_db] = override_scoped_db
    try:
        with TestClient(
            app,
            headers={"X-User-Id": "testuser", "X-Organization-Id": "org-acme"},
        ) as client:
            response = client.post("/api/search", json={"query": "test query"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    joined_statements = " ".join(str(stmt).lower() for stmt in session.statements)
    assert "<=>" in joined_statements


def test_search_module_has_no_language_dependent_fts():
    """G6 regression guard: no to_tsvector language configs in search."""
    import inspect
    from pathlib import Path

    from api.search import hybrid_search
    from services.hybrid_retrieval.retrieval_channels import (
        build_lexical_email_statement,
    )

    for module_member in (hybrid_search, build_lexical_email_statement):
        module_source = Path(inspect.getfile(module_member)).read_text()
        # Call forms, not prose mentions in docstrings.
        assert "to_tsvector(" not in module_source
        assert "plainto_tsquery(" not in module_source
        assert "ts_rank" not in module_source


def test_search_query_is_normalized_to_nfc_before_embedding_and_sql():
    import unicodedata

    from services.hybrid_retrieval import normalize_search_text

    decomposed_query = unicodedata.normalize("NFD", "Trần Hưng Đạo 회의")

    normalized_query = normalize_search_text("  " + decomposed_query + "  ")

    assert normalized_query == "Trần Hưng Đạo 회의"
    assert unicodedata.is_normalized("NFC", normalized_query)


def test_build_reply_counts_stmt_scopes_and_groups_by_thread_key():
    from api.search import build_reply_counts_stmt

    stmt = build_reply_counts_stmt(
        ["thread-1", "thread-2"],
        user_id="user1",
        organization_id="org1",
        workspace_id="workspace-a",
    )
    sql = str(stmt).lower()

    assert "email_records.user_id" in sql
    assert "email_records.organization_id" in sql
    assert "email_records.workspace_id" in sql
    assert "count(email_records.id)" in sql
    assert "group by coalesce(nullif(btrim(btrim(email_records.thread_id)" in sql


def test_lexical_attachment_statement_excludes_non_parsed_attachments():
    # Quarantined (content_type_mismatch_quarantined) and deferred-recognition
    # (pdf_dom_recognition_pending) attachments store a base64-encoded raw
    # payload in `content`, not parsed text -- hybrid search must not surface
    # that payload as if it were a genuine content match.
    from db.models import Email
    from services.hybrid_retrieval.retrieval_channels import (
        build_lexical_attachment_statement,
    )

    owner_filters = Email.owner_filters("user1", "org1", "workspace-a")

    stmt = build_lexical_attachment_statement("hello", owner_filters, 20)
    sql = str(stmt).lower()

    assert "email_attachments.parse_status" in sql


def test_dense_attachment_statement_excludes_non_parsed_attachments():
    from db.models import Email
    from services.hybrid_retrieval.retrieval_channels import (
        build_dense_attachment_statement,
    )

    owner_filters = Email.owner_filters("user1", "org1", "workspace-a")

    stmt = build_dense_attachment_statement([0.1] * 1536, owner_filters, 20)
    sql = str(stmt).lower()

    assert "email_attachments.parse_status" in sql


def _make_fusion_settings(**overrides):
    return FusionSettings(**overrides)


def test_merge_candidate_rows_accumulates_best_channel_evidence():
    from api.search import merge_candidate_rows

    fusion_settings = _make_fusion_settings()
    lexical_rows = [
        MockLexicalRow(1, "One", "a@example.com", "lexical body", 0.4),
        MockLexicalRow(2, "Two", "a@example.com", "other body", 0.2),
    ]
    segment_rows = [
        MockLexicalRow(
            1,
            "One",
            "a@example.com",
            "segment evidence",
            0.9,
            result_kind="content_segment",
        )
    ]
    dense_rows = [MockDenseRow(1, "One", "a@example.com", "dense body", 0.5)]

    candidates = merge_candidate_rows(
        [
            ("lexical_email", lexical_rows),
            ("lexical_content_segment", segment_rows),
            ("dense_email", dense_rows),
        ],
        fusion_settings,
    )

    assert set(candidates) == {1, 2}
    strongest_candidate = candidates[1]
    assert strongest_candidate.best_word_similarity == 0.9
    assert strongest_candidate.best_cosine_distance == 0.5
    assert strongest_candidate.evidence_kinds == {
        "email_body",
        "content_segment",
    }
    assert strongest_candidate.channel_ranks == {
        "lexical_email": 1,
        "lexical_content_segment": 1,
        "dense_email": 1,
    }
    # With the default semantic weight (0.7), the dense row's fused
    # evidence (0.7 * (1 - 0.5/2) = 0.525) outranks the segment row's
    # lexical-only evidence (0.3 * 0.9 = 0.27), so the dense row
    # provides the display snippet and result kind.
    assert strongest_candidate.primary_result_kind == "email_body"
    assert strongest_candidate.primary_matched_text == "dense body"


def test_build_search_result_items_orders_dedupes_and_limits():
    from api.search import build_search_result_items, merge_candidate_rows

    fusion_settings = _make_fusion_settings()
    rows = [
        MockLexicalRow(1, "One", "a@example.com", "body one", 0.9),
        MockLexicalRow(2, "Two", "a@example.com", "body two", 0.5),
        MockLexicalRow(3, "Three", "a@example.com", "body three", 0.7),
        MockLexicalRow(1, "One", "a@example.com", "body one again", 0.2),
    ]
    candidates = merge_candidate_rows([("lexical_email", rows)], fusion_settings)

    results = build_search_result_items(
        candidates, fusion_settings, limit=2, reply_counts_by_thread_key={}
    )

    assert [item.id for item in results] == [1, 3]
    assert results[0].score > results[1].score
    assert results[0].reply_count == 1


def test_build_search_result_items_truncates_long_snippets():
    from api.search import build_search_result_items, merge_candidate_rows

    fusion_settings = _make_fusion_settings()
    rows = [MockLexicalRow(1, "Long", "a@example.com", "A" * 300, 0.9)]
    candidates = merge_candidate_rows([("lexical_email", rows)], fusion_settings)

    results = build_search_result_items(
        candidates, fusion_settings, limit=10, reply_counts_by_thread_key={}
    )

    assert results[0].snippet == ("A" * 200) + "..."


def test_build_search_result_items_drops_below_minimum_score():
    from api.search import build_search_result_items, merge_candidate_rows

    fusion_settings = _make_fusion_settings()
    rows = [MockLexicalRow(1, "Weak", "a@example.com", "irrelevant", 0.01)]
    candidates = merge_candidate_rows([("lexical_email", rows)], fusion_settings)

    results = build_search_result_items(
        candidates, fusion_settings, limit=10, reply_counts_by_thread_key={}
    )

    assert results == []
