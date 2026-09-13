import asyncio
import pytest
from unittest.mock import MagicMock, patch

from db.models import TenantConfig
from services.pop3_worker import Pop3SyncWorker


def test_pop3_sync_requires_credentials(caplog, monkeypatch):
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        pop3_server="pop3.example.com",
        pop3_port=995,
    )
    pop3_client = MagicMock()

    monkeypatch.setattr(
        "services.pop3_worker.validate_pop3_destination",
        lambda host, port: (host, port),
    )
    with patch("services.pop3_worker.poplib.POP3_SSL", return_value=pop3_client):
        with pytest.raises(RuntimeError, match="POP3 account configuration incomplete"):
            worker._do_pop3_sync(config)

    pop3_client.user.assert_not_called()
    pop3_client.pass_.assert_not_called()
    pop3_client.quit.assert_called_once()
    assert "pop3_password" not in caplog.text
    assert "pop3-secret" not in caplog.text
    assert "credential secret" not in caplog.text.lower()


def test_pop3_sync_missing_secret_avoids_sensitive_log_names(caplog, monkeypatch):
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        pop3_server="pop3.example.com",
        pop3_port=995,
        pop3_username="pop3-user",
    )
    pop3_client = MagicMock()

    monkeypatch.setattr(
        "services.pop3_worker.validate_pop3_destination",
        lambda host, port: (host, port),
    )
    with patch("services.pop3_worker.poplib.POP3_SSL", return_value=pop3_client):
        with pytest.raises(RuntimeError, match="POP3 account configuration incomplete"):
            worker._do_pop3_sync(config)

    pop3_client.user.assert_not_called()
    pop3_client.pass_.assert_not_called()
    pop3_client.quit.assert_called_once()
    assert "pop3_password" not in caplog.text
    assert "password" not in caplog.text.lower()
    assert "credential secret" not in caplog.text.lower()


def test_pop3_do_sync_validates_destination_before_connect():
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        pop3_server="127.0.0.1",
        pop3_port=995,
    )

    with patch("services.pop3_worker.poplib.POP3_SSL") as pop3_ssl:
        with pytest.raises(ValueError):
            worker._do_pop3_sync(config)

    pop3_ssl.assert_not_called()


@pytest.mark.asyncio
async def test_pop3_worker_skips_disallowed_destination():
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        pop3_server="127.0.0.1",
        pop3_port=995,
    )

    with patch("services.pop3_worker.poplib.POP3_SSL") as pop3_ssl:
        await worker._sync_tenant(config, "workspace-pop3", asyncio.Semaphore(1))

    pop3_ssl.assert_not_called()


