import socket

import httpx
import pytest

from runner.local_dav_adapters import LocalDavAdapters, LocalDavSourceConfig


class FakeDavResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeDavClient:
    def __init__(self, response: FakeDavResponse):
        self.response = response
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def put(self, url, *, content, headers, auth):
        self.requests.append(
            {
                "url": url,
                "content": content,
                "headers": headers,
                "auth": auth,
            }
        )
        return self.response


class FailingDavClient(FakeDavClient):
    async def put(self, url, *, content, headers, auth):
        raise httpx.ConnectError("provider unavailable")


@pytest.fixture(autouse=True)
def stub_dav_dns(monkeypatch):
    def fake_getaddrinfo(host, port, type=socket.SOCK_STREAM):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", port),
            )
        ]

    monkeypatch.setattr(
        "runner.local_dav_adapters.socket.getaddrinfo", fake_getaddrinfo
    )


def test_webdav_adapter_canonicalizes_encoded_unicode_path():
    adapters = LocalDavAdapters([])

    assert (
        adapters._safe_target_path(  # noqa: SLF001 - security boundary regression
            "/Naruon/%ED%95%9C%EA%B8%80%20note.md"
        )
        == "/Naruon/%ED%95%9C%EA%B8%80%20note.md"
    )


@pytest.mark.asyncio
async def test_webdav_adapter_puts_content_with_if_match():
    fake_client = FakeDavClient(
        FakeDavResponse(204, headers={"ETag": "etag-after-write"})
    )
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com/remote.php/dav/files/alice",
                username="alice",
                password="dav-secret",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": "/Naruon/Notes/task.md",
            "content": "# Note\n",
            "content_type": "text/markdown; charset=utf-8",
            "if_match": "etag-before-write",
        }
    )

    assert result == {
        "status": "success",
        "provider_write_executed": True,
        "provider_status": 204,
        "etag": "etag-after-write",
    }
    assert fake_client.requests == [
        {
            "url": "https://webdav.example.com/remote.php/dav/files/alice/Naruon/Notes/task.md",
            "content": b"# Note\n",
            "headers": {
                "Content-Type": "text/markdown; charset=utf-8",
                "If-Match": "etag-before-write",
            },
            "auth": ("alice", "dav-secret"),
        }
    ]


@pytest.mark.asyncio
async def test_webdav_adapter_requires_if_match_before_network_request():
    fake_client = FakeDavClient(FakeDavResponse(204))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": "/Naruon/Notes/task.md",
            "content": "# Note\n",
        }
    )

    assert result == {
        "status": "error",
        "error": "missing_if_match",
        "error_code": "missing_if_match",
        "provider_write_executed": False,
    }
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_webdav_adapter_reports_provider_conflict_without_write_success():
    fake_client = FakeDavClient(FakeDavResponse(412))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": "/Naruon/Notes/task.md",
            "content": "# Note\n",
            "if_match": "stale-etag",
        }
    )

    assert result == {
        "status": "conflict",
        "error": "provider_conflict",
        "error_code": "provider_conflict",
        "provider_write_executed": False,
        "provider_status": 412,
    }


