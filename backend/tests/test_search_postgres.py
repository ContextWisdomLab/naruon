"""PostgreSQL integration tests for language-agnostic hybrid search.

These run against a real PostgreSQL (pgvector image) and verify the G6
acceptance criteria end-to-end through the API:

- CJK queries match without any language config / morphological
  analyzer (the removed ``to_tsvector('english', ...)`` scaffolding
  could not do this);
- Vietnamese matches across NFC/NFD forms and with/without diacritics
  (``normalize(..., NFC)`` + ``unaccent`` on both sides);
- content_segments and project_graph_objects are searched (naruon#975);
- results stay owner-scoped;
- the dense channel fuses with the lexical channel per TM2C2.
"""

import dataclasses
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from asyncpg.exceptions import (
    InvalidAuthorizationSpecificationError,
    InvalidPasswordError,
)
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from db.models import (
    Base,
    ContentNodeRecord,
    ContentSegmentRecord,
    Email,
    ProjectGraphObjectRecord,
)
from db.session import get_db, get_readonly_db
from main import app

pytestmark = pytest.mark.postgres

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0010_language_agnostic_search.py"
)


def _load_search_migration_module():
    spec = importlib.util.spec_from_file_location(
        "migration_0010_language_agnostic_search", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _apply_language_agnostic_search_ddl(conn) -> None:
    migration_module = _load_search_migration_module()
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    await conn.execute(text(migration_module._NORMALIZE_FUNCTION_DDL))
    for create_index_statement in (
        migration_module._TRIGRAM_INDEX_STATEMENTS.values()
    ):
        await conn.execute(text(create_index_statement))


@pytest_asyncio.fixture(scope="function")
async def hybrid_search_sessionmaker():
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            await _apply_language_agnostic_search_ddl(conn)
        yield async_sessionmaker(engine, expire_on_commit=False)
    except (
        InvalidAuthorizationSpecificationError,
        InvalidPasswordError,
        OperationalError,
        OSError,
    ) as exc:
        pytest.skip(f"PostgreSQL smoke database unavailable: {exc}")
    finally:
        await engine.dispose()


@pytest.fixture
def hybrid_search_db_override(hybrid_search_sessionmaker):
    async def override_db():
        async with hybrid_search_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_readonly_db] = override_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_readonly_db, None)


def _client(*, user_id: str, organization_id: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={
            "X-User-Id": user_id,
            "X-Organization-Id": organization_id,
        },
    )


def _unit_embedding_vector(hot_index: int) -> list[float]:
    vector = [0.0] * 1536
    vector[hot_index] = 1.0
    return vector


def _make_email(
    *,
    user_id: str,
    organization_id: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
    embedding: list[float] | None = None,
) -> Email:
    return Email(
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=f"workspace-{organization_id}",
        message_id=f"<{uuid.uuid4().hex}@example.com>",
        thread_id=thread_id,
        sender="sender@example.com",
        recipients="owner@example.com",
        subject=subject,
        date=__import__("datetime").datetime(
            2026, 7, 10, 9, 0, tzinfo=__import__("datetime").timezone.utc
        ),
        body=body,
        embedding=embedding,
    )


async def _seed_segment_and_project_object(
    session,
    *,
    email: Email,
    user_id: str,
    organization_id: str,
    segment_text: str,
    object_title: str,
    object_summary: str,
) -> None:
    content_node = ContentNodeRecord(
        content_node_uid=uuid.uuid4().hex,
        email_id=email.id,
        source_kind="email_body",
        source_record_uid=email.message_id,
        node_kind="document",
        node_path="/document[1]",
        ordinal_index=0,
        safe_text_content="",
        content_hash=uuid.uuid4().hex,
    )
    session.add(content_node)
    await session.flush()
    content_segment = ContentSegmentRecord(
        content_segment_uid=uuid.uuid4().hex,
        email_id=email.id,
        content_node_id=content_node.content_node_id,
        source_kind="email_body",
        source_record_uid=email.message_id,
        segment_kind="paragraph",
        segment_path="/document[1]/paragraph[1]",
        ordinal_index=0,
        safe_text_content=segment_text,
        content_hash=uuid.uuid4().hex,
        word_count=len(segment_text.split()),
    )
    session.add(content_segment)
    await session.flush()
    session.add(
        ProjectGraphObjectRecord(
            object_uid=f"requirement:{uuid.uuid4().hex}",
            user_id=user_id,
            organization_id=organization_id,
            workspace_id="workspace-primary",
            email_id=email.id,
            primary_content_segment_id=content_segment.content_segment_id,
            object_type="requirement",
            title=object_title,
            summary=object_summary,
            status_code="candidate",
            confidence=0.9,
            source_segment_uids=[content_segment.content_segment_uid],
            attributes_json={},
            extractor_name="deterministic_reference",
            extractor_version="test",
        )
    )


