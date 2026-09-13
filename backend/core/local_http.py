"""Shared validation for local-only HTTP smoke and live-test requests."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

ALLOWED_LOOPBACK_HTTP_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class LocalHTTPValidationError(ValueError):
    """Raised when a local HTTP origin or request target is unsafe."""


@dataclass(frozen=True)
class LocalHTTPOrigin:
    """A canonical loopback-only HTTP(S) origin."""

    origin: str
    scheme: str
    hostname: str
    port: int


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def validate_loopback_http_origin(value: str) -> LocalHTTPOrigin:
    """Return a canonical origin restricted to exact loopback hosts."""
    if _has_control_characters(value):
        raise LocalHTTPValidationError("local HTTP origin contains control characters")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise LocalHTTPValidationError(
            "local HTTP origin must be a loopback HTTP(S) origin"
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise LocalHTTPValidationError(
            "local HTTP origin must be a loopback HTTP(S) origin"
        )

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost":
        safe_hostname = hostname
    else:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise LocalHTTPValidationError(
                "local HTTP origin host is not allowlisted"
            ) from exc
        if (
            not address.is_loopback
            or address.compressed not in ALLOWED_LOOPBACK_HTTP_HOSTS
        ):
            raise LocalHTTPValidationError("local HTTP origin host is not allowlisted")
        safe_hostname = address.compressed

    try:
        port = (
            parsed.port
            if parsed.port is not None
            else (443 if parsed.scheme == "https" else 80)
        )
    except ValueError as exc:
        raise LocalHTTPValidationError("local HTTP origin port is invalid") from exc
    if not 1 <= port <= 65535:
        raise LocalHTTPValidationError("local HTTP origin port is invalid")

    host_part = f"[{safe_hostname}]" if ":" in safe_hostname else safe_hostname
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host_part if port == default_port else f"{host_part}:{port}"
    origin = urlunsplit((parsed.scheme, netloc, "", "", ""))
    return LocalHTTPOrigin(origin, parsed.scheme, safe_hostname, port)


def validate_local_request_target(
    path: str,
    *,
    allowed_exact_paths: frozenset[str] = frozenset(),
) -> str:
    """Return a relative local API target with traversal and authority rejected."""
    if _has_control_characters(path):
        raise LocalHTTPValidationError("local request path contains control characters")
    try:
        parsed = urlsplit(path)
    except ValueError as exc:
        raise LocalHTTPValidationError("request path must be a local API path") from exc
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise LocalHTTPValidationError("request path must be a local API path")
    if not (parsed.path.startswith("/api/") or parsed.path in allowed_exact_paths):
        raise LocalHTTPValidationError(
            "request path must target an allowed local endpoint"
        )
    if _INVALID_PERCENT_ESCAPE.search(parsed.path):
        raise LocalHTTPValidationError(
            "local request path contains invalid percent encoding"
        )
    for raw_segment in parsed.path.split("/"):
        try:
            decoded_segment = unquote(raw_segment, errors="strict")
        except UnicodeDecodeError as exc:
            raise LocalHTTPValidationError(
                "local request path contains invalid percent encoding"
            ) from exc
        if (
            decoded_segment in {".", ".."}
            or "/" in decoded_segment
            or "\\" in decoded_segment
        ):
            raise LocalHTTPValidationError(
                "local request path traversal is not allowed"
            )
        if _has_control_characters(decoded_segment):
            raise LocalHTTPValidationError(
                "local request path contains control characters"
            )
    return urlunsplit(("", "", parsed.path, parsed.query, ""))
