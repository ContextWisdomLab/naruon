"""Regression coverage for ZIP signatures without local file headers."""

from services.attachment_parser import (
    CONTENT_TYPE_MISMATCH_QUARANTINED_STATUS,
    parse_email_attachment,
)


def test_empty_zip_disguised_as_text_is_quarantined() -> None:
    """An empty ZIP starts with EOCD, not the usual local-file-header magic."""
    empty_zip = b"PK\x05\x06" + (b"\x00" * 18)

    result = parse_email_attachment(
        filename="meeting-notes.txt",
        content_type="text/plain",
        raw_content=empty_zip,
    )

    assert result.parse_status == CONTENT_TYPE_MISMATCH_QUARANTINED_STATUS
    assert result.parse_error_code == CONTENT_TYPE_MISMATCH_QUARANTINED_STATUS
    assert result.parse_content_type == "application/zip"
    assert result.content_type == "text/plain"
