from fastapi.testclient import TestClient
import pytest

import main
from core.config import settings
from main import app

client = TestClient(app)


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "AI Email Client API"}


def test_root_response_has_security_headers():
    response = client.get("/")

    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    assert "x-xss-protection" not in response.headers


def test_cors_policy_is_restrictive():
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    allowed_methods = response.headers["access-control-allow-methods"]
    assert "GET" in allowed_methods
    assert "POST" in allowed_methods
    assert "PROPFIND" in allowed_methods
    assert "DELETE" in allowed_methods
    assert "OPTIONS" in allowed_methods
    assert "*" not in allowed_methods

    allowed_headers = response.headers["access-control-allow-headers"]
    assert "Accept" in allowed_headers
    assert "Content-Type" in allowed_headers
    assert "Authorization" in allowed_headers
    assert "*" not in allowed_headers


def test_state_changing_api_rejects_cross_site_fetch_metadata():
    response = client.put(
        "/api/accounts/config",
        headers={"Sec-Fetch-Site": "cross-site"},
        json={"smtp_server": "mail.example.com"},
    )

    assert response.status_code == 403
    assert response.json() == {"error_code": "csrf_fetch_site_rejected"}


def test_state_changing_api_rejects_untrusted_origin():
    response = client.put(
        "/api/accounts/config",
        headers={"Origin": "https://evil.example"},
        json={"smtp_server": "mail.example.com"},
    )

    assert response.status_code == 403
    assert response.json() == {"error_code": "csrf_origin_rejected"}


def test_browser_state_change_rejects_missing_origin_and_referer():
    response = client.put(
        "/api/accounts/config",
        headers={"Sec-Fetch-Site": "same-origin"},
        json={"smtp_server": "mail.example.com"},
    )

    assert response.status_code == 403
    assert response.json() == {"error_code": "csrf_referer_rejected"}


def test_non_browser_state_change_without_provenance_reaches_auth_gate():
    response = client.put(
        "/api/accounts/config",
        json={"smtp_server": "mail.example.com"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_state_changing_api_allows_trusted_origin_to_reach_auth_gate():
    response = client.put(
        "/api/accounts/config",
        headers={"Origin": "http://localhost:3000"},
        json={"smtp_server": "mail.example.com"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_state_changing_api_canonicalizes_default_origin_ports(monkeypatch):
    monkeypatch.setattr(
        settings,
        "ALLOWED_CORS_ORIGINS",
        "https://app.example.com:443,http://app.example.com:80",
    )

    https_response = client.put(
        "/api/accounts/config",
        headers={"Origin": "https://app.example.com"},
        json={"smtp_server": "mail.example.com"},
    )
    http_referer_response = client.put(
        "/api/accounts/config",
        headers={"Referer": "http://app.example.com/settings/accounts"},
        json={"smtp_server": "mail.example.com"},
    )

    assert https_response.status_code == 401
    assert https_response.json() == {"detail": "Authentication required"}
    assert http_referer_response.status_code == 401
    assert http_referer_response.json() == {"detail": "Authentication required"}


@pytest.mark.asyncio
async def test_lifespan_starts_mail_reply_sla_and_writeback_retry_workers(monkeypatch):
    events: list[str] = []

    class FakeWorker:
        def __init__(self, name: str):
            self.name = name

        async def start(self):
            events.append(f"start:{self.name}")

        async def stop(self):
            events.append(f"stop:{self.name}")

    monkeypatch.setattr(main, "DISABLE_WORKERS", False)
    monkeypatch.setattr(main, "preload_oidc_jwks", lambda: None)
    monkeypatch.setattr(main, "imap_worker", FakeWorker("imap"))
    monkeypatch.setattr(main, "pop3_worker", FakeWorker("pop3"), raising=False)
    monkeypatch.setattr(
        main,
        "reply_sla_scheduler",
        FakeWorker("reply_sla"),
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "provider_writeback_retry_worker",
        FakeWorker("provider_writeback_retry"),
        raising=False,
    )

    async with main.lifespan(app):
        assert events == [
            "start:imap",
            "start:pop3",
            "start:reply_sla",
            "start:provider_writeback_retry",
        ]

    assert events == [
        "start:imap",
        "start:pop3",
        "start:reply_sla",
        "start:provider_writeback_retry",
        "stop:provider_writeback_retry",
        "stop:reply_sla",
        "stop:pop3",
        "stop:imap",
    ]
