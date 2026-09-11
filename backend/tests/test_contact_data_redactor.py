import pytest

from services.contact_data_redactor import DETECTOR_VERSION, redact_contact_data


def test_redacts_email_and_korean_phone_with_output_spans():
    source = "문의: user@example.com, 010-1234-5678"
    result = redact_contact_data(source)

    assert result.redacted_text == "문의: [REDACTED_EMAIL], [REDACTED_PHONE]"
    assert result.match_counts == {"email": 1, "phone": 1}
    assert [match.data_class for match in result.matches] == ["email", "phone"]
    assert all(match.detector_version == DETECTOR_VERSION for match in result.matches)
    for match in result.matches:
        assert source[match.source_start : match.source_end] not in result.redacted_text
        assert result.redacted_text[match.replacement_start : match.replacement_end].startswith("[REDACTED_")


def test_spans_round_trip_with_unicode_prefix_and_multiple_placeholders():
    source = "안내 📬 first@example.com 및 +82 10 1234 5678"
    result = redact_contact_data(source, placeholders=True)

    assert [
        source[match.source_start : match.source_end] for match in result.matches
    ] == ["first@example.com", "+82 10 1234 5678"]
    assert [
        result.redacted_text[match.replacement_start : match.replacement_end]
        for match in result.matches
    ] == ["[EMAIL_1]", "[PHONE_1]"]
    assert result.redacted_text == "안내 📬 [EMAIL_1] 및 [PHONE_1]"


def test_overlapping_phone_candidate_does_not_consume_email_like_suffix():
    result = redact_contact_data("contact 01012345678@example.com")

    assert [match.data_class for match in result.matches] == ["phone"]
    assert result.redacted_text == "contact [REDACTED_PHONE]@example.com"


def test_placeholders_are_deterministic_and_do_not_expose_values():
    result = redact_contact_data(
        "a@example.com a@example.com +82 10 1234 5678", placeholders=True
    )

    assert result.redacted_text == "[EMAIL_1] [EMAIL_2] [PHONE_1]"
    assert "a@example.com" not in result.redacted_text
    assert "+82" not in result.redacted_text


def test_avoids_phone_near_misses_and_warns_about_unsupported_classes():
    result = redact_contact_data(
        "order 1234567, 주민번호 900101-1234567, name Alice"
    )

    assert result.redacted_text == "order 1234567, 주민번호 900101-1234567, name Alice"
    assert result.matches == ()
    assert result.warnings == ("unsupported_pii_classes_not_removed",)


def test_supports_e164_and_korean_landline_and_service_forms():
    result = redact_contact_data("+1 (415) 555-2671 / 02-1234-5678 / 1588-1234")

    assert result.redacted_text == (
        "[REDACTED_PHONE] / [REDACTED_PHONE] / [REDACTED_PHONE]"
    )
    assert result.match_counts == {"phone": 3}


def test_rejects_non_string_and_oversized_input():
    with pytest.raises(TypeError):
        redact_contact_data(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        redact_contact_data("x", max_input_chars=0)
    with pytest.raises(ValueError):
        redact_contact_data("abcd", max_input_chars=3)
