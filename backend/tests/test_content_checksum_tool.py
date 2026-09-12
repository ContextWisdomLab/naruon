"""Regression tests for Naruon's bounded content-checksum tool."""

import hashlib

import pytest

from api.content_checksum_tool import (
    ContentChecksumError,
    register_content_checksum_tool,
)
from api.tools import registry
from main import app


SECURITY_NOTE = (
    "Use this digest to compare exact content bytes; it does not authenticate "
    "the sender or replace a MAC/signature."
)


def test_application_bootstrap_registers_content_checksum_tool() -> None:
    """Loading the FastAPI application must expose the built-in checksum tool."""
    assert app is not None
    assert registry.get("content_checksum_generator") is not None


def test_content_checksum_registration_is_idempotent() -> None:
    """Repeated startup registration must preserve the existing catalog entry."""
    original = registry.get("content_checksum_generator")

    assert original is not None
    register_content_checksum_tool()

    assert registry.get("content_checksum_generator") is original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("algorithm", "expected_digest"),
    [
        (
            "sha256",
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        ),
        (
            "sha3_256",
            "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532",
        ),
        (
            "blake2b_256",
            "bddd813c634239723171ef3fee98579b94964e3bb1cb3e427262c8c068d52319",
        ),
    ],
)
async def test_content_checksum_generator_matches_published_vectors(
    algorithm: str,
    expected_digest: str,
) -> None:
    """The catalog tool must return stable standards-based digests for exact bytes."""
    tool = registry.get("content_checksum_generator")

    assert tool is not None
    assert tool.parameters == {"text": "string", "algorithm": "string"}

    result = await registry.invoke_tool(
        "content_checksum_generator",
        {"text": "abc", "algorithm": algorithm},
    )

    assert result == {
        "algorithm_code": algorithm,
        "digest_hex": expected_digest,
        "byte_length": 3,
        "encoding_code": "utf-8",
        "security_note": SECURITY_NOTE,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ["sha256", "sha3_256", "blake2b_256"])
async def test_content_checksum_generator_matches_incremental_utf8_chunk_reference(
    algorithm: str,
) -> None:
    """One-shot tool output must equal incremental hashing of the same UTF-8 bytes."""
    chunks = ["Naruon ", "이메일 증거", "🙂\n", "second chunk"]
    text = "".join(chunks)
    if algorithm == "blake2b_256":
        reference = hashlib.blake2b(digest_size=32)
    else:
        reference = hashlib.new(algorithm)
    for chunk in chunks:
        reference.update(chunk.encode("utf-8"))

    result = await registry.invoke_tool(
        "content_checksum_generator",
        {"text": text, "algorithm": algorithm},
    )

    assert result["digest_hex"] == reference.hexdigest()
    assert result["byte_length"] == len(text.encode("utf-8"))


@pytest.mark.asyncio
async def test_content_checksum_generator_hashes_exact_utf8_without_normalizing() -> (
    None
):
    """Canonically equivalent Unicode strings must remain distinct exact-byte inputs."""
    composed = await registry.invoke_tool(
        "content_checksum_generator",
        {"text": "é", "algorithm": "sha256"},
    )
    decomposed = await registry.invoke_tool(
        "content_checksum_generator",
        {"text": "e\u0301", "algorithm": "sha256"},
    )

    assert composed["byte_length"] == 2
    assert composed["digest_hex"] == (
        "4a99557e4033c3539de2eb65472017cad5f9557f7a0625a09f1c3f6e2ba69c4c"
    )
    assert decomposed["byte_length"] == 3
    assert decomposed["digest_hex"] == (
        "bf12767b0f2a56b2190075bae8169f656e3ce8d6357d4aff184bc6c7ea48f9f6"
    )
    assert composed["digest_hex"] != decomposed["digest_hex"]


@pytest.mark.asyncio
async def test_content_checksum_generator_rejects_invalid_utf8_scalar_input() -> None:
    """A lone surrogate must fail with the checksum tool's stable validation code."""
    with pytest.raises(ContentChecksumError) as exc_info:
        await registry.invoke_tool(
            "content_checksum_generator",
            {"text": "\ud800", "algorithm": "sha256"},
        )

    assert exc_info.value.error_code == "content_checksum_invalid_utf8"


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ["sha1", "md5", "SHA256", "sha-256", ""])
async def test_content_checksum_generator_rejects_unapproved_algorithm_names(
    algorithm: str,
) -> None:
    """Legacy or ambiguous algorithm names must fail closed instead of being guessed."""
    with pytest.raises(ValueError, match="Unsupported checksum algorithm"):
        await registry.invoke_tool(
            "content_checksum_generator",
            {"text": "abc", "algorithm": algorithm},
        )


@pytest.mark.asyncio
async def test_content_checksum_generator_enforces_utf8_byte_limit() -> None:
    """The one-mebibyte boundary is measured after UTF-8 encoding."""
    accepted = await registry.invoke_tool(
        "content_checksum_generator",
        {"text": "a" * 1_048_576, "algorithm": "sha256"},
    )
    assert accepted["byte_length"] == 1_048_576

    with pytest.raises(ValueError, match="Content exceeds 1048576 UTF-8 bytes"):
        await registry.invoke_tool(
            "content_checksum_generator",
            {"text": "é" * 524_289, "algorithm": "sha256"},
        )