from fastapi.testclient import TestClient

from main import app

AUTH_HEADERS = {
    "X-User-Id": "user123",
    "X-User-Role": "organization_admin",
    "X-Organization-Id": "org-acme",
}


def test_dav_options_advertises_only_operational_methods(
    dev_auth_dependency_overrides,
) -> None:
    with TestClient(app) as client:
        response = client.options("/dav/user123/projects/", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert "DAV" not in response.headers
    assert {method.strip() for method in response.headers["Allow"].split(",")} == {
        "OPTIONS",
        "PROPFIND",
    }
