import datetime
import uuid

import pytest
import pytest_asyncio
from asyncpg.exceptions import (
    InvalidAuthorizationSpecificationError,
    InvalidPasswordError,
)
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from db.models import (
    Base,
    ContentNodeRecord,
    ContentSegmentRecord,
    Email,
    ProjectGraphCorrectionRecord,
    ProjectGraphEdgeRecord,
    ProjectGraphObjectRecord,
)
from services.project_graph import (
    ProjectObjectType,
    ProjectSemanticEdge,
    ProjectSemanticExtractionResult,
    ProjectSemanticObject,
    ProjectSourceSegment,
    apply_project_graph_correction,
    extract_project_semantics,
    persist_project_graph_projection,
)


@pytest_asyncio.fixture(scope="function")
async def project_graph_sessionmaker():
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
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


@pytest.mark.asyncio
async def test_project_graph_projection_persists_source_cited_objects_and_edges(
    project_graph_sessionmaker,
):
    user_id = f"project-user-{uuid.uuid4().hex}"
    organization_id = f"org-projection-{uuid.uuid4().hex[:12]}"
    workspace_id = f"workspace-{organization_id}"
    async with project_graph_sessionmaker() as session:
        segment = await _seed_source_segment(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        extraction = extract_project_semantics([_source_segment(segment)])

        result = await persist_project_graph_projection(
            session,
            extraction=extraction,
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        await session.commit()

        # The deterministic reference extractor emits a REQUIREMENT and a
        # FEATURE for the seeded sentence; assert on the requirement and
        # its evidence edge specifically.
        assert len(result.objects) == 2
        assert len(result.edges) == 2
        assert sorted(obj.object_type for obj in result.objects) == [
            "feature",
            "requirement",
        ]
        persisted_object = next(
            obj for obj in result.objects if obj.object_type == "requirement"
        )
        persisted_edge = next(
            edge
            for edge in result.edges
            if edge.target_object_id == persisted_object.project_graph_object_id
        )
        assert persisted_object.user_id == user_id
        assert persisted_object.organization_id == organization_id
        assert persisted_object.workspace_id == workspace_id
        assert persisted_object.primary_content_segment_id == segment.content_segment_id
        assert persisted_object.source_segment_uids == [segment.content_segment_uid]
        assert persisted_object.attributes_json["source_record_uid"] == (
            segment.source_record_uid
        )
        assert persisted_edge.target_object_id == persisted_object.project_graph_object_id
        assert persisted_edge.source_uid == f"segment:{segment.content_segment_uid}"
        assert persisted_edge.source_segment_uids == [segment.content_segment_uid]


@pytest.mark.asyncio
async def test_project_graph_projection_persists_object_to_object_edges(
    project_graph_sessionmaker,
):
    user_id = f"project-user-{uuid.uuid4().hex}"
    organization_id = "org-acme"
    workspace_id = "workspace-org-acme"
    async with project_graph_sessionmaker() as session:
        segment = await _seed_source_segment(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        segment_uid = segment.content_segment_uid
        feature = ProjectSemanticObject(
            uid=f"feature:{uuid.uuid4().hex[:16]}",
            object_type=ProjectObjectType.FEATURE,
            title="Feature: retry banner",
            summary="Show a retry banner on card decline.",
            source_segment_uids=(segment_uid,),
            confidence=0.8,
            extractor_name="llm_grounded_project_graph",
            extractor_version="test",
        )
        requirement = ProjectSemanticObject(
            uid=f"requirement:{uuid.uuid4().hex[:16]}",
            object_type=ProjectObjectType.REQUIREMENT,
            title="Requirement: handle card declines",
            summary="The checkout must handle card declines.",
            source_segment_uids=(segment_uid,),
            confidence=0.9,
            extractor_name="llm_grounded_project_graph",
            extractor_version="test",
        )
        relation_edge = ProjectSemanticEdge(
            source_uid=feature.uid,
            target_uid=requirement.uid,
            edge_type="implements",
            confidence=0.7,
            source_segment_uids=(segment_uid,),
        )
        extraction = ProjectSemanticExtractionResult(
            objects=(feature, requirement),
            edges=(relation_edge,),
            extractor_name="llm_grounded_project_graph",
            extractor_version="test",
        )

        result = await persist_project_graph_projection(
            session,
            extraction=extraction,
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        await session.commit()

        assert len(result.objects) == 2
        assert len(result.edges) == 1
        persisted_edge = result.edges[0]
        object_ids = {obj.project_graph_object_id for obj in result.objects}
        # The object-to-object edge wires both endpoints to persisted objects,
        # so the graph carries a real inter-object relationship (not just
        # segment evidence).
        assert persisted_edge.edge_type == "implements"
        assert persisted_edge.source_object_id in object_ids
        assert persisted_edge.target_object_id in object_ids
        assert persisted_edge.source_object_id != persisted_edge.target_object_id
        assert persisted_edge.source_segment_uids == [segment_uid]


@pytest.mark.asyncio
async def test_project_graph_projection_upserts_existing_records(
    project_graph_sessionmaker,
):
    user_id = f"project-user-{uuid.uuid4().hex}"
    organization_id = f"org-projection-{uuid.uuid4().hex[:12]}"
    workspace_id = f"workspace-{organization_id}"
    async with project_graph_sessionmaker() as session:
        segment = await _seed_source_segment(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        extraction = extract_project_semantics([_source_segment(segment)])

        await persist_project_graph_projection(
            session,
            extraction=extraction,
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        await persist_project_graph_projection(
            session,
            extraction=extraction,
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            status_code="confirmed",
        )
        await session.commit()

        object_count = await session.scalar(
            select(func.count()).select_from(ProjectGraphObjectRecord).where(
                ProjectGraphObjectRecord.user_id == user_id
            )
        )
        edge_count = await session.scalar(
            select(func.count()).select_from(ProjectGraphEdgeRecord).where(
                ProjectGraphEdgeRecord.user_id == user_id
            )
        )
        persisted_objects = (
            await session.scalars(
                select(ProjectGraphObjectRecord).where(
                    ProjectGraphObjectRecord.user_id == user_id
                )
            )
        ).all()

        # Re-running the projection upserts the same two extracted
        # objects (requirement + feature) instead of duplicating them.
        assert object_count == 2
        assert edge_count == 2
        assert persisted_objects
        assert {obj.status_code for obj in persisted_objects} == {"confirmed"}


@pytest.mark.asyncio
async def test_project_graph_correction_records_before_after_and_updates_projection(
    project_graph_sessionmaker,
):
    user_id = f"project-user-{uuid.uuid4().hex}"
    organization_id = f"org-projection-{uuid.uuid4().hex[:12]}"
    workspace_id = f"workspace-{organization_id}"
    async with project_graph_sessionmaker() as session:
        segment = await _seed_source_segment(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        extraction = extract_project_semantics([_source_segment(segment)])
        result = await persist_project_graph_projection(
            session,
            extraction=extraction,
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )

        correction = await apply_project_graph_correction(
            session,
            object_uid=result.objects[0].object_uid,
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id="reviewer",
            correction_action="confirm_requirement",
            after_json={
                "status_code": "approved",
                "title": "Requirement: confirmed checkout retry guidance",
            },
            rationale="Reviewed against the source segment.",
        )
        await session.commit()

        persisted_object = await session.get(
            ProjectGraphObjectRecord,
            result.objects[0].project_graph_object_id,
        )
        persisted_correction = await session.get(
            ProjectGraphCorrectionRecord,
            correction.project_graph_correction_id,
        )

        assert persisted_object is not None
        assert persisted_object.status_code == "approved"
        assert persisted_object.title == "Requirement: confirmed checkout retry guidance"
        assert persisted_correction is not None
        assert persisted_correction.before_json["status_code"] == "candidate"
        assert persisted_correction.after_json["status_code"] == "approved"
        assert persisted_correction.source_segment_uids == [segment.content_segment_uid]


@pytest.mark.asyncio
async def test_project_graph_projection_rejects_cross_scope_source_segments(
    project_graph_sessionmaker,
):
    organization_id = f"org-projection-{uuid.uuid4().hex[:12]}"
    async with project_graph_sessionmaker() as session:
        segment = await _seed_source_segment(
            session,
            user_id=f"project-user-{uuid.uuid4().hex}",
            organization_id=organization_id,
        )
        extraction = extract_project_semantics([_source_segment(segment)])

        with pytest.raises(ValueError, match="different scope"):
            await persist_project_graph_projection(
                session,
                extraction=extraction,
                user_id="different-user",
                organization_id=organization_id,
                workspace_id=f"workspace-{organization_id}",
            )


async def _seed_source_segment(
    session,
    *,
    user_id: str,
    organization_id: str,
) -> ContentSegmentRecord:
    await _cleanup_user(session, user_id)
    now = datetime.datetime.now(datetime.timezone.utc)
    email = Email(
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=f"workspace-{organization_id}",
        message_id=f"<{uuid.uuid4().hex}@example.com>",
        thread_id=f"thread-{uuid.uuid4().hex}",
        fingerprint=f"sha256:{uuid.uuid4().hex}",
        sender="partner@example.com",
        recipients="owner@example.com",
        subject="Project Alpha requirements",
        date=now,
        body="요구사항 본문",
    )
    session.add(email)
    await session.flush()
    node = ContentNodeRecord(
        content_node_uid=f"node-{uuid.uuid4().hex[:16]}",
        email_id=email.id,
        attachment_id=None,
        source_kind="email_body",
        source_record_uid=email.message_id,
        parent_node_uid=None,
        node_kind="document",
        node_path="/document[1]",
        ordinal_index=1,
        display_label="body",
        safe_text_content="요구사항 문단",
        content_hash=uuid.uuid4().hex,
        created_at=now,
    )
    session.add(node)
    await session.flush()
    segment = ContentSegmentRecord(
        content_segment_uid=f"seg-{uuid.uuid4().hex[:16]}",
        email_id=email.id,
        attachment_id=None,
        content_node_id=node.content_node_id,
        source_kind="email_body",
        source_record_uid=email.message_id,
        segment_kind="paragraph",
        segment_path="/document[1]/paragraph[1]",
        ordinal_index=1,
        heading_path="Requirements",
        safe_text_content=(
            "요구사항: 결제 화면은 카드 승인 실패 시 재시도 안내를 반드시 보여줘야 합니다."
        ),
        content_hash=uuid.uuid4().hex,
        word_count=9,
        created_at=now,
    )
    session.add(segment)
    await session.flush()
    return segment


def _source_segment(segment: ContentSegmentRecord) -> ProjectSourceSegment:
    return ProjectSourceSegment(
        content_segment_uid=segment.content_segment_uid,
        source_kind=segment.source_kind,
        source_record_uid=segment.source_record_uid,
        safe_text_content=segment.safe_text_content,
        heading_path=segment.heading_path,
        segment_path=segment.segment_path,
        ordinal_index=segment.ordinal_index,
    )


async def _cleanup_user(session, user_id: str) -> None:
    await session.execute(
        delete(ProjectGraphCorrectionRecord).where(
            ProjectGraphCorrectionRecord.user_id == user_id
        )
    )
    await session.execute(
        delete(ProjectGraphEdgeRecord).where(ProjectGraphEdgeRecord.user_id == user_id)
    )
    await session.execute(
        delete(ProjectGraphObjectRecord).where(
            ProjectGraphObjectRecord.user_id == user_id
        )
    )
    await session.execute(delete(Email).where(Email.user_id == user_id))
    await session.flush()
