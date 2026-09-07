import socket

import pytest

from services.carddav_discovery import (
    CarddavDiscoveryResult,
    discover_carddav,
    discover_carddav_base_url,
    socket as discovery_socket,
)

PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def force_global_dns(monkeypatch):
    """Resolve every hostname to a public IP so the SSRF guard passes."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port))]

    monkeypatch.setattr(discovery_socket, "getaddrinfo", fake_getaddrinfo)


class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeClient:
    def __init__(self, response):
        self._response = response
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        return self._response


def _factory(response):
    def make():
        return FakeClient(response)

    return make


@pytest.mark.asyncio
async def test_well_known_redirect_resolves_base_url():
    response = FakeResponse(
        301, headers={"Location": "https://dav.example.com/carddav/"}
    )
    result = await discover_carddav(
        "user@example.com",
        http_client_factory=_factory(response),
        srv_resolver=lambda name: [],
    )
    assert result == CarddavDiscoveryResult(
        base_url="https://dav.example.com/carddav/",
        discovery_source="well_known",
    )


@pytest.mark.asyncio
async def test_well_known_200_uses_well_known_path():
    response = FakeResponse(207)
    url = await discover_carddav_base_url(
        "example.com",
        http_client_factory=_factory(response),
        srv_resolver=lambda name: [],
    )
    assert url == "https://example.com/.well-known/carddav"


@pytest.mark.asyncio
async def test_srv_secure_fallback_when_well_known_missing():
    response = FakeResponse(404)

    def resolver(name):
        if name == "_carddavs._tcp.example.com":
            return [("dav.example.com", 443)]
        return []

    result = await discover_carddav(
        "user@example.com",
        http_client_factory=_factory(response),
        srv_resolver=resolver,
    )
    assert result is not None
    assert result.discovery_source == "srv_secure"
    assert result.base_url == "https://dav.example.com/"


@pytest.mark.asyncio
async def test_srv_secure_with_custom_port_and_txt_path():
    response = FakeResponse(404)

    def resolver(name):
        if name == "_carddavs._tcp.example.com":
            return [("dav.example.com", 8443)]
        return []

    def txt_resolver(name):
        if name == "_carddavs._tcp.example.com":
            return ['path=/dav/addressbooks']
        return []

    result = await discover_carddav(
        "example.com",
        http_client_factory=_factory(response),
        srv_resolver=resolver,
        txt_resolver=txt_resolver,
    )
    assert result is not None
    assert result.discovery_source == "srv_secure"
    assert result.base_url == "https://dav.example.com:8443/dav/addressbooks"


@pytest.mark.asyncio
async def test_plain_carddav_srv_is_refused_not_upgraded():
    # A non-TLS _carddav._tcp record must NOT be silently contacted over TLS.
    response = FakeResponse(404)

    def resolver(name):
        if name == "_carddav._tcp.example.com":
            return [("dav.example.com", 8443)]
        return []

    result = await discover_carddav(
        "example.com",
        http_client_factory=_factory(response),
        srv_resolver=resolver,
    )
    assert result is None


@pytest.mark.asyncio
async def test_malformed_txt_path_is_ignored():
    response = FakeResponse(404)

    def resolver(name):
        if name == "_carddavs._tcp.example.com":
            return [("dav.example.com", 443)]
        return []

    def txt_resolver(name):
        # Traversal and absolute-URL path hints are rejected -> fall back to "/".
        return ["path=../escape", "path=https://evil.example/x"]

    result = await discover_carddav(
        "example.com",
        http_client_factory=_factory(response),
        srv_resolver=resolver,
        txt_resolver=txt_resolver,
    )
    assert result is not None
    assert result.base_url == "https://dav.example.com/"


@pytest.mark.parametrize(
    "txt_path",
    [
        "/%2e%2e%2fescape",
        "/%252e%252e%252fescape",
        "/%5c..%5cescape",
        "/%255c..%255cescape",
        "/safe%0aheader",
    ],
)
@pytest.mark.asyncio
async def test_encoded_unsafe_txt_path_is_ignored(txt_path):
    response = FakeResponse(404)

    def resolver(name):
        if name == "_carddavs._tcp.example.com":
            return [("dav.example.com", 443)]
        return []

    result = await discover_carddav(
        "example.com",
        http_client_factory=_factory(response),
        srv_resolver=resolver,
        txt_resolver=lambda name: [f"path={txt_path}"],
    )
    assert result is not None
    assert result.base_url == "https://dav.example.com/"


@pytest.mark.asyncio
async def test_no_discovery_returns_none():
    response = FakeResponse(404)
    result = await discover_carddav(
        "user@example.com",
        http_client_factory=_factory(response),
        srv_resolver=lambda name: [],
    )
    assert result is None


@pytest.mark.asyncio
async def test_invalid_input_returns_none():
    assert (
        await discover_carddav_base_url(
            "not-an-email-or-domain",
            http_client_factory=_factory(FakeResponse(200)),
            srv_resolver=lambda name: [],
        )
        is None
    )


@pytest.mark.asyncio
async def test_private_host_is_rejected_by_ssrf_guard():
    # A well-known redirect pointing at a private IP must be discarded.
    response = FakeResponse(302, headers={"Location": "https://10.0.0.5/carddav/"})
    result = await discover_carddav(
        "user@example.com",
        http_client_factory=_factory(response),
        srv_resolver=lambda name: [],
    )
    assert result is None
