import datetime
import uuid

import httpx
import pytest
import pytest_asyncio
from asyncpg.exceptions import (
    InvalidAuthorizationSpecificationError,
    InvalidPasswordError,
)
from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api.projects as projects_api
from db.models import (
    Base,
    ContentNodeRecord,
    ContentSegmentRecord,
    Email,
    ProjectGraphCorrectionRecord,
    ProjectGraphEdgeRecord,
    ProjectGraphObjectRecord,
)
from db.session import get_db
from main import app
from services.project_graph import (
    ProjectCandidateSummary,
    ProjectCitation,
    ProjectCorrection,
    ProjectDecisionRecord,
    ProjectDecisionView,
    ProjectEvidence,
    ProjectGraphNotFoundError,
    ProjectRelationSummary,
    ProjectRelationTypeSummary,
    ProjectSourceSegment,
    ProjectTraceEdge,
    ProjectTraceObject,
    ProjectTraceRelation,
    ProjectTraceRelationEndpoint,
    ProjectTraceability,
    extract_project_semantics,
    persist_project_graph_projection,
)
from core.config import settings


@pytest.mark.asyncio
async def test_project_candidates_endpoint_maps_scope_without_database(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    captured = {}
    observed_at = datetime.datetime.now(datetime.timezone.utc)

    async def fake_list_project_candidates(session, *, scope, limit):
        captured["scope"] = scope
        captured["limit"] = limit
        return (
            ProjectCandidateSummary(
                candidate_uid="project_candidate:test",
                project_uid="project_candidate:test",
                title="Project: API contract",
                status_code="candidate",
                score=0.91,
                object_count=3,
                requirement_count=1,
                issue_count=1,
                milestone_count=0,
                deliverable_count=1,
                participant_count=0,
                source_segment_count=1,
                representative_object_uids=("requirement:test",),
                citation_bundle=(
                    ProjectCitation(
                        content_segment_uid="seg-test",
                        source_kind="email_body",
                        source_record_uid="<api@example.com>",
                        heading_path="Requirements",
                        segment_path="/document[1]/paragraph[1]",
                        ordinal_index=1,
                        safe_text_excerpt="요구사항 근거 문단",
                    ),
                ),
                updated_at=observed_at,
            ),
        )

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "list_project_candidates",
        fake_list_project_candidates,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
            role="organization_admin",
        ) as client:
            response = await client.get("/api/projects/candidates?limit=5")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert captured["limit"] == 5
    assert captured["scope"].can_read_organization_scope is True
    candidate = response.json()["candidates"][0]
    assert candidate["candidate_uid"] == "project_candidate:test"
    assert candidate["citation_bundle"][0]["safe_text_excerpt"] == "요구사항 근거 문단"