@pytest.mark.parametrize(
    "target_path",
    [
        "/Naruon/../Secrets/task.md",
        "/Naruon/%2e%2e/Secrets/task.md",
        "/Naruon/%252e%252e/Secrets/task.md",
        "/Naruon/%25252525252e%25252525252e/Secrets/task.md",
        "/Naruon/%5c..%5cSecrets/task.md",
        "/Naruon/%00Secrets/task.md",
        "/Naruon/%FF/task.md",
        "/" + "a" * 4096,
    ],
)
@pytest.mark.asyncio
async def test_webdav_adapter_rejects_path_traversal_before_network_request(
    target_path,
):
    fake_client = FakeDavClient(FakeDavResponse(204))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": target_path,
            "content": "# Note\n",
            "if_match": "etag-before-write",
        }
    )

    assert result == {
        "status": "error",
        "error": "invalid_target_path",
        "error_code": "invalid_target_path",
        "provider_write_executed": False,
    }
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_webdav_adapter_rejects_private_source_url_before_network_request(
    monkeypatch,
):
    def fake_private_getaddrinfo(host, port, type=socket.SOCK_STREAM):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("192.168.1.10", port),
            )
        ]

    monkeypatch.setattr(
        "runner.local_dav_adapters.socket.getaddrinfo",
        fake_private_getaddrinfo,
    )
    fake_client = FakeDavClient(FakeDavResponse(204))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": "/Naruon/Notes/task.md",
            "content": "# Note\n",
            "if_match": "etag-before-write",
        }
    )

    assert result == {
        "status": "error",
        "error": "invalid_source_url",
        "error_code": "invalid_source_url",
        "provider_write_executed": False,
    }
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_caldav_adapter_puts_icalendar_content_with_if_match():
    fake_client = FakeDavClient(FakeDavResponse(201, headers={"ETag": "caldav-etag"}))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="caldav_src_1",
                protocol="caldav",
                base_url="https://calendar.example.com/dav/calendars/alice/tasks",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_caldav(
        {
            "source_id": "caldav_src_1",
            "target_path": "/naruon-task.ics",
            "content": "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
            "if_match": "caldav-before",
        }
    )

    assert result == {
        "status": "success",
        "provider_write_executed": True,
        "provider_status": 201,
        "etag": "caldav-etag",
    }
    assert fake_client.requests[0]["url"] == (
        "https://calendar.example.com/dav/calendars/alice/tasks/naruon-task.ics"
    )
    assert fake_client.requests[0]["headers"] == {
        "Content-Type": "text/calendar; charset=utf-8",
        "If-Match": "caldav-before",
    }


@pytest.mark.asyncio
async def test_webdav_adapter_rejects_unresolvable_source_url_before_network_request(
    monkeypatch,
):
    def fake_unresolvable_getaddrinfo(host, port, type=socket.SOCK_STREAM):
        raise OSError("Name or service not known")

    monkeypatch.setattr(
        "runner.local_dav_adapters.socket.getaddrinfo",
        fake_unresolvable_getaddrinfo,
    )
    fake_client = FakeDavClient(FakeDavResponse(204))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": "/Naruon/Notes/task.md",
            "content": "# Note\n",
            "if_match": "etag-before-write",
        }
    )

    assert result == {
        "status": "error",
        "error": "invalid_source_url",
        "error_code": "invalid_source_url",
        "provider_write_executed": False,
    }
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_webdav_adapter_rejects_invalid_port_before_dns_lookup(monkeypatch):
    def fail_getaddrinfo(host, port, type=socket.SOCK_STREAM):
        raise AssertionError("invalid port URL should fail before DNS lookup")

    monkeypatch.setattr(
        "runner.local_dav_adapters.socket.getaddrinfo",
        fail_getaddrinfo,
    )
    fake_client = FakeDavClient(FakeDavResponse(204))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="webdav_src_1",
                protocol="webdav",
                base_url="https://webdav.example.com:abc",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_webdav(
        {
            "source_id": "webdav_src_1",
            "target_path": "/Naruon/Notes/task.md",
            "content": "# Note\n",
            "if_match": "etag-before-write",
        }
    )

    assert result == {
        "status": "error",
        "error": "invalid_source_url",
        "error_code": "invalid_source_url",
        "provider_write_executed": False,
    }
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_dav_adapter_default_client_and_payload_helper_boundaries():
    adapters = LocalDavAdapters([])
    client = adapters._default_http_client()  # noqa: SLF001
    assert client.follow_redirects is False
    await client.aclose()

    assert adapters._payload_text({"value": 1}, "value") is None  # noqa: SLF001
    assert adapters._payload_text({"value": "  "}, "value") is None  # noqa: SLF001
    assert adapters._payload_content(b"bytes") == b"bytes"  # noqa: SLF001
    assert adapters._payload_content(object()) is None  # noqa: SLF001
    assert adapters._safe_target_path(None) is None  # noqa: SLF001
    assert adapters._safe_target_path("/") is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_dav_adapter_rejects_source_and_payload_states_before_network():
    fake_client = FakeDavClient(FakeDavResponse(204))
    disabled = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="disabled",
                protocol="webdav",
                base_url="https://webdav.example.com",
            ),
            LocalDavSourceConfig(
                source_id="calendar",
                protocol="caldav",
                base_url="https://calendar.example.com",
                writeback_enabled=True,
            ),
            LocalDavSourceConfig(
                source_id="enabled",
                protocol="webdav",
                base_url="https://webdav.example.com",
                writeback_enabled=True,
            ),
        ],
        http_client_factory=lambda: fake_client,
    )
    base_payload = {
        "target_path": "/Naruon/task.md",
        "content": "note",
        "if_match": "etag",
    }

    assert (await disabled.write_webdav(base_payload))["error_code"] == (
        "source_not_configured"
    )
    assert (await disabled.write_webdav({**base_payload, "source_id": "calendar"}))[
        "error_code"
    ] == "source_not_configured"
    assert (await disabled.write_webdav({**base_payload, "source_id": "disabled"}))[
        "error_code"
    ] == "source_writeback_disabled"
    assert (
        await disabled.write_webdav(
            {**base_payload, "source_id": "enabled", "content": object()}
        )
    )["error_code"] == "invalid_payload"
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_dav_adapter_reports_provider_transport_and_status_failures():
    source = LocalDavSourceConfig(
        source_id="webdav",
        protocol="webdav",
        base_url="https://webdav.example.com",
        writeback_enabled=True,
    )
    payload = {
        "source_id": "webdav",
        "target_path": "/Naruon/task.md",
        "content": "note",
        "if_match": "etag",
    }
    transport_failure = LocalDavAdapters(
        [source],
        http_client_factory=lambda: FailingDavClient(FakeDavResponse(204)),
    )
    status_failure = LocalDavAdapters(
        [source],
        http_client_factory=lambda: FakeDavClient(FakeDavResponse(503)),
    )

    assert (await transport_failure.write_webdav(payload))["error_code"] == (
        "provider_request_failed"
    )
    assert await status_failure.write_webdav(payload) == {
        "status": "error",
        "error": "provider_write_failed",
        "error_code": "provider_write_failed",
        "provider_write_executed": False,
        "provider_status": 503,
    }


