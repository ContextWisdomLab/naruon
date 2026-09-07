"""Contract tests for bounded email and phone redaction."""

import pytest

import main
from api.contact_data_redactor import (
    ContactRedactionError,
    MAX_CONTACT_REDACTION_BYTES,
    register_contact_data_redactor,
)
from api.tools import ExecuteRequest, execute_tool, registry


@pytest.mark.asyncio
async def test_contact_redactor_returns_safe_placeholders_and_span_evidence() -> None:
    """Supported Korean and E.164-compatible contacts are replaced deterministically."""
    text = (
        "한국 담당자 alice@example.com, 010-1234-5678, "
        "+1 (415) 555-2671에게 연락하세요."
    )

    result = await registry.invoke_tool("contact_data_redactor", {"text": text})

    assert main.app is not None
    assert result["match_counts"] == {"email": 1, "phone": 2}
    assert "alice@example.com" not in result["redacted_text"]
    assert "010-1234-5678" not in result["redacted_text"]
    assert "+1 (415) 555-2671" not in result["redacted_text"]
    assert result["redacted_text"].count("[EMAIL_1]") == 1
    assert result["redacted_text"].count("[PHONE_1]") == 1
    assert result["redacted_text"].count("[PHONE_2]") == 1
    for match in result["matches"]:
        assert (
            result["redacted_text"][
                match["replacement_start"] : match["replacement_end"]
            ]
            == match["placeholder"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("separator", [" ", "\n"])
async def test_contact_redactor_redacts_adjacent_phone_numbers(
    separator: str,
) -> None:
    """Phone lists separated only by whitespace redact every supported number."""
    result = await registry.invoke_tool(
        "contact_data_redactor",
        {"text": f"010-1234-5678{separator}010-8765-4321"},
    )

    assert result["match_counts"] == {"email": 0, "phone": 2}
    assert "010-1234-5678" not in result["redacted_text"]
    assert "010-8765-4321" not in result["redacted_text"]


@pytest.mark.asyncio
async def test_contact_redactor_finds_phone_after_date_prefix() -> None:
    """An invalid date prefix must not hide a supported phone after whitespace."""
    result = await registry.invoke_tool(
        "contact_data_redactor",
        {"text": "2026-08-21 010-1234-5678"},
    )

    assert result["match_counts"] == {"email": 0, "phone": 1}
    assert "2026-08-21" in result["redacted_text"]
    assert "010-1234-5678" not in result["redacted_text"]


@pytest.mark.asyncio
async def test_contact_redactor_reuses_placeholder_for_repeated_contact() -> None:
    """Repeated contact values preserve entity distinction without exposing values."""
    result = await registry.invoke_tool(
        "contact_data_redactor",
        {"text": "alice@example.com copied to alice@example.com"},
    )

    assert result["match_counts"] == {"email": 2, "phone": 0}
    assert result["redacted_text"].count("[EMAIL_1]") == 2
    assert len({match["placeholder"] for match in result["matches"]}) == 1


@pytest.mark.asyncio
async def test_contact_redactor_does_not_claim_to_remove_unsupported_pii() -> None:
    """Unsupported classes remain visible and the warning tells the next action."""
    result = await registry.invoke_tool(
        "contact_data_redactor",
        {"text": "주민번호 900101-1234567 및 홍길동@example.com"},
    )

    assert "900101-1234567" in result["redacted_text"]
    assert "unsupported_pii_classes_not_removed" in result["warnings"]
    assert "ascii_email_and_korean_e164_phone_scope_only" in result["warnings"]


@pytest.mark.asyncio
async def test_contact_redactor_fails_closed_at_input_bound() -> None:
    """Oversized input is rejected before detector work begins."""
    with pytest.raises(ContactRedactionError) as error:
        await registry.invoke_tool(
            "contact_data_redactor",
            {"text": "x" * (MAX_CONTACT_REDACTION_BYTES + 1)},
        )
    assert error.value.error_code == "contact_redaction_input_too_large"


@pytest.mark.asyncio
async def test_contact_redactor_accepts_twenty_megabyte_working_text() -> None:
    """Large attachment-sized text remains usable by the optional tool."""
    text = "x" * (20 * 1024 * 1024)
    result = await registry.invoke_tool("contact_data_redactor", {"text": text})
    assert result["redacted_text"] == text
    assert result["match_counts"] == {"email": 0, "phone": 0}


@pytest.mark.asyncio
async def test_tool_api_preserves_deterministic_redaction_error_code() -> None:
    """The shared execution envelope exposes the handler's stable failure code."""
    response = await execute_tool(
        "contact_data_redactor",
        ExecuteRequest(parameters={"text": "x" * (MAX_CONTACT_REDACTION_BYTES + 1)}),
    )

    assert response.status == "failed"
    assert response.error_code == "contact_redaction_input_too_large"


def test_contact_redactor_registration_is_idempotent() -> None:
    """Repeated bootstrap registration keeps the original catalog object."""
    original = registry.get("contact_data_redactor")
    assert original is not None
    register_contact_data_redactor()
    assert registry.get("contact_data_redactor") is original
