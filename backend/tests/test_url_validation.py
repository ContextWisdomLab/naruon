import pytest
import socket
from unittest.mock import patch

from core.url_validation import (
    parse_allowed_hosts,
    validate_https_url_host,
    validate_same_or_subdomain_host,
    validate_https_url_host_details,
    _normalize_host,
    _reject_unsafe_ip_literal,
    _validate_global_address,
    _resolve_global_addresses,
)


def test_parse_allowed_hosts():
    assert parse_allowed_hosts("example.com, TEST.COM. , [2001:db8::1]") == frozenset(
        {"example.com", "test.com", "2001:db8::1"}
    )
    assert parse_allowed_hosts("") == frozenset()
    assert parse_allowed_hosts("   ") == frozenset()
    assert parse_allowed_hosts("example.com,, example.com , example.net") == frozenset(
        {"example.com", "example.net"}
    )


def test_normalize_host():
    assert _normalize_host(" Example.COM. ") == "example.com"
    assert _normalize_host("[2001:db8::1]") == "2001:db8::1"
    assert _normalize_host("test") == "test"


def test_reject_unsafe_ip_literal():
    # Safe global IP
    _reject_unsafe_ip_literal("setting", "8.8.8.8")
    _reject_unsafe_ip_literal("setting", "2001:4860:4860::8888")

    # Non-global IP
    with pytest.raises(ValueError, match="setting IP host must be globally routable"):
        _reject_unsafe_ip_literal("setting", "127.0.0.1")
    with pytest.raises(ValueError, match="setting IP host must be globally routable"):
        _reject_unsafe_ip_literal("setting", "::1")

    with pytest.raises(
        ValueError, match="setting host must not be a local or internal domain"
    ):
        _reject_unsafe_ip_literal("setting", "localhost")
    with pytest.raises(
        ValueError, match="setting host must not be a local or internal domain"
    ):
        _reject_unsafe_ip_literal("setting", "test.localhost")
    with pytest.raises(
        ValueError, match="setting host must not be a local or internal domain"
    ):
        _reject_unsafe_ip_literal("setting", "internal")
    with pytest.raises(
        ValueError, match="setting host must not be a local or internal domain"
    ):
        _reject_unsafe_ip_literal("setting", "test.internal")
    with pytest.raises(
        ValueError, match="setting host must not be a local or internal domain"
    ):
        _reject_unsafe_ip_literal("setting", "test.local")

    # Standard domain name
    _reject_unsafe_ip_literal("setting", "example.com")


def test_validate_global_address():
    assert _validate_global_address("setting", "8.8.8.8") == "8.8.8.8"
    assert (
        _validate_global_address("setting", "2001:4860:4860::8888")
        == "2001:4860:4860::8888"
    )

    with pytest.raises(
        ValueError, match="setting resolved IP host must be globally routable"
    ):
        _validate_global_address("setting", "127.0.0.1")

    with pytest.raises(
        ValueError, match="setting resolved IP host must be globally routable"
    ):
        _validate_global_address("setting", "invalid-ip")


@patch("socket.getaddrinfo")
def test_resolve_global_addresses(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.4.4", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),  # duplicate
        (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            6,
            "",
            ("2001:4860:4860::8888", 443, 0, 0),
        ),
    ]
    addresses = _resolve_global_addresses("setting", "example.com", 443)
    assert addresses == ("8.8.8.8", "8.8.4.4", "2001:4860:4860::8888")
    mock_getaddrinfo.assert_called_once_with(
        "example.com", 443, type=socket.SOCK_STREAM
    )