def test_dav_adapter_rejects_invalid_source_url_boundaries(monkeypatch):
    adapters = LocalDavAdapters([])

    with pytest.raises(ValueError, match="invalid_source_url"):
        adapters._target_url("http://webdav.example.com", "/task.md")  # noqa: SLF001
    assert (
        adapters._target_url(  # noqa: SLF001
            "https://93.184.216.34", "/task.md"
        )
        == "https://93.184.216.34/task.md"
    )
    with pytest.raises(ValueError, match="invalid_source_url"):
        adapters._validate_global_address("not-an-ip")  # noqa: SLF001

    monkeypatch.setattr(
        "runner.local_dav_adapters.socket.getaddrinfo",
        lambda *_args, **_kwargs: [],
    )
    with pytest.raises(ValueError, match="invalid_source_url"):
        adapters._target_url("https://empty.example.com", "/task.md")  # noqa: SLF001


@pytest.mark.asyncio
async def test_carddav_adapter_puts_vcard_with_if_match():
    fake_client = FakeDavClient(
        FakeDavResponse(201, headers={"ETag": "etag-vcard"})
    )
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="carddav_src_1",
                protocol="carddav",
                base_url="https://dav.example.com/carddav/addressbooks/alice",
                username="alice",
                password="dav-secret",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    result = await adapters.write_carddav(
        {
            "source_id": "carddav_src_1",
            "target_path": "/contact.vcf",
            "content": "BEGIN:VCARD\r\nEND:VCARD\r\n",
            "if_match": "etag-before",
        }
    )

    assert result["status"] == "success"
    assert result["provider_write_executed"] is True
    assert fake_client.requests[0]["url"] == (
        "https://dav.example.com/carddav/addressbooks/alice/contact.vcf"
    )
    assert fake_client.requests[0]["headers"]["Content-Type"] == (
        "text/vcard; charset=utf-8"
    )


@pytest.mark.asyncio
async def test_carddav_adapter_rejects_protocol_mismatch():
    fake_client = FakeDavClient(FakeDavResponse(201))
    adapters = LocalDavAdapters(
        [
            LocalDavSourceConfig(
                source_id="caldav_src_1",
                protocol="caldav",
                base_url="https://dav.example.com/caldav/alice",
                writeback_enabled=True,
            )
        ],
        http_client_factory=lambda: fake_client,
    )

    # A carddav write against a caldav-only source must not be dispatched.
    result = await adapters.write_carddav(
        {
            "source_id": "caldav_src_1",
            "target_path": "/contact.vcf",
            "content": "BEGIN:VCARD\r\nEND:VCARD\r\n",
            "if_match": "etag-before",
        }
    )
    assert result["status"] == "error"
    assert result["error_code"] == "source_not_configured"
    assert fake_client.requests == []
