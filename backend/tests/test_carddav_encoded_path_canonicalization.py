"""Regression tests for canonical CardDAV TXT context-path execution."""

import pytest

from services.carddav_discovery import _txt_context_path


def test_fully_encoded_leading_slash_is_canonicalized() -> None:
    """Execute the same singly decoded representation that passed validation."""
    assert _txt_context_path(["path=%2Fsafe"]) == "/safe"


def test_percent_encoded_unicode_path_is_canonicalized() -> None:
    """Preserve a safe Unicode path after one percent-decoding pass."""
    assert _txt_context_path(["path=/%EC%A3%BC%EC%86%8C%EB%A1%9D"]) == "/주소록"


@pytest.mark.parametrize(
    ("txt_path", "expected_path"),
    [
        ("/users/alice%2Fcalendar", "/users/alice%2Fcalendar"),
        ("/collections/a%3Bb", "/collections/a%3Bb"),
    ],
)
def test_encoded_reserved_path_characters_preserve_wire_identity(
    txt_path: str,
    expected_path: str,
) -> None:
    """Validate reserved escapes without turning them into path delimiters."""
    assert _txt_context_path([f"path={txt_path}"]) == expected_path


@pytest.mark.parametrize(
    "txt_path",
    [
        "/literal%252Fsegment",
        "/%252e%252e%252fescape",
        "/safe%2525control",
    ],
)
def test_nested_percent_encoding_is_rejected(txt_path: str) -> None:
    """Reject values whose meaning would change under a second decode pass."""
    assert _txt_context_path([f"path={txt_path}"]) is None


@pytest.mark.parametrize("txt_path", ["/safe%", "/safe%2", "/safe%2G"])
def test_malformed_percent_triplets_are_rejected(txt_path: str) -> None:
    """Reject malformed URI percent encodings instead of forwarding ambiguity."""
    assert _txt_context_path([f"path={txt_path}"]) is None


def test_invalid_utf8_percent_octet_is_rejected() -> None:
    """Reject invalid UTF-8 rather than accepting a replacement-character path."""
    assert _txt_context_path(["path=/safe%FF"]) is None


def test_encoded_literal_percent_is_preserved_after_one_decode() -> None:
    """Allow a single encoded percent when it does not form another triplet."""
    assert _txt_context_path(["path=/discount-100%25"]) == "/discount-100%"
