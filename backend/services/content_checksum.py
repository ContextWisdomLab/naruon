"""Secure content checksums for non-authentication integrity use.

The normal surface permits only SHA-256, SHA3-256, and BLAKE2b-256. Legacy
digests are intentionally not exposed as compatibility options here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

SUPPORTED_ALGORITHMS = ("sha256", "sha3_256", "blake2b_256")
_ALGORITHM_FACTORIES = {
    "sha256": hashlib.sha256,
    "sha3_256": hashlib.sha3_256,
    "blake2b_256": lambda: hashlib.blake2b(digest_size=32),
}


def _content_bytes(content: bytes | str) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise TypeError("content must be bytes or str")


def _new_hasher(algorithm: str):
    try:
        return _ALGORITHM_FACTORIES[algorithm]()
    except KeyError as exc:
        raise ValueError("unsupported checksum algorithm") from exc


def generate_content_checksum(
    content: bytes | str,
    algorithm: str = "sha256",
) -> str:
    """Return a lowercase hexadecimal checksum for content."""
    hasher = _new_hasher(algorithm)
    hasher.update(_content_bytes(content))
    return hasher.hexdigest()


def generate_chunked_checksum(
    chunks: Iterable[bytes],
    algorithm: str = "sha256",
) -> str:
    """Return the same checksum as one-shot hashing over ordered byte chunks."""
    hasher = _new_hasher(algorithm)
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise TypeError("checksum chunks must be bytes")
        hasher.update(chunk)
    return hasher.hexdigest()
