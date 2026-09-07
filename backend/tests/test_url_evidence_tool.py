"""Contract tests for bounded URL evidence extraction."""

import pytest

import main
from api.tools import ExecuteRequest, execute_tool, registry
from api.url_evidence_tool import (
    MAX_URL_EVIDENCE_BYTES,
    MAX_URL_EVIDENCE_MATCH_BYTES,
    URLEvidenceError,
    register_url_evidence_tool,
    url_evidence_handler,
)


@pytest.mark.asyncio
async def test_url_evidence_preserves_unicode_spans_and_normalizes_hosts() -> None:
    """URL evidence retains source locations for IDNA and IPv6 URLs."""
    text = (
        "검토 https://例え.テスト/path?q=1#frag, 그리고 (https://[2001:db8::1]/docs)."
    )

    result = await registry.invoke_tool("url_evidence_extractor", {"text": text})

    assert main.app is not None
    assert result["match_count"] == 2
    assert result["unique_match_count"] == 2
    first, second = result["matches"]
    assert first["raw_value"] == "https://例え.テスト/path?q=1#frag"
    assert first["source_start"] == text.index(first["raw_value"])
    assert first["source_end"] == first["source_start"] + len(first["raw_value"])
    assert first["host_value"].startswith("xn--")
    assert second["raw_value"] == "https://[2001:db8::1]/docs"
    assert second["host_value"] == "2001:db8::1"
    assert second["validation_status"] == "valid"


@pytest.mark.asyncio
async def test_url_evidence_validates_dns_and_ip_host_syntax_without_network() -> None:
    """Accept enterprise/IDNA hosts while rejecting malformed DNS/IP syntax."""
    text = (
        "single http://intranet/health "
        "uppercase HTTPS://EXAMPLE.COM/path "
        "idna https://예시.한국/경로 "
        "malformed-dots https://example..com/path "
        "malformed-leading-hyphen https://-example.com/path "
        "malformed-trailing-hyphen https://example-.com/path "
        "malformed-underscore https://example_test.com/path "
        "malformed-percent https://example%zz.com/path "
        "malformed-ip https://999.999.999.999/path"
    )

    result = await registry.invoke_tool("url_evidence_extractor", {"text": text})
    by_raw = {match["raw_value"]: match for match in result["matches"]}

    assert by_raw["http://intranet/health"]["validation_status"] == "valid"
    assert by_raw["HTTPS://EXAMPLE.COM/path"]["validation_status"] == "valid"
    assert by_raw["HTTPS://EXAMPLE.COM/path"]["normalized_value"] == (
        "https://example.com/path"
    )
    assert by_raw["https://예시.한국/경로"]["validation_status"] == "valid"
    assert by_raw["https://예시.한국/경로"]["host_value"].startswith("xn--")

    malformed = (
        "https://example..com/path",
        "https://-example.com/path",
        "https://example-.com/path",
        "https://example_test.com/path",
        "https://example%zz.com/path",
        "https://999.999.999.999/path",
    )
    for raw_value in malformed:
        assert by_raw[raw_value]["validation_status"] == "rejected_malformed_uri"
        assert "malformed_uri" in by_raw[raw_value]["warning_codes"]


@pytest.mark.asyncio
async def test_url_evidence_deduplicates_values_without_losing_occurrences() -> None:
    """Repeated URLs remain separate span records but have one unique value."""
    text = "https://example.com/a and https://example.com/a"

    result = await registry.invoke_tool("url_evidence_extractor", {"text": text})

    assert result["match_count"] == 2
    assert result["unique_match_count"] == 1
    assert len(result["unique_normalized_values"]) == 1
    assert result["matches"][0]["source_start"] != result["matches"][1]["source_start"]


@pytest.mark.asyncio
async def test_url_evidence_marks_userinfo_and_invalid_percent_encoding() -> None:
    """Dangerous URL forms are reported as rejected evidence, never fetched."""
    result = await registry.invoke_tool(
        "url_evidence_extractor",
        {"text": "https://user:pass@example.com/a https://example.com/%ZZ"},
    )

    assert result["matches"][0]["contains_userinfo"] is True
    assert result["matches"][0]["validation_status"] == "rejected_userinfo"
    assert result["matches"][1]["validation_status"] == (
        "rejected_invalid_percent_encoding"
    )
    assert "extracted_urls_are_never_fetched" in result["warning_codes"]


@pytest.mark.asyncio
async def test_url_evidence_does_not_treat_query_at_as_userinfo() -> None:
    """An at-sign in query data is not URL authority userinfo."""
    result = await registry.invoke_tool(
        "url_evidence_extractor",
        {"text": "https://example.com?to=person@example.com#contact"},
    )

    match = result["matches"][0]
    assert match["contains_userinfo"] is False
    assert match["validation_status"] == "valid"
    assert match["warning_codes"] == []


@pytest.mark.asyncio
async def test_url_evidence_fails_closed_at_input_and_match_bounds() -> None:
    """Large inputs and excessive match counts cannot become unbounded work."""
    with pytest.raises(URLEvidenceError) as input_error:
        await registry.invoke_tool(
            "url_evidence_extractor",
            {"text": "x" * (MAX_URL_EVIDENCE_BYTES + 1)},
        )
    assert input_error.value.error_code == "url_evidence_input_too_large"

    text = " ".join("https://example.com" for _ in range(129))
    with pytest.raises(URLEvidenceError) as match_error:
        await registry.invoke_tool("url_evidence_extractor", {"text": text})
    assert match_error.value.error_code == "url_evidence_match_limit_exceeded"


@pytest.mark.asyncio
async def test_url_evidence_checks_raw_candidate_before_trimming() -> None:
    """A punctuation-trimmed URL still obeys the raw per-match byte ceiling."""
    prefix = "https://example.com/"
    raw_candidate = prefix + ("a" * (MAX_URL_EVIDENCE_MATCH_BYTES - len(prefix))) + "."

    with pytest.raises(URLEvidenceError) as error:
        await registry.invoke_tool("url_evidence_extractor", {"text": raw_candidate})

    assert len(raw_candidate.encode("utf-8")) == MAX_URL_EVIDENCE_MATCH_BYTES + 1
    assert error.value.error_code == "url_evidence_match_too_large"


@pytest.mark.asyncio
async def test_url_evidence_request_shape_errors_have_stable_codes() -> None:
    """Direct and HTTP-style calls expose deterministic missing/type failures."""
    with pytest.raises(URLEvidenceError) as missing_error:
        url_evidence_handler({})
    assert missing_error.value.error_code == "url_evidence_text_required"

    missing_response = await execute_tool(
        "url_evidence_extractor", ExecuteRequest(parameters={})
    )
    assert missing_response.error_code == "url_evidence_text_required"

    invalid_response = await execute_tool(
        "url_evidence_extractor", ExecuteRequest(parameters={"text": 123})
    )
    assert invalid_response.error_code == "url_evidence_invalid_text"


@pytest.mark.asyncio
async def test_url_evidence_accepts_twenty_megabyte_working_text() -> None:
    """Large attachment-sized text remains inspectable without network access."""
    text = "x" * (20 * 1024 * 1024)
    result = await registry.invoke_tool("url_evidence_extractor", {"text": text})
    assert result["match_count"] == 0
    assert result["unique_normalized_values"] == []


def test_url_evidence_registration_is_idempotent() -> None:
    """Repeated bootstrap registration keeps the original catalog object."""
    original = registry.get("url_evidence_extractor")
    assert original is not None
    register_url_evidence_tool()
    assert registry.get("url_evidence_extractor") is original
