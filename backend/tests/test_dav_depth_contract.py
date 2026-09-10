"""Executable contract for bounded WebDAV PROPFIND Depth handling."""

import defusedxml.ElementTree as ET
import pytest
from fastapi.testclient import TestClient

from main import app
from services.webdav_service import webdav_service

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
    ) -> list[dict[str, str | None]]:
        assert user_id == "user123"
        assert organization_id == "org-acme"
        assert folder_uid is None
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


def _assert_finite_depth_error(response) -> None:
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.text)
    assert root.tag == "{DAV:}error"
    assert root.find("{DAV:}propfind-finite-depth") is not None


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
