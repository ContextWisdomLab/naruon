"""Exercise public probe responses without workers or customer/provider access."""

from contextlib import asynccontextmanager
import os
import secrets

import httpx
import pytest
from sqlalchemy.exc import OperationalError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unit:unit@127.0.0.1:1/unit_db")
os.environ.setdefault("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")

from db import session as database_session  # noqa: E402
from main import app  # noqa: E402


def install_probe_engines(monkeypatch, *, failed_dependency=None, failure_factory=None):
    """Install deterministic primary/read-only probes and return lifecycle evidence."""
    connection_events = []

    class ProbeConnection:
        async def execute(self, query_statement):
            assert str(query_statement) == "SELECT 1"
            if self.dependency_name == failed_dependency and failure_factory is not None:
                raise failure_factory()

        def __init__(self, dependency_name):
            self.dependency_name = dependency_name

    class ProbeEngine:
        def __init__(self, dependency_name):
            self.dependency_name = dependency_name

        @asynccontextmanager
        async def connect(self):
            connection_events.append((self.dependency_name, "open"))
            try:
                yield ProbeConnection(self.dependency_name)
            finally:
                connection_events.append((self.dependency_name, "close"))

    monkeypatch.setattr(database_session, "engine", ProbeEngine("primary"))
    monkeypatch.setattr(database_session, "readonly_engine", ProbeEngine("readonly"))
    return connection_events


@pytest.mark.asyncio
async def test_liveness_does_not_touch_databases_and_disables_cache(monkeypatch):
    """Liveness is process-only and returns a stable non-cacheable contract."""
    connection_events = install_probe_engines(monkeypatch)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.local") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert connection_events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_dependency", [None, "primary", "readonly"])
async def test_readiness_checks_both_databases_without_leaking_errors(monkeypatch, failed_dependency):
    """A failed database must remove readiness, and every acquired connection closes."""

    def operational_failure():
        return OperationalError("SELECT 1", None, Exception("unit-private-detail"))

    connection_events = install_probe_engines(
        monkeypatch,
        failed_dependency=failed_dependency,
        failure_factory=operational_failure if failed_dependency is not None else None,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.local") as client:
        response = await client.get("/readyz")

    assert response.status_code == (503 if failed_dependency else 200)
    assert response.json() == {"status": "unavailable" if failed_dependency else "ready"}
    assert response.headers["cache-control"] == "no-store"
    assert "unit-private-detail" not in response.text
    expected_events = [("primary", "open"), ("primary", "close")]
    if failed_dependency != "primary":
        expected_events += [("readonly", "open"), ("readonly", "close")]
    assert connection_events == expected_events


def os_failure():
    """Return an OS-level connection failure containing private test detail."""
    return OSError("os-private-detail")


def timeout_failure():
    """Return a timeout failure containing private test detail."""
    return TimeoutError("timeout-private-detail")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_factory", "private_detail"),
    [
        (os_failure, "os-private-detail"),
        (timeout_failure, "timeout-private-detail"),
    ],
    ids=["os-error", "timeout"],
)
async def test_readiness_sanitizes_supported_connection_failures(
    monkeypatch, failure_factory, private_detail
):
    """Supported transport failures fail closed without leaking their detail."""
    connection_events = install_probe_engines(
        monkeypatch,
        failed_dependency="primary",
        failure_factory=failure_factory,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.local") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert private_detail not in response.text
    assert connection_events == [("primary", "open"), ("primary", "close")]