@patch("socket.getaddrinfo")
def test_resolve_global_addresses_gaierror(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
    with pytest.raises(
        ValueError, match="setting host must resolve to a global address"
    ):
        _resolve_global_addresses("setting", "example.com", 443)


@patch("socket.getaddrinfo")
def test_resolve_global_addresses_no_global(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ]
    with pytest.raises(
        ValueError, match="setting resolved IP host must be globally routable"
    ):
        _resolve_global_addresses("setting", "example.com", 443)


@patch("socket.getaddrinfo")
def test_resolve_global_addresses_empty(mock_getaddrinfo):
    mock_getaddrinfo.return_value = []
    with pytest.raises(
        ValueError, match="setting host must resolve to a global address"
    ):
        _resolve_global_addresses("setting", "example.com", 443)


@patch("core.url_validation._resolve_global_addresses")
def test_validate_https_url_host_details(mock_resolve):
    mock_resolve.return_value = ("8.8.8.8",)

    # Success
    res = validate_https_url_host_details(
        "setting",
        "https://example.com/path",
        frozenset({"example.com"}),
        "ALLOWED_HOSTS",
    )
    assert res.normalized_url == "https://example.com/path"
    assert res.hostname == "example.com"
    assert res.port == 443
    assert res.addresses == ("8.8.8.8",)

    # Success with port
    res2 = validate_https_url_host_details(
        "setting",
        "https://example.com:8443/path",
        frozenset({"example.com"}),
        "ALLOWED_HOSTS",
    )
    assert res2.normalized_url == "https://example.com:8443/path"
    assert res2.hostname == "example.com"
    assert res2.port == 8443
    assert res2.addresses == ("8.8.8.8",)

    # Not https
    with pytest.raises(ValueError, match="setting must use https"):
        validate_https_url_host_details(
            "setting",
            "http://example.com/path",
            frozenset({"example.com"}),
            "ALLOWED_HOSTS",
        )

    # Userinfo
    with pytest.raises(ValueError, match="setting must not include userinfo"):
        validate_https_url_host_details(
            "setting",
            "https://user:pass@example.com/path",
            frozenset({"example.com"}),
            "ALLOWED_HOSTS",
        )

    # Fragment
    with pytest.raises(ValueError, match="setting must not include a fragment"):
        validate_https_url_host_details(
            "setting",
            "https://example.com/path#frag",
            frozenset({"example.com"}),
            "ALLOWED_HOSTS",
        )

    # No host
    with pytest.raises(ValueError, match="setting must include a host"):
        validate_https_url_host_details(
            "setting", "https:///path", frozenset({"example.com"}), "ALLOWED_HOSTS"
        )

    # Host not in allowed
    with pytest.raises(
        ValueError, match="setting host must be listed in ALLOWED_HOSTS"
    ):
        validate_https_url_host_details(
            "setting",
            "https://bad.com/path",
            frozenset({"example.com"}),
            "ALLOWED_HOSTS",
        )


@patch("core.url_validation.validate_https_url_host_details")
def test_validate_https_url_host(mock_details):
    validate_https_url_host(
        "setting", "https://example.com", frozenset({"example.com"}), "ALLOWED_HOSTS"
    )
    mock_details.assert_called_once_with(
        "setting", "https://example.com", frozenset({"example.com"}), "ALLOWED_HOSTS"
    )


def test_validate_same_or_subdomain_host_rejects_suffix_confusion():
    for valid_host in (
        "issuer.example.com",
        "jwks.issuer.example.com",
        "a.b.c.issuer.example.com",
    ):
        validate_same_or_subdomain_host(
            "OIDC_JWKS_URL", valid_host, "OIDC_ISSUER_URL", "issuer.example.com"
        )

    for invalid_host in (
        "other.com",
        "fakeissuer.example.com",
        "issuer.example.com.attacker.com",
        "notexample.com",
    ):
        with pytest.raises(
            ValueError,
            match="OIDC_JWKS_URL host must match or be a subdomain of OIDC_ISSUER_URL host",
        ):
            validate_same_or_subdomain_host(
                "OIDC_JWKS_URL", invalid_host, "OIDC_ISSUER_URL", "issuer.example.com"
            )