@dataclasses.dataclass
class SeededSearchData:
    user_id: str
    organization_id: str
    korean_email_id: int
    vietnamese_email_id: int
    segment_email_id: int
    other_user_id: str


async def _seed_search_data(sessionmaker) -> SeededSearchData:
    user_id = f"search-user-{uuid.uuid4().hex}"
    other_user_id = f"search-other-{uuid.uuid4().hex}"
    organization_id = "org-acme"
    async with sessionmaker() as session:
        korean_email = _make_email(
            user_id=user_id,
            organization_id=organization_id,
            subject="다음주 회의 일정 공유",
            body="다음주 화요일 오후 3시에 회의 일정을 확정했습니다. 장소는 본사 대회의실입니다.",
            thread_id="<thread-korean@example.com>",
        )
        korean_reply = _make_email(
            user_id=user_id,
            organization_id=organization_id,
            subject="RE: 다음주 회의 일정 공유",
            body="확인했습니다. 회의 자료는 미리 보내드리겠습니다.",
            thread_id="<thread-korean@example.com>",
        )
        vietnamese_email = _make_email(
            user_id=user_id,
            organization_id=organization_id,
            subject="Lịch họp ban nhạc",
            body="Chúng ta sẽ họp ban nhạc vào tối thứ Sáu tại phòng tập quen thuộc.",
        )
        segment_email = _make_email(
            user_id=user_id,
            organization_id=organization_id,
            subject="첨부 문서 전달",
            body="문서를 첨부합니다.",
        )
        other_user_email = _make_email(
            user_id=other_user_id,
            organization_id=organization_id,
            subject="다음주 회의 일정 공유 (다른 사용자)",
            body="다른 사용자의 회의 일정입니다. 노출되면 안 됩니다.",
        )
        session.add_all(
            [
                korean_email,
                korean_reply,
                vietnamese_email,
                segment_email,
                other_user_email,
            ]
        )
        await session.flush()
        await _seed_segment_and_project_object(
            session,
            email=segment_email,
            user_id=user_id,
            organization_id=organization_id,
            segment_text="예산 승인 절차 안내: 부서장 결재 후 재무팀 검토가 필요합니다.",
            object_title="밴드 리허설 일정 조율",
            object_summary="금요일 저녁 리허설 확정을 위해 멤버 가용 시간을 수집한다.",
        )
        await session.commit()
        return SeededSearchData(
            user_id=user_id,
            organization_id=organization_id,
            korean_email_id=korean_email.id,
            vietnamese_email_id=vietnamese_email.id,
            segment_email_id=segment_email.id,
            other_user_id=other_user_id,
        )


async def _search(client: httpx.AsyncClient, query: str) -> list[dict]:
    response = await client.post("/api/search", json={"query": query})
    assert response.status_code == 200, response.text
    return response.json()["results"]


@pytest.mark.asyncio
async def test_korean_query_matches_without_language_config(
    dev_auth_dependency_overrides,
    hybrid_search_db_override,
    hybrid_search_sessionmaker,
):
    seeded = await _seed_search_data(hybrid_search_sessionmaker)

    async with _client(
        user_id=seeded.user_id, organization_id=seeded.organization_id
    ) as client:
        results = await _search(client, "회의 일정")

    result_ids = [item["id"] for item in results]
    assert seeded.korean_email_id in result_ids
    top_result = results[0]
    assert top_result["score"] > 0.0
    assert top_result["result_kind"] == "email_body"
    korean_result = next(
        item for item in results if item["id"] == seeded.korean_email_id
    )
    assert korean_result["reply_count"] == 2
    assert seeded.other_user_id not in {
        item["sender"] for item in results
    }  # sanity: sender field untouched


