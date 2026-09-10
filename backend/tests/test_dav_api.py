import defusedxml.ElementTree as ET

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.dav import _normalize_dav_authorization_path

from main import app
from services.webdav_service import webdav_service

AUTH_HEADERS = {
    "X-User-Id": "user123",
    "X-User-Role": "organization_admin",
    "X-Organization-Id": "org-acme",
}


@pytest.fixture
def stub_dav_project_folders(monkeypatch):
    async def fake_project_folders(db, user_id, organization_id, folder_uid=None):
        assert user_id == "user123"
        assert organization_id == "org-acme"
        if folder_uid is None:
            return [
                {
                    "folder_uid": "demo",
                    "project_name": "demo",
                    "webdav_path": "/projects/demo",
                    "owner_user_id": user_id,
                    "organization_id": organization_id,
                }
            ]
        return [
            {
                "folder_uid": folder_uid,
                "project_name": folder_uid,
                "webdav_path": f"/projects/{folder_uid}",
                "owner_user_id": user_id,
                "organization_id": organization_id,
            }
        ]

    monkeypatch.setattr(
        webdav_service,
        "get_project_folders_from_db",
        fake_project_folders,
    )


def test_dav_rejects_missing_auth():
    with TestClient(app) as client:
        response = client.request("PROPFIND", "/dav/user123/projects/")
        assert response.status_code == 401


def test_dav_route_uses_signed_session_dependency():
    with TestClient(app) as client:
        response = client.options(
            "/dav/user123/projects/",
            headers={"Authorization": "Bearer not-a-signed-session"},
        )

    assert response.status_code == 401


