"""Executable contract for bounded WebDAV PROPFIND Depth handling."""

import defusedxml.ElementTree as ET
import pytest
from fastapi.testclient import TestClient

from main import app
from services.webdav_service import WebDavService, webdav_service

AUTH_HEADERS = {
    "X-User-Id": "user123",
    "X-User-Role": "organization_admin",
    "X-Organization-Id": "org-acme",
}


@pytest.fixture
def stub_dav_project_folders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide one collection so Depth handling reaches the PROPFIND boundary."""

    async def fake_project_folders(
        db: object,
        user_id: str,
        organization_id: str | None,
        folder_uid: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, str | None]]:
        assert user_id == "user123"
        assert organization_id == "org-acme"
        assert folder_uid is None
        assert max_results == 257
        return [
            {
                "folder_uid": "demo",
                "project_name": "demo",
                "webdav_path": "/projects/demo",
                "owner_user_id": user_id,
                "organization_id": organization_id,
            }
        ]

    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        fake_project_folders,
    )


def test_propfind_depth_zero_returns_only_addressed_collection(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
) -> None:
    """Depth zero must not enumerate the addressed collection's members."""

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers={**AUTH_HEADERS, "Depth": "0"},
        )

    assert response.status_code == 207
    root = ET.fromstring(response.text)
    responses = root.findall("{DAV:}response")
    assert len(responses) == 1
    assert root.findtext(".//{DAV:}displayname") == "projects"
    assert "demo" not in response.text


def test_propfind_depth_one_returns_addressed_collection_and_direct_member(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
) -> None:
    """Depth one must include both the addressed collection and direct members."""

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers={**AUTH_HEADERS, "Depth": "1"},
        )

    assert response.status_code == 207
    root = ET.fromstring(response.text)
    responses = root.findall("{DAV:}response")
    assert len(responses) == 2
    assert [
        item.findtext(".//{DAV:}displayname") for item in responses
    ] == ["projects", "demo"]


def test_propfind_project_collection_depth_one_rejects_unimplemented_member_enumeration(
    dev_auth_dependency_overrides,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A project collection must not masquerade as empty when members are unknown."""

    async def selected_project_folder(
        db: object,
        user_id: str,
        organization_id: str | None,
        folder_uid: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, str | None]]:
        assert user_id == "user123"
        assert organization_id == "org-acme"
        assert folder_uid == "demo"
        assert max_results is None
        return [
            {
                "folder_uid": "demo",
                "project_name": "demo",
                "webdav_path": "/projects/demo",
                "owner_user_id": user_id,
                "organization_id": organization_id,
            }
        ]

    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        selected_project_folder,
    )

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/demo/",
            headers={**AUTH_HEADERS, "Depth": "1"},
        )

    assert response.status_code == 501
    assert response.json()["detail"] == (
        "DAV project collection member enumeration is not implemented"
    )


def test_propfind_depth_one_accepts_exact_product_ceiling(
    dev_auth_dependency_overrides,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly 256 members remains a complete successful depth-one response."""

    async def maximum_project_folders(
        db: object,
        user_id: str,
        organization_id: str | None,
        folder_uid: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, str | None]]:
        assert user_id == "user123"
        assert organization_id == "org-acme"
        assert folder_uid is None
        assert max_results == 257
        return [
            {
                "folder_uid": f"folder-{index}",
                "project_name": f"Folder {index}",
                "webdav_path": f"/projects/folder-{index}",
                "owner_user_id": user_id,
                "organization_id": organization_id,
            }
            for index in range(256)
        ]

    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        maximum_project_folders,
    )

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers={**AUTH_HEADERS, "Depth": "1"},
        )

    assert response.status_code == 207
    root = ET.fromstring(response.text)
    responses = root.findall("{DAV:}response")
    assert len(responses) == 257
    assert responses[0].findtext(".//{DAV:}displayname") == "projects"
    assert responses[-1].findtext(".//{DAV:}displayname") == "Folder 255"


def test_propfind_depth_one_rejects_member_set_above_product_ceiling(
    dev_auth_dependency_overrides,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Depth one must refuse an oversized collection instead of materializing it."""

    async def too_many_project_folders(
        db: object,
        user_id: str,
        organization_id: str | None,
        folder_uid: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, str | None]]:
        assert user_id == "user123"
        assert organization_id == "org-acme"
        assert folder_uid is None
        assert max_results == 257
        return [
            {
                "folder_uid": f"folder-{index}",
                "project_name": f"Folder {index}",
                "webdav_path": f"/projects/folder-{index}",
                "owner_user_id": user_id,
                "organization_id": organization_id,
            }
            for index in range(257)
        ]

    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        too_many_project_folders,
    )

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers={**AUTH_HEADERS, "Depth": "1"},
        )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.text)
    assert root.tag == "{DAV:}error"
    assert root.find("{urn:naruon:dav}project-member-limit") is not None


@pytest.mark.asyncio
async def test_project_folder_reader_applies_requested_sql_limit() -> None:
    """The database read itself must stop at the caller's bounded probe size."""

    statements: list[object] = []

    class EmptyScalars:
        def all(self) -> list[object]:
            return []

    class EmptyResult:
        def scalars(self) -> EmptyScalars:
            return EmptyScalars()

    class RecordingSession:
        async def execute(self, statement: object) -> EmptyResult:
            statements.append(statement)
            return EmptyResult()

    service = WebDavService()
    await service.get_project_folders_from_db(
        RecordingSession(),
        "user123",
        "org-acme",
        max_results=257,
    )
    await service.get_project_folders_from_db(
        RecordingSession(),
        "user123",
        "org-acme",
    )

    limited_sql = str(statements[0].compile(compile_kwargs={"literal_binds": True}))
    unbounded_sql = str(statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 257" in limited_sql
    assert "LIMIT" not in unbounded_sql


def test_propfind_without_depth_fails_closed_as_infinite_depth(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
) -> None:
    """Missing Depth follows RFC 4918's infinity default, which Naruon declines."""

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers=AUTH_HEADERS,
        )

    _assert_finite_depth_error(response)


def test_propfind_infinite_depth_returns_webdav_precondition(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
) -> None:
    """Unbounded traversal is rejected with the RFC 4918 finite-depth precondition."""

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers={**AUTH_HEADERS, "Depth": "infinity"},
        )

    _assert_finite_depth_error(response)


@pytest.mark.parametrize("depth", ["", "2", "children", "0, 1"])
def test_propfind_rejects_invalid_depth_values(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
    depth: str,
) -> None:
    """A Depth value outside RFC 4918's grammar must not be coerced to depth one."""

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers={**AUTH_HEADERS, "Depth": depth},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "DAV Depth must be 0, 1, or infinity"