@pytest.mark.asyncio
async def test_vietnamese_matches_across_nfc_nfd_and_without_diacritics(
    dev_auth_dependency_overrides,
    hybrid_search_db_override,
    hybrid_search_sessionmaker,
):
    seeded = await _seed_search_data(hybrid_search_sessionmaker)

    decomposed_query = "họp ban nhạc"  # NFD-style combining marks
    ascii_query = "hop ban nhac"

    async with _client(
        user_id=seeded.user_id, organization_id=seeded.organization_id
    ) as client:
        decomposed_results = await _search(client, decomposed_query)
        ascii_results = await _search(client, ascii_query)

    assert seeded.vietnamese_email_id in [
        item["id"] for item in decomposed_results
    ]
    assert seeded.vietnamese_email_id in [item["id"] for item in ascii_results]


@pytest.mark.asyncio
async def test_content_segments_and_project_objects_are_searched(
    dev_auth_dependency_overrides,
    hybrid_search_db_override,
    hybrid_search_sessionmaker,
):
    seeded = await _seed_search_data(hybrid_search_sessionmaker)

    async with _client(
        user_id=seeded.user_id, organization_id=seeded.organization_id
    ) as client:
        segment_results = await _search(client, "예산 승인 절차")
        object_results = await _search(client, "밴드 리허설")

    segment_hit = next(
        item for item in segment_results if item["id"] == seeded.segment_email_id
    )
    assert segment_hit["result_kind"] == "content_segment"
    assert "예산 승인" in segment_hit["snippet"]

    object_hit = next(
        item for item in object_results if item["id"] == seeded.segment_email_id
    )
    assert "project_graph_object" in object_hit["evidence_kinds"]


@pytest.mark.asyncio
async def test_search_results_are_owner_scoped(
    dev_auth_dependency_overrides,
    hybrid_search_db_override,
    hybrid_search_sessionmaker,
):
    seeded = await _seed_search_data(hybrid_search_sessionmaker)

    async with _client(
        user_id=seeded.user_id, organization_id=seeded.organization_id
    ) as client:
        results = await _search(client, "회의 일정")

    assert results  # the owner sees their own emails
    async with hybrid_search_sessionmaker() as session:
        other_user_email_ids = {
            row for (row,) in (
                await session.execute(
                    text(
                        "SELECT id FROM email_records WHERE user_id = :user_id"
                    ),
                    {"user_id": seeded.other_user_id},
                )
            ).all()
        }
    assert other_user_email_ids
    assert not other_user_email_ids & {item["id"] for item in results}


@pytest.mark.asyncio
async def test_dense_channel_fuses_with_lexical_channel(
    dev_auth_dependency_overrides,
    hybrid_search_db_override,
    hybrid_search_sessionmaker,
):
    user_id = f"dense-user-{uuid.uuid4().hex}"
    organization_id = "org-acme"
    async with hybrid_search_sessionmaker() as session:
        semantic_only_email = _make_email(
            user_id=user_id,
            organization_id=organization_id,
            subject="Quarterly planning notes",
            body="Completely unrelated wording in this body.",
            embedding=_unit_embedding_vector(0),
        )
        lexical_match_email = _make_email(
            user_id=user_id,
            organization_id=organization_id,
            subject="semantic planning query",
            body="semantic planning query appears verbatim here.",
            embedding=_unit_embedding_vector(1),
        )
        session.add_all([semantic_only_email, lexical_match_email])
        await session.commit()
        semantic_only_email_id = semantic_only_email.id
        lexical_match_email_id = lexical_match_email.id

    class StubProvider:
        api_key = "stub-key"
        base_url = None
        embedding_model = "stub-embedding-model"

    with (
        patch(
            "api.search.resolve_runtime_llm_provider",
            new_callable=AsyncMock,
            return_value=StubProvider(),
        ),
        patch(
            "api.search.generate_embeddings",
            new_callable=AsyncMock,
            return_value=[_unit_embedding_vector(0)],
        ),
    ):
        async with _client(
            user_id=user_id, organization_id=organization_id
        ) as client:
            results = await _search(client, "semantic planning query")

    result_ids = [item["id"] for item in results]
    assert semantic_only_email_id in result_ids
    assert lexical_match_email_id in result_ids
    # TM2C2 with alpha=0.7: an exact embedding match (semantic score
    # 1.0 -> fused ~0.7 + lexical residue) outranks an exact lexical
    # match whose embedding is orthogonal to the query
    # (0.7 * 0.5 + 0.3 * ~1.0 = ~0.65).
    assert result_ids.index(semantic_only_email_id) < result_ids.index(
        lexical_match_email_id
    )