@pytest.mark.asyncio
async def test_project_correction_endpoint_commits_and_returns_audit_trail(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    captured = {}
    observed_at = datetime.datetime.now(datetime.timezone.utc)

    class DummySession:
        committed = False

        async def commit(self):
            self.committed = True

    dummy_session = DummySession()

    async def fake_apply_project_correction(session, **kwargs):
        captured["session"] = session
        captured.update(kwargs)
        return ProjectCorrection(
            correction_uid="project_correction_test",
            object_uid=kwargs["object_uid"],
            correction_action=kwargs["correction_action"],
            before_json={"status_code": "candidate"},
            after_json=kwargs["after_json"],
            rationale=kwargs["rationale"],
            actor_user_id=kwargs["actor_user_id"],
            source_segment_uids=("seg-test",),
            created_at=observed_at,
        )

    async def override_get_db():
        yield dummy_session

    monkeypatch.setattr(
        projects_api,
        "apply_project_correction",
        fake_apply_project_correction,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.post(
                "/api/projects/project_candidate:test/corrections",
                json={
                    "object_uid": "requirement:test",
                    "correction_action": "confirm_requirement",
                    "after_json": {"status_code": "approved"},
                    "rationale": "reviewed",
                    "source_segment_uids": ["seg-test"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert dummy_session.committed is True
    assert captured["actor_user_id"] == "reviewer"
    assert captured["project_uid"] == "project_candidate:test"
    assert captured["source_segment_uids"] == ("seg-test",)
    body = response.json()
    assert body["before_json"]["status_code"] == "candidate"
    assert body["after_json"]["status_code"] == "approved"


@pytest.mark.asyncio
async def test_project_traceability_endpoint_serializes_typed_relations(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    captured = {}

    def _citation() -> ProjectCitation:
        return ProjectCitation(
            content_segment_uid="seg-rel",
            source_kind="email_body",
            source_record_uid="<launch@example.com>",
            heading_path="Requirements",
            segment_path="/document[1]/paragraph[1]",
            ordinal_index=1,
            safe_text_excerpt="feature implements the retry requirement",
        )

    feature = ProjectTraceObject(
        object_uid="feature:aaa",
        object_type="feature",
        title="Feature: checkout retry",
        summary="retry the failed card authorization",
        status_code="candidate",
        confidence=0.82,
        source_segment_uids=("seg-rel",),
        citation_bundle=(_citation(),),
        attributes={},
    )
    requirement = ProjectTraceObject(
        object_uid="requirement:bbb",
        object_type="requirement",
        title="Requirement: retry guidance",
        summary="show retry guidance on auth failure",
        status_code="candidate",
        confidence=0.9,
        source_segment_uids=("seg-rel",),
        citation_bundle=(_citation(),),
        attributes={},
    )
    evidence_edge = ProjectTraceEdge(
        edge_uid="project_edge:ev",
        source_uid="segment:seg-rel",
        target_uid="requirement:bbb",
        edge_type="segment_evidences_project_object",
        confidence=0.9,
        source_segment_uids=("seg-rel",),
        citation_bundle=(_citation(),),
    )
    relation_edge = ProjectTraceEdge(
        edge_uid="project_edge:rel",
        source_uid="feature:aaa",
        target_uid="requirement:bbb",
        edge_type="implements",
        confidence=0.88,
        source_segment_uids=("seg-rel",),
        citation_bundle=(_citation(),),
    )
    relation = ProjectTraceRelation(
        relation_uid="project_edge:rel",
        relation_type="implements",
        source=ProjectTraceRelationEndpoint(
            object_uid="feature:aaa",
            object_type="feature",
            title="Feature: checkout retry",
        ),
        target=ProjectTraceRelationEndpoint(
            object_uid="requirement:bbb",
            object_type="requirement",
            title="Requirement: retry guidance",
        ),
        confidence=0.88,
        source_segment_uids=("seg-rel",),
        citation_bundle=(_citation(),),
    )
    candidate = ProjectCandidateSummary(
        candidate_uid="project_candidate:test",
        project_uid="project_candidate:test",
        title="Project: checkout",
        status_code="candidate",
        score=0.9,
        object_count=2,
        requirement_count=1,
        issue_count=0,
        milestone_count=0,
        deliverable_count=0,
        participant_count=0,
        source_segment_count=1,
        representative_object_uids=("feature:aaa",),
        citation_bundle=(_citation(),),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
    )

    async def fake_get_project_traceability(session, *, scope, project_uid):
        captured["project_uid"] = project_uid
        return ProjectTraceability(
            project_uid=project_uid,
            candidate=candidate,
            objects=(feature, requirement),
            edges=(evidence_edge, relation_edge),
            relations=(relation,),
        )

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "get_project_traceability",
        fake_get_project_traceability,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.get(
                "/api/projects/project_candidate:test/traceability"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert captured["project_uid"] == "project_candidate:test"
    # Raw edges stay unchanged (backward compatible): both edge kinds present.
    assert {edge["edge_type"] for edge in body["edges"]} == {
        "segment_evidences_project_object",
        "implements",
    }
    # Relations expose only the typed object-to-object edge with both endpoints
    # resolved, so a consumer can render *why* the objects connect.
    assert len(body["relations"]) == 1
    surfaced = body["relations"][0]
    assert surfaced["relation_uid"] == "project_edge:rel"
    assert surfaced["relation_type"] == "implements"
    assert surfaced["source"]["object_type"] == "feature"
    assert surfaced["source"]["title"] == "Feature: checkout retry"
    assert surfaced["target"]["object_type"] == "requirement"
    assert surfaced["target"]["object_uid"] == "requirement:bbb"
    assert surfaced["confidence"] == 0.88
    assert surfaced["citation_bundle"][0]["content_segment_uid"] == "seg-rel"


@pytest.mark.asyncio
async def test_project_evidence_endpoint_serializes_incident_relations(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    def _citation() -> ProjectCitation:
        return ProjectCitation(
            content_segment_uid="seg-rel",
            source_kind="email_body",
            source_record_uid="<launch@example.com>",
            heading_path="Requirements",
            segment_path="/document[1]/paragraph[1]",
            ordinal_index=1,
            safe_text_excerpt="feature implements the retry requirement",
        )

    relation = ProjectTraceRelation(
        relation_uid="project_edge:rel",
        relation_type="implements",
        source=ProjectTraceRelationEndpoint(
            object_uid="feature:aaa",
            object_type="feature",
            title="Feature: checkout retry",
        ),
        target=ProjectTraceRelationEndpoint(
            object_uid="requirement:bbb",
            object_type="requirement",
            title="Requirement: retry guidance",
        ),
        confidence=0.88,
        source_segment_uids=("seg-rel",),
        citation_bundle=(_citation(),),
    )

    async def fake_get_project_evidence(session, *, scope, project_uid, object_uid):
        assert object_uid == "feature:aaa"
        return ProjectEvidence(
            project_uid=project_uid,
            object_uid=object_uid,
            object_type="feature",
            title="Feature: checkout retry",
            summary="retry the failed card authorization",
            status_code="candidate",
            confidence=0.82,
            citation_bundle=(_citation(),),
            relations=(relation,),
        )

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "get_project_evidence",
        fake_get_project_evidence,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.get(
                "/api/projects/project_candidate:test/evidence/feature:aaa"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    # Existing evidence fields stay unchanged (backward compatible).
    assert body["object_uid"] == "feature:aaa"
    assert body["citation_bundle"][0]["content_segment_uid"] == "seg-rel"
    # The object's typed relations are inlined with both endpoints resolved so
    # the evidence drill-down can render *why* it connects to other objects.
    assert len(body["relations"]) == 1
    surfaced = body["relations"][0]
    assert surfaced["relation_uid"] == "project_edge:rel"
    assert surfaced["relation_type"] == "implements"
    assert surfaced["source"]["object_uid"] == "feature:aaa"
    assert surfaced["target"]["object_uid"] == "requirement:bbb"
    assert surfaced["citation_bundle"][0]["content_segment_uid"] == "seg-rel"


@pytest_asyncio.fixture(scope="function")
async def project_graph_api_sessionmaker():
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


@pytest.fixture
def project_graph_api_db_override(project_graph_api_sessionmaker):
    async def override_get_db():
        async with project_graph_api_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_project_graph_api_exposes_candidates_traceability_and_corrections(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    user_id = f"project-api-user-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        await _seed_projection(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        candidates_response = await client.get("/api/projects/candidates")
        assert candidates_response.status_code == 200
        candidates = candidates_response.json()["candidates"]
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate["candidate_uid"].startswith("project_candidate:")
        assert candidate["source_segment_count"] == 1
        assert candidate["requirement_count"] == 1
        assert candidate["issue_count"] == 1
        assert candidate["milestone_count"] == 1
        assert candidate["deliverable_count"] == 1
        assert candidate["citation_bundle"][0]["segment_path"] == (
            "/document[1]/paragraph[1]"
        )

        confirm_response = await client.post(
            f"/api/projects/candidates/{candidate['candidate_uid']}/confirm"
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status_code"] == "confirmed"

        trace_response = await client.get(
            f"/api/projects/{candidate['project_uid']}/traceability"
        )
        assert trace_response.status_code == 200
        traceability = trace_response.json()
        assert traceability["project_uid"] == candidate["project_uid"]
        assert len(traceability["objects"]) >= 6
        assert all(item["citation_bundle"] for item in traceability["objects"])
        assert any(
            edge["edge_type"] == "segment_evidences_project_object"
            for edge in traceability["edges"]
        )

        requirement = next(
            item
            for item in traceability["objects"]
            if item["object_type"] == "requirement"
        )
        evidence_response = await client.get(
            f"/api/projects/{candidate['project_uid']}"
            f"/evidence/{requirement['object_uid']}"
        )
        assert evidence_response.status_code == 200
        evidence = evidence_response.json()
        assert evidence["object_uid"] == requirement["object_uid"]
        assert "결제 화면" in evidence["citation_bundle"][0]["safe_text_excerpt"]

        correction_response = await client.post(
            f"/api/projects/{candidate['project_uid']}/corrections",
            json={
                "object_uid": requirement["object_uid"],
                "correction_action": "confirm_requirement",
                "after_json": {
                    "status_code": "approved",
                    "title": "Requirement: approved checkout retry guidance",
                },
                "rationale": "Reviewed with cited source paragraph.",
            },
        )
        assert correction_response.status_code == 200
        correction = correction_response.json()
        assert correction["before_json"]["status_code"] == "confirmed"
        assert correction["after_json"]["status_code"] == "approved"
        assert correction["source_segment_uids"] == [
            evidence["citation_bundle"][0]["content_segment_uid"]
        ]

        updated_evidence_response = await client.get(
            f"/api/projects/{candidate['project_uid']}"
            f"/evidence/{requirement['object_uid']}"
        )
        assert updated_evidence_response.status_code == 200
        assert updated_evidence_response.json()["status_code"] == "approved"


@pytest.mark.asyncio
async def test_project_graph_api_enforces_member_scope_and_allows_org_admin(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    owner_id = f"project-api-owner-{uuid.uuid4().hex}"
    other_user_id = f"project-api-other-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        await _seed_projection(
            session,
            user_id=owner_id,
            organization_id=organization_id,
        )

    async with _client(
        user_id=other_user_id,
        organization_id=organization_id,
    ) as client:
        response = await client.get("/api/projects/candidates")
        assert response.status_code == 200
        assert response.json()["candidates"] == []

    async with _client(
        user_id=other_user_id,
        organization_id=organization_id,
        role="organization_admin",
    ) as client:
        response = await client.get("/api/projects/candidates")
        assert response.status_code == 200
        candidates = response.json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["source_segment_count"] == 1


@pytest.mark.asyncio
async def test_project_graph_api_returns_404_when_evidence_segment_is_stale(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    user_id = f"project-api-stale-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        seeded = await _seed_projection(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        project_object = await session.scalar(
            select(ProjectGraphObjectRecord).where(
                ProjectGraphObjectRecord.object_type == "requirement",
                ProjectGraphObjectRecord.user_id == user_id,
            )
        )
        assert project_object is not None
        project_object.source_segment_uids = ["missing-segment"]
        await session.commit()

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        response = await client.get(
            f"/api/projects/{seeded['candidate_uid']}"
            f"/evidence/{project_object.object_uid}"
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Project graph source evidence not found"


@pytest.mark.asyncio
async def test_project_traceability_surfaces_typed_object_to_object_relation(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    user_id = f"project-api-rel-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        seeded = await _seed_projection(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        before = await client.get(
            f"/api/projects/{seeded['candidate_uid']}/traceability"
        )
        assert before.status_code == 200
        before_body = before.json()
        # The deterministic seed extractor only emits segment-evidence edges, so
        # no evidence edge may leak into relations.
        assert before_body["edges"]
        assert before_body["relations"] == []

    async with project_graph_api_sessionmaker() as session:
        objects = (
            (
                await session.execute(
                    select(ProjectGraphObjectRecord)
                    .where(ProjectGraphObjectRecord.user_id == user_id)
                    .where(ProjectGraphObjectRecord.object_type != "project_candidate")
                    .order_by(ProjectGraphObjectRecord.object_uid.asc())
                )
            )
            .scalars()
            .all()
        )
        assert len(objects) >= 2
        source_object, target_object = objects[0], objects[1]
        segment = await session.scalar(
            select(ContentSegmentRecord).where(
                ContentSegmentRecord.content_segment_uid == seeded["segment_uid"]
            )
        )
        assert segment is not None
        session.add(
            ProjectGraphEdgeRecord(
                edge_uid=f"project_edge:test-{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                organization_id=organization_id,
                workspace_id=f"workspace-{organization_id}",
                source_uid=source_object.object_uid,
                target_uid=target_object.object_uid,
                edge_type="implements",
                confidence=0.86,
                source_segment_uids=[seeded["segment_uid"]],
                source_object=source_object,
                target_object=target_object,
                primary_content_segment_id=segment.content_segment_id,
            )
        )
        await session.commit()

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        after = await client.get(
            f"/api/projects/{seeded['candidate_uid']}/traceability"
        )
        assert after.status_code == 200
        relations = after.json()["relations"]
        assert len(relations) == 1
        relation = relations[0]
        assert relation["relation_type"] == "implements"
        assert relation["source"]["object_uid"] == source_object.object_uid
        assert relation["source"]["object_type"] == source_object.object_type
        assert relation["target"]["object_uid"] == target_object.object_uid
        assert relation["confidence"] == 0.86
        # Grounded: the relation carries the endpoint citation, not a bare edge.
        assert relation["citation_bundle"]
        assert relation["citation_bundle"][0]["content_segment_uid"] == (
            seeded["segment_uid"]
        )


@pytest.mark.asyncio
async def test_project_evidence_surfaces_incident_object_relation(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    user_id = f"project-api-evrel-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        seeded = await _seed_projection(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )

    async with project_graph_api_sessionmaker() as session:
        objects = (
            (
                await session.execute(
                    select(ProjectGraphObjectRecord)
                    .where(ProjectGraphObjectRecord.user_id == user_id)
                    .where(ProjectGraphObjectRecord.object_type != "project_candidate")
                    .order_by(ProjectGraphObjectRecord.object_uid.asc())
                )
            )
            .scalars()
            .all()
        )
        assert len(objects) >= 3
        source_object, target_object, unrelated_object = (
            objects[0],
            objects[1],
            objects[2],
        )
        segment = await session.scalar(
            select(ContentSegmentRecord).where(
                ContentSegmentRecord.content_segment_uid == seeded["segment_uid"]
            )
        )
        assert segment is not None
        session.add(
            ProjectGraphEdgeRecord(
                edge_uid=f"project_edge:test-{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                organization_id=organization_id,
                workspace_id=f"workspace-{organization_id}",
                source_uid=source_object.object_uid,
                target_uid=target_object.object_uid,
                edge_type="implements",
                confidence=0.86,
                source_segment_uids=[seeded["segment_uid"]],
                source_object=source_object,
                target_object=target_object,
                primary_content_segment_id=segment.content_segment_id,
            )
        )
        await session.commit()

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        # Outbound: the source object's evidence names the relation it drives.
        source_response = await client.get(
            f"/api/projects/{seeded['candidate_uid']}"
            f"/evidence/{source_object.object_uid}"
        )
        assert source_response.status_code == 200
        source_evidence = source_response.json()
        # Existing evidence contract is unchanged (backward compatible).
        assert source_evidence["object_uid"] == source_object.object_uid
        assert source_evidence["citation_bundle"]
        assert len(source_evidence["relations"]) == 1
        outbound = source_evidence["relations"][0]
        assert outbound["relation_type"] == "implements"
        assert outbound["source"]["object_uid"] == source_object.object_uid
        assert outbound["target"]["object_uid"] == target_object.object_uid
        assert outbound["confidence"] == 0.86
        # Grounded: the relation carries the endpoint citation.
        assert outbound["citation_bundle"][0]["content_segment_uid"] == (
            seeded["segment_uid"]
        )

        # Inbound: the target object's evidence names the same relation.
        target_response = await client.get(
            f"/api/projects/{seeded['candidate_uid']}"
            f"/evidence/{target_object.object_uid}"
        )
        assert target_response.status_code == 200
        target_evidence = target_response.json()
        assert len(target_evidence["relations"]) == 1
        assert target_evidence["relations"][0]["relation_uid"] == (
            outbound["relation_uid"]
        )

        # An object that is neither endpoint has no incident relations, and a
        # segment-evidence edge never leaks into relations.
        unrelated_response = await client.get(
            f"/api/projects/{seeded['candidate_uid']}"
            f"/evidence/{unrelated_object.object_uid}"
        )
        assert unrelated_response.status_code == 200
        assert unrelated_response.json()["relations"] == []


@pytest.mark.asyncio
async def test_project_relation_summary_endpoint_serializes_distribution(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    captured = {}

    summary = ProjectRelationSummary(
        project_uid="project_candidate:test",
        relation_count=3,
        grounded_relation_count=2,
        relation_types=(
            ProjectRelationTypeSummary(
                relation_type="implements",
                relation_count=2,
                grounded_relation_count=1,
                source_object_types=("feature",),
                target_object_types=("requirement",),
            ),
            ProjectRelationTypeSummary(
                relation_type="blocks",
                relation_count=1,
                grounded_relation_count=1,
                source_object_types=("issue",),
                target_object_types=("milestone",),
            ),
        ),
    )

    async def fake_get_project_relation_summary(session, *, scope, project_uid):
        captured["project_uid"] = project_uid
        captured["scope"] = scope
        return summary

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "get_project_relation_summary",
        fake_get_project_relation_summary,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.get(
                "/api/projects/project_candidate:test/relations/summary"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert captured["project_uid"] == "project_candidate:test"
    assert body["project_uid"] == "project_candidate:test"
    assert body["relation_count"] == 3
    assert body["grounded_relation_count"] == 2
    # Count-descending order is preserved through serialization.
    assert [item["relation_type"] for item in body["relation_types"]] == [
        "implements",
        "blocks",
    ]
    implements = body["relation_types"][0]
    assert implements["relation_count"] == 2
    assert implements["grounded_relation_count"] == 1
    assert implements["source_object_types"] == ["feature"]
    assert implements["target_object_types"] == ["requirement"]


@pytest.mark.asyncio
async def test_project_relation_summary_endpoint_returns_404_when_missing(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    async def fake_get_project_relation_summary(session, *, scope, project_uid):
        raise ProjectGraphNotFoundError("Project candidate not found")

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "get_project_relation_summary",
        fake_get_project_relation_summary,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.get(
                "/api/projects/project_candidate:missing/relations/summary"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project candidate not found"


@pytest.mark.asyncio
async def test_project_decisions_endpoint_serializes_decision_slice(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    captured = {}

    def _citation() -> ProjectCitation:
        return ProjectCitation(
            content_segment_uid="seg-dec",
            source_kind="email_body",
            source_record_uid="<launch@example.com>",
            heading_path="Decisions",
            segment_path="/document[1]/paragraph[1]",
            ordinal_index=1,
            safe_text_excerpt="결제 재시도 안내 도입을 최종 확정했습니다",
        )

    relation = ProjectTraceRelation(
        relation_uid="project_edge:rel",
        relation_type="resolves",
        source=ProjectTraceRelationEndpoint(
            object_uid="decision:aaa",
            object_type="decision",
            title="Decision: adopt retry",
        ),
        target=ProjectTraceRelationEndpoint(
            object_uid="issue:bbb",
            object_type="issue",
            title="Issue: approval blocker",
        ),
        confidence=0.88,
        source_segment_uids=("seg-dec",),
        citation_bundle=(_citation(),),
    )
    view = ProjectDecisionView(
        project_uid="project_candidate:test",
        decision_count=1,
        grounded_decision_count=1,
        decisions=(
            ProjectDecisionRecord(
                object_uid="decision:aaa",
                title="Decision: adopt retry",
                summary="retry guidance adoption was approved",
                status_code="candidate",
                confidence=0.82,
                citation_bundle=(_citation(),),
                relations=(relation,),
            ),
        ),
    )

    async def fake_get_project_decisions(session, *, scope, project_uid):
        captured["project_uid"] = project_uid
        captured["scope"] = scope
        return view

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "get_project_decisions",
        fake_get_project_decisions,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.get(
                "/api/projects/project_candidate:test/decisions"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert captured["project_uid"] == "project_candidate:test"
    assert body["project_uid"] == "project_candidate:test"
    assert body["decision_count"] == 1
    assert body["grounded_decision_count"] == 1
    assert len(body["decisions"]) == 1
    decision = body["decisions"][0]
    assert decision["object_uid"] == "decision:aaa"
    assert decision["title"] == "Decision: adopt retry"
    # Grounded: the decision carries its own citation bundle, not a bare claim.
    assert decision["citation_bundle"][0]["content_segment_uid"] == "seg-dec"
    # Incident typed relations are inlined so a consumer can render *why* the
    # decision connects to the objects it resolves.
    assert len(decision["relations"]) == 1
    surfaced = decision["relations"][0]
    assert surfaced["relation_type"] == "resolves"
    assert surfaced["source"]["object_type"] == "decision"
    assert surfaced["target"]["object_uid"] == "issue:bbb"


@pytest.mark.asyncio
async def test_project_decisions_endpoint_returns_404_when_missing(
    dev_auth_dependency_overrides,
    monkeypatch,
):
    async def fake_get_project_decisions(session, *, scope, project_uid):
        raise ProjectGraphNotFoundError("Project candidate not found")

    async def override_get_db():
        yield object()

    monkeypatch.setattr(
        projects_api,
        "get_project_decisions",
        fake_get_project_decisions,
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with _client(
            user_id="reviewer",
            organization_id="org-acme",
        ) as client:
            response = await client.get(
                "/api/projects/project_candidate:missing/decisions"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project candidate not found"


@pytest.mark.asyncio
async def test_project_relation_summary_aggregates_typed_relation(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    user_id = f"project-api-relsum-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        seeded = await _seed_projection(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        before = await client.get(
            f"/api/projects/{seeded['candidate_uid']}/relations/summary"
        )
        assert before.status_code == 200
        before_body = before.json()
        # The deterministic seed extractor only emits segment-evidence edges, so
        # the relation summary starts empty (no object-to-object relations).
        assert before_body["project_uid"] == seeded["candidate_uid"]
        assert before_body["relation_count"] == 0
        assert before_body["grounded_relation_count"] == 0
        assert before_body["relation_types"] == []

    async with project_graph_api_sessionmaker() as session:
        objects = (
            (
                await session.execute(
                    select(ProjectGraphObjectRecord)
                    .where(ProjectGraphObjectRecord.user_id == user_id)
                    .where(ProjectGraphObjectRecord.object_type != "project_candidate")
                    .order_by(ProjectGraphObjectRecord.object_uid.asc())
                )
            )
            .scalars()
            .all()
        )
        assert len(objects) >= 2
        source_object, target_object = objects[0], objects[1]
        segment = await session.scalar(
            select(ContentSegmentRecord).where(
                ContentSegmentRecord.content_segment_uid == seeded["segment_uid"]
            )
        )
        assert segment is not None
        session.add(
            ProjectGraphEdgeRecord(
                edge_uid=f"project_edge:test-{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                organization_id=organization_id,
                workspace_id=f"workspace-{organization_id}",
                source_uid=source_object.object_uid,
                target_uid=target_object.object_uid,
                edge_type="implements",
                confidence=0.86,
                source_segment_uids=[seeded["segment_uid"]],
                source_object=source_object,
                target_object=target_object,
                primary_content_segment_id=segment.content_segment_id,
            )
        )
        await session.commit()

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        after = await client.get(
            f"/api/projects/{seeded['candidate_uid']}/relations/summary"
        )
        assert after.status_code == 200
        after_body = after.json()
        assert after_body["relation_count"] == 1
        # Grounded: the relation carries the endpoint citation, not a bare edge.
        assert after_body["grounded_relation_count"] == 1
        assert len(after_body["relation_types"]) == 1
        implements = after_body["relation_types"][0]
        assert implements["relation_type"] == "implements"
        assert implements["relation_count"] == 1
        assert implements["grounded_relation_count"] == 1
        assert implements["source_object_types"] == [source_object.object_type]
        assert implements["target_object_types"] == [target_object.object_type]


@pytest.mark.asyncio
async def test_project_decisions_surface_grounded_slice_and_incident_relation(
    dev_auth_dependency_overrides,
    project_graph_api_db_override,
    project_graph_api_sessionmaker,
):
    user_id = f"project-api-dec-{uuid.uuid4().hex}"
    organization_id = f"org-project-api-{uuid.uuid4().hex[:12]}"
    async with project_graph_api_sessionmaker() as session:
        seeded = await _seed_projection(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        before = await client.get(
            f"/api/projects/{seeded['candidate_uid']}/decisions"
        )
        assert before.status_code == 200
        before_body = before.json()
        # The deterministic seed text ("...확정...") yields exactly one grounded
        # decision object, and no object-to-object relation yet.
        assert before_body["project_uid"] == seeded["candidate_uid"]
        assert before_body["decision_count"] == 1
        assert before_body["grounded_decision_count"] == 1
        decision = before_body["decisions"][0]
        assert decision["object_uid"].startswith("decision:")
        # Grounded: the decision carries its citation, not a bare assertion.
        assert decision["citation_bundle"]
        assert decision["relations"] == []
        decision_uid = decision["object_uid"]

    # Attach a typed object-to-object relation from the decision to another
    # object so the incident-relation projection is exercised end to end.
    async with project_graph_api_sessionmaker() as session:
        decision_object = await session.scalar(
            select(ProjectGraphObjectRecord).where(
                ProjectGraphObjectRecord.user_id == user_id,
                ProjectGraphObjectRecord.object_uid == decision_uid,
            )
        )
        assert decision_object is not None
        target_object = await session.scalar(
            select(ProjectGraphObjectRecord)
            .where(ProjectGraphObjectRecord.user_id == user_id)
            .where(ProjectGraphObjectRecord.object_type == "issue")
            .order_by(ProjectGraphObjectRecord.object_uid.asc())
        )
        assert target_object is not None
        segment = await session.scalar(
            select(ContentSegmentRecord).where(
                ContentSegmentRecord.content_segment_uid == seeded["segment_uid"]
            )
        )
        assert segment is not None
        session.add(
            ProjectGraphEdgeRecord(
                edge_uid=f"project_edge:test-{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                organization_id=organization_id,
                workspace_id=f"workspace-{organization_id}",
                source_uid=decision_object.object_uid,
                target_uid=target_object.object_uid,
                edge_type="resolves",
                confidence=0.86,
                source_segment_uids=[seeded["segment_uid"]],
                source_object=decision_object,
                target_object=target_object,
                primary_content_segment_id=segment.content_segment_id,
            )
        )
        await session.commit()

    async with _client(user_id=user_id, organization_id=organization_id) as client:
        after = await client.get(
            f"/api/projects/{seeded['candidate_uid']}/decisions"
        )
        assert after.status_code == 200
        after_decision = after.json()["decisions"][0]
        assert len(after_decision["relations"]) == 1
        relation = after_decision["relations"][0]
        assert relation["relation_type"] == "resolves"
        assert relation["source"]["object_uid"] == decision_uid
        assert relation["source"]["object_type"] == "decision"
        assert relation["target"]["object_uid"] == target_object.object_uid
        # Grounded: the relation carries the endpoint citation.
        assert relation["citation_bundle"][0]["content_segment_uid"] == (
            seeded["segment_uid"]
        )


async def _seed_projection(
    session,
    *,
    user_id: str,
    organization_id: str,
) -> dict[str, str]:
    await _cleanup_user(session, user_id)
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
        workspace_id=f"workspace-{organization_id}",
    )
    await session.commit()
    candidate = next(
        record
        for record in result.objects
        if record.object_type == "project_candidate"
    )
    return {
        "candidate_uid": candidate.object_uid,
        "segment_uid": segment.content_segment_uid,
    }


async def _seed_source_segment(
    session,
    *,
    user_id: str,
    organization_id: str,
) -> ContentSegmentRecord:
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
        subject="Project Alpha checkout launch",
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
        safe_text_content="프로젝트 요구사항 문단",
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
        heading_path="Project kickoff",
        safe_text_content=(
            "프로젝트 Alpha launch 요구사항: 결제 화면은 카드 승인 실패 시 "
            "재시도 안내를 반드시 보여줘야 합니다. 2026-08-01 일정까지 "
            "SRS 산출물과 담당자 PM을 확정하고 blocker 리스크를 해결합니다."
        ),
        content_hash=uuid.uuid4().hex,
        word_count=25,
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


def _client(
    *,
    user_id: str,
    organization_id: str,
    role: str = "member",
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={
            "X-User-Id": user_id,
            "X-Organization-Id": organization_id,
            "X-User-Role": role,
        },
    )
