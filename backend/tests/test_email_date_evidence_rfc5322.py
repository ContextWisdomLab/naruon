import datetime

from services.email_import_service import _email_fingerprint
from services.email_parser import parse_eml_bytes


def _message(date_value: str) -> bytes:
    return (
        "From: sender@example.com\r\n"
        "To: owner@example.com\r\n"
        "Subject: provenance boundary\r\n"
        f"Date: {date_value}\r\n"
        "Message-ID: <provenance@example.com>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "same body\r\n"
    ).encode("utf-8")


def test_zone_less_date_is_not_strong_source_evidence():
    parsed = parse_eml_bytes(_message("Fri, 11 Sep 2026 12:00:00"))

    assert parsed["date_evidence"] == "invalid"
    assert parsed["date"].tzinfo is not None
    assert _email_fingerprint(parsed, parsed["date"]) is None


def test_rfc5322_minus_0000_remains_valid_utc_instant_with_unknown_local_zone():
    parsed = parse_eml_bytes(_message("Fri, 11 Sep 2026 12:00:00 -0000"))

    assert parsed["date_evidence"] == "parsed"
    assert parsed["date"].utcoffset() == datetime.timedelta(0)
    assert _email_fingerprint(parsed, parsed["date"]) is not None