@pytest.mark.asyncio
async def test_pop3_worker_imports_retrieved_messages(monkeypatch):
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        organization_id="org-pop3",
        pop3_server="pop3.example.com",
        pop3_port=995,
        pop3_username="pop3-user@example.com",
        pop3_password="pop3-secret",
    )
    raw_message = (
        b"Message-ID: <pop3-1@example.com>\r\n"
        b"From: Sender <sender@example.com>\r\n"
        b"To: pop3-user@example.com\r\n"
        b"Subject: POP3 import\r\n"
        b"Date: Mon, 15 Jun 2026 10:00:00 +0000\r\n"
        b"\r\n"
        b"Imported from POP3.\r\n"
    )
    pop3_client = MagicMock()
    pop3_client.list.return_value = (b"+OK", [b"1 128"], 128)
    pop3_client.retr.return_value = (b"+OK", raw_message.splitlines(), len(raw_message))
    imported: list[dict[str, object]] = []

    class FakeSession:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    session = FakeSession()

    async def fake_process_fetched_email(
        db_session,
        email_data,
        user_id,
        organization_id,
        workspace_id,
        owner_addresses=None,
    ):
        imported.append(
            {
                "session": db_session,
                "email_data": email_data,
                "user_id": user_id,
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "owner_addresses": owner_addresses,
            }
        )

    monkeypatch.setattr(
        "services.pop3_worker.validate_pop3_destination",
        lambda host, port: (host, port),
    )
    monkeypatch.setattr(
        "services.pop3_worker.AsyncSessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        "services.pop3_worker.process_fetched_email",
        fake_process_fetched_email,
        raising=False,
    )
    monkeypatch.setattr(
        "services.pop3_worker.poplib.POP3_SSL",
        lambda host, port: pop3_client,
    )

    await worker._sync_tenant(config, "workspace-pop3", asyncio.Semaphore(1))

    pop3_client.user.assert_called_once_with("pop3-user@example.com")
    pop3_client.pass_.assert_called_once_with("pop3-secret")
    pop3_client.list.assert_called_once()
    pop3_client.retr.assert_called_once_with(1)
    pop3_client.quit.assert_called_once()
    assert len(imported) == 1
    assert imported[0]["session"] is session
    assert imported[0]["user_id"] == "pop3-user"
    assert imported[0]["organization_id"] == "org-pop3"
    assert imported[0]["owner_addresses"] == ["pop3-user@example.com"]
    assert imported[0]["email_data"]["message_id"] == "<pop3-1@example.com>"
    assert imported[0]["email_data"]["subject"] == "POP3 import"
    assert session.committed is True
    assert session.rolled_back is False


class _FakeTenantResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSyncSession:
    """Fakes the two queries _sync() issues in its own session: an initial
    TenantConfig load, then a per-tenant distinct-workspace resolution scan
    against already-imported Email rows."""

    def __init__(self, tenant_rows, workspace_rows_by_user_id):
        self._tenant_rows = tenant_rows
        self._workspace_rows_by_user_id = workspace_rows_by_user_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _statement):
        return _FakeTenantResult(self._tenant_rows)

    async def scalars(self, _statement):
        rows = self._workspace_rows_by_user_id[self._tenant_rows[0].user_id]

        class _Iter:
            def __iter__(self):
                return iter(rows)

        return _Iter()


@pytest.mark.asyncio
async def test_pop3_sync_resolves_workspace_from_existing_mail(monkeypatch):
    # TenantConfig has no workspace_id column at all; _sync() must derive it
    # from this owner's already-imported Email rows the same way ImapSyncWorker
    # does, not assume one is already attached to the loaded config (attaching
    # one dynamically, as this test used to, hides that _sync() never actually
    # resolved anything in production and every nonempty POP3 fetch silently
    # imported zero messages).
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        organization_id="org-pop3",
        pop3_server="pop3.example.com",
        pop3_port=995,
    )
    session = _FakeSyncSession([config], {"pop3-user": ["workspace-existing"]})
    monkeypatch.setattr("services.pop3_worker.AsyncSessionLocal", lambda: session)

    observed = []

    async def fake_sync_tenant(cfg, workspace_id, _semaphore):
        observed.append((cfg, workspace_id))

    monkeypatch.setattr(worker, "_sync_tenant", fake_sync_tenant)

    await worker._sync()

    assert len(observed) == 1
    assert observed[0][0] is config
    assert observed[0][1] == "workspace-existing"


@pytest.mark.asyncio
async def test_pop3_sync_skips_tenant_with_no_unambiguous_workspace(monkeypatch):
    worker = Pop3SyncWorker()
    config = TenantConfig(
        user_id="pop3-user",
        organization_id="org-pop3",
        pop3_server="pop3.example.com",
        pop3_port=995,
    )
    session = _FakeSyncSession([config], {"pop3-user": []})
    monkeypatch.setattr("services.pop3_worker.AsyncSessionLocal", lambda: session)

    observed = []

    async def fake_sync_tenant(cfg, workspace_id, _semaphore):
        observed.append((cfg, workspace_id))

    monkeypatch.setattr(worker, "_sync_tenant", fake_sync_tenant)

    await worker._sync()

    assert observed == []
