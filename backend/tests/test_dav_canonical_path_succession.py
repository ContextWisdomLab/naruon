"""Regression coverage for DAV canonical-path succession and request bounds."""

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from api.dav import _validate_dav_raw_request_path
from main import app
from services.webdav_service import webdav_service

AUTH_HEADERS = {
    "X-User-Id": "user123",
    "X-User-Role": "organization_admin",
    "X-Organization-Id": "org-acme",
}


@pytest.fixture
def stub_dav_project_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return one project folder through the production DAV service seam."""

    async def fake_project_folders(
        db: object,
        user_id: str,
        organization_id: str | None,
        folder_uid: str | None = None,
    ) -> list[dict[str, str | None]]:
        assert user_id == "user123"
        assert organization_id == "org-acme"
        assert folder_uid == "demo"
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


def test_propfind_propagates_framework_decoded_backslashes_to_project_routing(
    dev_auth_dependency_overrides,
    stub_dav_project_folder,
) -> None:
    """One decoded path representation must drive authorization and routing."""

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123%5Cprojects%5Cdemo",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 207
    assert "<D:displayname>demo</D:displayname>" in response.text


def test_dav_raw_path_enforces_explicit_8192_octet_resource_boundary() -> None:
    """The wire-path validator must bound work while supporting RFC 9110's minimum."""

    accepted_raw_path = b"/dav/" + (b"x" * (8192 - len(b"/dav/")))
    accepted_request = Request(
        {
            "type": "http",
            "method": "OPTIONS",
            "headers": [],
            "path": "/dav/" + ("x" * (8192 - len("/dav/"))),
            "raw_path": accepted_raw_path,
        }
    )
    _validate_dav_raw_request_path(
        accepted_request,
        "x" * (8192 - len(b"/dav/")),
    )

    rejected_request = Request(
        {
            "type": "http",
            "method": "OPTIONS",
            "headers": [],
            "path": "/dav/" + ("x" * (8193 - len("/dav/"))),
            "raw_path": accepted_raw_path + b"x",
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        _validate_dav_raw_request_path(
            rejected_request,
            "x" * (8193 - len(b"/dav/")),
        )

    assert exc_info.value.status_code == 414
    assert exc_info.value.detail == "DAV raw path exceeds 8192 octets"


def test_dav_missing_raw_path_bounds_decoded_fallback() -> None:
    """An ASGI server without raw_path still receives a bounded fail-closed path."""

    request = Request(
        {
            "type": "http",
            "method": "OPTIONS",
            "headers": [],
            "path": "/dav/" + ("x" * 8193),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        _validate_dav_raw_request_path(request, "x" * 8193)

    assert exc_info.value.status_code == 414
    assert exc_info.value.detail == "DAV decoded path exceeds 8192 characters"