def test_dav_options(dev_auth_dependency_overrides):
    with TestClient(app) as client:
        response = client.options("/dav/user123/projects/", headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert "calendar-access" in response.headers.get("DAV", "")


def test_dav_rejects_different_user_path(dev_auth_dependency_overrides):
    with TestClient(app) as client:
        response = client.request(
            "PROPFIND", "/dav/other-user/projects/", headers=AUTH_HEADERS
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "DAV path belongs to a different user"


def test_dav_rejects_ownerless_path(dev_auth_dependency_overrides):
    with TestClient(app) as client:
        response = client.request("PROPFIND", "/dav/", headers=AUTH_HEADERS)
        assert response.status_code == 403
        assert response.json()["detail"] == "DAV path must include an owner user"


def test_dav_rejects_ownerless_options_before_capability_discovery(
    dev_auth_dependency_overrides,
):
    with TestClient(app) as client:
        response = client.options("/dav/", headers=AUTH_HEADERS)
        assert response.status_code == 403
        assert "dav" not in {header.lower() for header in response.headers}
        assert response.json()["detail"] == "DAV path must include an owner user"


def test_dav_propfind(dev_auth_dependency_overrides, stub_dav_project_folders):
    with TestClient(app) as client:
        response = client.request(
            "PROPFIND", "/dav/user123/projects/", headers=AUTH_HEADERS
        )
        assert response.status_code == 207
        assert "<D:multistatus" in response.text
        root = ET.fromstring(response.text)
        assert root.find(".//{DAV:}collection") is not None


def test_dav_propfind_escapes_path_values(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
):
    with TestClient(app) as client:
        response = client.request(
            "PROPFIND", "/dav/user123/projects/x%26y%3Cz%3E", headers=AUTH_HEADERS
        )
        assert response.status_code == 207
        assert "x&amp;y&lt;z&gt;" in response.text
        assert "x&y<z>" not in response.text
        ET.fromstring(response.text)


def test_dav_put(dev_auth_dependency_overrides, caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="api.dav")
    with TestClient(app) as client:
        response = client.put(
            "/dav/user123/projects/file.ics",
            content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 501
        assert "Provider-backed DAV writeback is not implemented" in response.text
        assert "etag" not in {header.lower() for header in response.headers}
        assert any(
            "provider-backed DAV writeback is not implemented" in record.getMessage()
            for record in caplog.records
        )


def test_dav_unsupported_method_logs_reason(dev_auth_dependency_overrides, caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="api.dav")
    with TestClient(app) as client:
        response = client.delete(
            "/dav/user123/projects/file.ics",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 501
    assert "Provider-backed DAV method is not implemented" in response.text
    assert any(
        "method is not implemented for the provider-backed DAV gateway"
        in record.getMessage()
        for record in caplog.records
    )


def test_dav_log_injection_prevention(dev_auth_dependency_overrides, caplog):
    """Keep control characters escaped if a direct handler test reaches logging."""
    import asyncio
    import logging

    from fastapi import Request

    caplog.set_level(logging.INFO)
    malicious_path = "user123/projects/test\x1b[31minjected\n\r"
    scope = {
        "type": "http",
        "method": "OPTIONS",
        "headers": [],
    }

    async def run_handler():
        req = Request(scope)
        from api.auth import AuthContext

        auth_ctx = AuthContext(
            user_id="user123",
            organization_id="org1",
            role="user",
            group_ids=[],
            workspace_id="ws1",
        )

        from api.dav import dav_handler

        await dav_handler(request=req, path=malicious_path, auth_context=auth_ctx)

    asyncio.run(run_handler())

    raw_ansi = "\x1b[31m"
    found_in_logs = False
    for record in caplog.records:
        if "DAV Request" in record.message:
            assert raw_ansi not in record.message, "Raw ANSI escape sequence found in logs!"
            assert "\n" not in record.message[12:], "Raw newline found in log message body!"
            assert (
                "\\x1b[31minjected\\n\\r" in record.message
                or "\\x1b[31minjected\\r\\n" in record.message
            ), "Escaped characters missing from log message!"
            found_in_logs = True

    assert found_in_logs, "DAV Request log was not found"


@pytest.mark.parametrize(
    "request_path",
    [
        "/dav/user123/projects/%252e%252e",
        "/dav/user123/projects/%25252e%25252e",
        "/dav/user123/projects/alice%255c..%255cbob",
        "/dav/user123/projects/%2525",
        "/dav/user123/projects/%25%32%65",
        "/dav/user123/projects/alice%25%35%63..%25%35%63bob",
    ],
)
def test_dav_route_rejects_ambiguous_nested_encoding(
    dev_auth_dependency_overrides,
    request_path: str,
) -> None:
    with TestClient(app) as client:
        response = client.request("PROPFIND", request_path, headers=AUTH_HEADERS)

    assert response.status_code == 400
    assert response.json()["detail"] == "DAV path contains nested percent encoding"


@pytest.mark.parametrize(
    "request_path",
    [
        "/dav/user123/projects/report%25",
        "/dav/user123/projects/%25report",
    ],
)
def test_dav_route_preserves_encoded_percent_as_data(
    dev_auth_dependency_overrides,
    stub_dav_project_folders,
    request_path: str,
) -> None:
    with TestClient(app) as client:
        response = client.request("PROPFIND", request_path, headers=AUTH_HEADERS)

    assert response.status_code == 207
    assert "%" in response.text


@pytest.mark.parametrize(
    "request_path",
    [
        "/dav/user123/projects/%GG",
        "/dav/user123/projects/%2",
    ],
)
def test_dav_route_rejects_malformed_raw_percent_escape(
    dev_auth_dependency_overrides,
    request_path: str,
) -> None:
    with TestClient(app) as client:
        response = client.request("PROPFIND", request_path, headers=AUTH_HEADERS)

    assert response.status_code == 400
    assert response.json()["detail"] == "DAV path contains invalid percent encoding"


@pytest.mark.parametrize(
    "request_path",
    [
        "/dav/user123/projects/%00",
        "/dav/user123/projects/%0A",
        "/dav/user123/projects/%7F",
    ],
)
def test_dav_route_rejects_percent_encoded_control_character(
    dev_auth_dependency_overrides,
    request_path: str,
) -> None:
    with TestClient(app) as client:
        response = client.request("PROPFIND", request_path, headers=AUTH_HEADERS)

    assert response.status_code == 400
    assert response.json()["detail"] == "DAV path contains control characters"


def test_dav_route_rejects_invalid_utf8_replacement(
    dev_auth_dependency_overrides,
) -> None:
    with TestClient(app) as client:
        response = client.request(
            "PROPFIND",
            "/dav/user123/projects/%FF",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "DAV path contains invalid Unicode"


@pytest.mark.parametrize(
    "request_path",
    [
        "/dav/user123/projects/%2e%2e",
        "/dav/user123/projects/%5c..%5c",
    ],
)
def test_dav_route_rejects_single_decode_traversal(
    dev_auth_dependency_overrides,
    request_path: str,
) -> None:
    with TestClient(app) as client:
        response = client.request("PROPFIND", request_path, headers=AUTH_HEADERS)

    assert response.status_code == 403
    assert response.json()["detail"] == "DAV path must include an owner user"


def test_dav_missing_raw_path_fails_closed_for_residual_percent(
    dev_auth_dependency_overrides,
) -> None:
    import asyncio

    from fastapi import Request

    from api.auth import AuthContext
    from api.dav import dav_handler

    scope = {
        "type": "http",
        "method": "OPTIONS",
        "headers": [],
        "path": "/dav/user123/projects/report%",
    }
    request = Request(scope)
    auth_context = AuthContext(
        user_id="user123",
        organization_id="org1",
        role="user",
        group_ids=[],
        workspace_id="ws1",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            dav_handler(
                request=request,
                path="user123/projects/report%",
                auth_context=auth_context,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "DAV raw path required for percent-bearing path"


def test_normalize_dav_authorization_path_treats_route_path_as_already_decoded() -> None:
    assert _normalize_dav_authorization_path("/alice/docs") == "/alice/docs"
    assert _normalize_dav_authorization_path("/%2e%2e/bob") == "/%2e%2e/bob"
    assert _normalize_dav_authorization_path("/alice%/docs") == "/alice%/docs"


def test_normalize_dav_authorization_path_has_no_recursive_input_amplification() -> None:
    path = "/alice/" + ("segment-" * 8192)
    assert _normalize_dav_authorization_path(path) == path
