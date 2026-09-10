"""Bounded cryptographic checksums for exact UTF-8 text content.

This module owns the checksum algorithm allowlist and registers the tool with
Naruon's existing deterministic tool catalog. Its digests compare content
bytes; they are not proof of sender identity or message authenticity.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from api.tools import ToolInfo, registry

MAX_CONTENT_BYTES = 1_048_576
SECURITY_NOTE = (
    "Use this digest to compare exact content bytes; it does not authenticate "
    "the sender or replace a MAC/signature."
)


class ContentChecksumError(ValueError):
    """Expected checksum validation failure with a stable machine error code."""

    def __init__(self, message: str, *, error_code: str) -> None:
        """Initialize a customer-safe validation failure and deterministic code."""
        super().__init__(message)
        self.error_code = error_code


def _sha256(payload: bytes) -> str:
    """Return the SHA-256 hexadecimal digest for ``payload``."""
    return hashlib.sha256(payload).hexdigest()


def _sha3_256(payload: bytes) -> str:
    """Return the SHA-3-256 hexadecimal digest for ``payload``."""
    return hashlib.sha3_256(payload).hexdigest()


def _blake2b_256(payload: bytes) -> str:
    """Return the 256-bit BLAKE2b hexadecimal digest for ``payload``."""
    return hashlib.blake2b(payload, digest_size=32).hexdigest()


_HASHERS: dict[str, Callable[[bytes], str]] = {
    "sha256": _sha256,
    "sha3_256": _sha3_256,
    "blake2b_256": _blake2b_256,
}


async def content_checksum_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Hash exact UTF-8 bytes with an allowlisted modern checksum algorithm.

    The input is never Unicode-normalized, so the digest compares the exact
    byte representation Naruon received. Inputs larger than one MiB after
    UTF-8 encoding are rejected before hashing.

    Args:
        params: Validated tool parameters containing ``text`` and ``algorithm``.

    Returns:
        A deterministic checksum receipt with the algorithm, digest, byte
        length, encoding, and an authenticity warning.

    Raises:
        ContentChecksumError: If the algorithm is not allowlisted, the text
            cannot be represented as valid UTF-8, or the encoded content exceeds
            one MiB. Each expected failure carries a stable machine-readable
            ``error_code``.
    """
    text = params["text"]
    algorithm = params["algorithm"]
    if algorithm not in _HASHERS:
        raise ContentChecksumError(
            "Unsupported checksum algorithm; choose sha256, sha3_256, or blake2b_256",
            error_code="unsupported_checksum_algorithm",
        )

    try:
        payload = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContentChecksumError(
            "Content must contain valid Unicode scalar values",
            error_code="content_checksum_invalid_utf8",
        ) from exc
    if len(payload) > MAX_CONTENT_BYTES:
        raise ContentChecksumError(
            f"Content exceeds {MAX_CONTENT_BYTES} UTF-8 bytes",
            error_code="content_checksum_payload_too_large",
        )

    return {
        "algorithm_code": algorithm,
        "digest_hex": _HASHERS[algorithm](payload),
        "byte_length": len(payload),
        "encoding_code": "utf-8",
        "security_note": SECURITY_NOTE,
    }


def register_content_checksum_tool() -> None:
    """Register the checksum generator once in Naruon's built-in tool catalog."""
    if registry.get("content_checksum_generator") is not None:
        return

    registry.register(
        ToolInfo(
            code="content_checksum_generator",
            name="Content checksum generator",
            description=(
                "Compare exact UTF-8 content using SHA-256, SHA-3-256, or "
                "BLAKE2b-256. Choose an algorithm, then compare the returned "
                "digest with the expected value."
            ),
            category="유틸리티",
            parameters={"text": "string", "algorithm": "string"},
        ),
        content_checksum_handler,
    )
