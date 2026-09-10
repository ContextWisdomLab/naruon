"""Executable contract for canonical WebDAV collection URLs."""

import defusedxml.ElementTree as ET
import pytest
from fastapi.testclient import TestClient

from main import app
from services.webdav_service import webdav_service

AUTH_HEADERS = {
    "X-User-Id": "user123",
    "X-User-Role": "organization_admin",
    "X-Organization-Id": "org-acme",
    "Depth": "1",
}


def test_propfind_emits_trailing_slashes_for_collection_hrefs(
    dev_auth_dependency_overrides,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every generated URL that identifies a collection should use canonical slash form."""

    async def project_folders(
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
                "project_name": "Demo",
                "webdav_path": "/projects/demo",
                "owner_user_id": user_id,
                "organization_id": organization_id,
            }
        ]

    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        project_folders,
    )

    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 207
    root = ET.fromstring(response.text)
    hrefs = [item.findtext("{DAV:}href") for item in root.findall("{DAV:}response")]
    assert hrefs == [
        "/api/dav/user123/projects/",
        "/api/dav/user123/projects/demo/",
    ]
