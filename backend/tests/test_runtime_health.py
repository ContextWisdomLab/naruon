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


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_dependency", [None, "primary", "readonly"])
async def test_readiness_checks_both_databases_without_leaking_errors(monkeypatch, failed_dependency):
    """A failed database must remove readiness, and every acquired connection closes."""
    connection_events = []

    class ProbeConnection:
        """Unit-only SQL connection with a failure at the external boundary."""

        def __init__(self, dependency_name):
            self.dependency_name = dependency_name

        async def execute(self, query_statement):
            assert str(query_statement) == "SELECT 1"
            if self.dependency_name == failed_dependency:
                raise OperationalError("SELECT 1", None, Exception("unit-private-detail"))

    class ProbeEngine:
        """Record acquisition and cleanup while the actual endpoint executes."""

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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.local") as client:
        health_response = await client.get("/healthz")
        assert health_response.status_code == 200
        assert connection_events == []
        readiness_response = await client.get("/readyz")

    assert readiness_response.status_code == (503 if failed_dependency else 200)
    assert readiness_response.json() == {"status": "unavailable" if failed_dependency else "ready"}
    assert readiness_response.headers["cache-control"] == "no-store"
    assert "unit-private-detail" not in readiness_response.text
    expected_events = [("primary", "open"), ("primary", "close")]
    if failed_dependency != "primary":
        expected_events += [("readonly", "open"), ("readonly", "close")]
    assert connection_events == expected_events
