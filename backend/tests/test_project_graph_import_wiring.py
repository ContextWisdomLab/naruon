"""Tests for wiring project-graph extraction into the email import pipeline.

The projection is flag-gated and best-effort: it must never affect the (already
committed) email import. These tests exercise the real deterministic extractor
and mock only the DB persistence layer.
"""

import types

import pytest
from unittest.mock import AsyncMock

import services.email_import_service as import_service


def _segment(uid: str, text: str, ordinal: int = 0):
    return types.SimpleNamespace(
        content_segment_uid=uid,
        source_kind="email_body",
        source_record_uid="email:1",
        safe_text_content=text,
        heading_path=None,
        segment_path=f"body/{ordinal}",
        ordinal_index=ordinal,
    )


def test_project_source_segments_maps_content_segments():
    email_obj = types.SimpleNamespace(
        content_segments=[_segment("seg1", "hello", 0), _segment("seg2", "world", 1)]
    )

    result = import_service._project_source_segments(email_obj)

    assert [segment.content_segment_uid for segment in result] == ["seg1", "seg2"]
    assert result[0].safe_text_content == "hello"
    assert result[0].source_kind == "email_body"
    assert result[1].ordinal_index == 1


@pytest.mark.asyncio
async def test_projection_persists_with_the_callers_resolved_workspace(monkeypatch):
    # workspace_id is the caller's already-resolved workspace (the same value
    # the imported Email row itself was stored under) -- the function must
    # pass it through verbatim rather than recomputing its own default from
    # organization_id/user_id, or a non-default import workspace would put
    # the email and its derived project-graph objects in different
    # workspaces.
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        import_service, "persist_project_graph_projection", persist_mock
    )
    session = AsyncMock()
    segments = [
        _segment("seg1", "The system must support export. This is a requirement.", 0)
    ]

    await import_service._persist_project_graph_projection(
        session,
        segments,
        user_id="user1",
        organization_id="org1",
        workspace_id="workspace-org1",
    )

    persist_mock.assert_awaited_once()
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["user_id"] == "user1"
    assert kwargs["organization_id"] == "org1"
    assert kwargs["workspace_id"] == "workspace-org1"
    assert kwargs["extraction"].objects  # real extractor produced candidates
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_projection_passes_through_a_non_default_workspace(monkeypatch):
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        import_service, "persist_project_graph_projection", persist_mock
    )
    session = AsyncMock()
    segments = [_segment("seg1", "We must deliver the milestone by 2026-01-01.", 0)]

    await import_service._persist_project_graph_projection(
        session,
        segments,
        user_id="user1",
        organization_id="",
        workspace_id="workspace-custom-tenant",
    )

    kwargs = persist_mock.await_args.kwargs
    assert kwargs["workspace_id"] == "workspace-custom-tenant"


@pytest.mark.asyncio
async def test_projection_noop_when_no_segments(monkeypatch):
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        import_service, "persist_project_graph_projection", persist_mock
    )
    session = AsyncMock()

    await import_service._persist_project_graph_projection(
        session, [], user_id="u", organization_id="o", workspace_id="workspace-o"
    )

    persist_mock.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_projection_noop_when_no_objects_extracted(monkeypatch):
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        import_service, "persist_project_graph_projection", persist_mock
    )
    session = AsyncMock()
    # Neutral text with no rule keywords -> extractor yields nothing.
    segments = [_segment("seg1", "hello there, nice weather today", 0)]

    await import_service._persist_project_graph_projection(
        session, segments, user_id="u", organization_id="o", workspace_id="workspace-o"
    )

    persist_mock.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_projection_swallows_failure_and_rolls_back(monkeypatch):
    persist_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(
        import_service, "persist_project_graph_projection", persist_mock
    )
    session = AsyncMock()
    segments = [_segment("seg1", "The system must support export requirement.", 0)]

    # Best-effort: a projection failure must not propagate to the import.
    await import_service._persist_project_graph_projection(
        session, segments, user_id="u", organization_id="o", workspace_id="workspace-o"
    )

    session.rollback.assert_awaited_once()
