import pytest

from core.local_http import (
    LocalHTTPOrigin,
    LocalHTTPValidationError,
    validate_local_request_target,
    validate_loopback_http_origin,
)


def test_loopback_origin_is_canonicalized() -> None:
    assert validate_loopback_http_origin("http://[::1]:18080/") == LocalHTTPOrigin(
        origin="http://[::1]:18080",
        scheme="http",
        hostname="::1",
        port=18080,
    )
    assert validate_loopback_http_origin("http://localhost") == LocalHTTPOrigin(
        origin="http://localhost",
        scheme="http",
        hostname="localhost",
        port=80,
    )
    assert validate_loopback_http_origin("https://127.0.0.1:443/") == LocalHTTPOrigin(
        origin="https://127.0.0.1",
        scheme="https",
        hostname="127.0.0.1",
        port=443,
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://[::1",
        "http://[localhost]:18080",
    ],
)
def test_loopback_origin_normalizes_malformed_parser_errors(value: str) -> None:
    with pytest.raises(
        LocalHTTPValidationError,
        match=r"must be a loopback HTTP\(S\) origin",
    ):
        validate_loopback_http_origin(value)


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:80\x00/",
        "http://\nlocalhost/",
    ],
)
def test_loopback_origin_rejects_control_characters(value: str) -> None:
    with pytest.raises(LocalHTTPValidationError, match="control characters"):
        validate_loopback_http_origin(value)


@pytest.mark.parametrize(
    "value",
    [
        "ftp://localhost/",
        "http://user:pass@localhost/",
        "http://localhost/path",
        "http://localhost/?query=1",
        "http://localhost/#frag",
        "http:///",  # No hostname
    ],
)
def test_loopback_origin_rejects_invalid_components(value: str) -> None:
    with pytest.raises(
        LocalHTTPValidationError, match=r"must be a loopback HTTP\(S\) origin"
    ):
        validate_loopback_http_origin(value)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com/",
        "http://192.168.1.1/",
        "http://[2001:db8::1]/",
        "http://invalid.localhost/",
    ],
)
def test_loopback_origin_rejects_non_allowlisted_hosts(value: str) -> None:
    with pytest.raises(LocalHTTPValidationError, match="host is not allowlisted"):
        validate_loopback_http_origin(value)


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:-1/",
        "http://localhost:65536/",
        "http://localhost:abc/",
        "http://localhost:0/",
    ],
)
def test_loopback_origin_rejects_invalid_ports(value: str) -> None:
    with pytest.raises(LocalHTTPValidationError, match="port is invalid"):
        validate_loopback_http_origin(value)


def test_local_request_target_preserves_safe_path_and_query() -> None:
    assert (
        validate_local_request_target("/api/emails?limit=10") == "/api/emails?limit=10"
    )
    assert (
        validate_local_request_target(
            "/auth/session",
            allowed_exact_paths=frozenset({"/auth/session"}),
        )
        == "/auth/session"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/../auth/session",
        "/api/%2e%2e/auth/session",
        "/api/%2E%2E/auth/session",
        "/api/%2fadmin",
        "/api/%2Fadmin",
        "/api/%5cadmin",
        "/api/%5Cadmin",
        r"/api/\admin",
    ],
)
def test_local_request_target_rejects_raw_and_encoded_traversal(path: str) -> None:
    with pytest.raises(LocalHTTPValidationError, match="traversal"):
        validate_local_request_target(path)


@pytest.mark.parametrize(
    "path",
    [
        "/api/%",
        "/api/%2",
        "/api/%GG",
        "/api/%FF",
    ],
)
def test_local_request_target_rejects_invalid_percent_encoding(path: str) -> None:
    with pytest.raises(LocalHTTPValidationError, match="percent encoding"):
        validate_local_request_target(path)


def test_local_request_target_normalizes_malformed_parser_errors() -> None:
    with pytest.raises(LocalHTTPValidationError, match="local API path"):
        validate_local_request_target("//[::1")
