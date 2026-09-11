import hashlib

import pytest

from services.content_checksum import (
    SUPPORTED_ALGORITHMS,
    generate_chunked_checksum,
    generate_content_checksum,
)


@pytest.mark.parametrize("algorithm", SUPPORTED_ALGORITHMS)
def test_supported_algorithms_match_hashlib(algorithm):
    content = "Naruon checksum evidence"
    expected = {
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "sha3_256": hashlib.sha3_256(content.encode()).hexdigest(),
        "blake2b_256": hashlib.blake2b(content.encode(), digest_size=32).hexdigest(),
    }[algorithm]

    assert generate_content_checksum(content, algorithm) == expected


@pytest.mark.parametrize("algorithm", SUPPORTED_ALGORITHMS)
def test_chunked_checksum_matches_one_shot(algorithm):
    chunks = [b"Naruon ", b"checksum ", b"evidence"]

    assert generate_chunked_checksum(chunks, algorithm) == generate_content_checksum(
        b"".join(chunks), algorithm
    )


def test_text_encoding_is_explicit_utf8():
    assert generate_content_checksum("한글") == hashlib.sha256("한글".encode("utf-8")).hexdigest()


@pytest.mark.parametrize("algorithm", ["md5", "sha1", "unknown"])
def test_unsupported_and_legacy_algorithms_fail_closed(algorithm):
    with pytest.raises(ValueError, match="unsupported checksum algorithm"):
        generate_content_checksum(b"content", algorithm)


def test_invalid_content_types_fail_closed_without_serialization():
    with pytest.raises(TypeError, match="content must be bytes or str"):
        generate_content_checksum(123)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="checksum chunks must be bytes"):
        generate_chunked_checksum([b"ok", "not bytes"])  # type: ignore[list-item]
