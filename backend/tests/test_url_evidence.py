from services.url_evidence import extract_url_evidence


def test_extracts_normalizes_and_preserves_unicode_offsets():
    result = extract_url_evidence("안내: HTTPS://Example.com/a?q=1#x.")

    assert len(result) == 1
    evidence = result[0]
    assert evidence.raw_value == "HTTPS://Example.com/a?q=1#x"
    assert evidence.normalized_value == "https://example.com/a?q=1#x"
    assert evidence.source_start == 4
    assert evidence.source_end == 31
    assert evidence.source_locations == ((4, 31),)
    assert evidence.validation_status == "valid"


def test_deduplicates_normalized_urls_without_losing_locations():
    result = extract_url_evidence("https://example.com https://EXAMPLE.com")

    assert len(result) == 1
    assert result[0].source_locations == ((0, 19), (20, 39))


def test_marks_userinfo_without_treating_it_as_safe():
    result = extract_url_evidence("https://user:secret@example.com/path")

    assert result[0].normalized_value is None
    assert result[0].contains_userinfo is True
    assert result[0].validation_status == "invalid"
    assert "userinfo_present" in result[0].warning_codes


def test_handles_parentheses_and_limits_input_and_matches():
    result = extract_url_evidence(
        "(https://example.com/a), https://two.example/x https://three.example/y",
        max_matches=2,
    )

    assert [item.normalized_value for item in result] == [
        "https://example.com/a",
        "https://two.example/x",
    ]


def test_malformed_authority_returns_invalid_evidence_instead_of_raising():
    result = extract_url_evidence("https://[not-an-ip https://[not-an-ip")

    assert result[0].validation_status == "invalid"
    assert result[0].normalized_value is None
    assert result[0].warning_codes == ("invalid_host",)
    assert len(result[0].source_locations) == 2
