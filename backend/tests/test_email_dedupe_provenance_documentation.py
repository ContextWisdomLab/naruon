from pathlib import Path


def test_email_dedupe_provenance_runbook_matches_contract():
    runbook = (
        Path(__file__).parents[2]
        / "docs"
        / "operations"
        / "email-dedupe-provenance.md"
    ).read_text()

    for value in (
        "date_evidence",
        "message_id_evidence",
        "dedupe_review_required",
        "embedded_message_id",
        "raw_content_fallback_message_id",
        "metadata_fingerprint",
        "email_metadata_provenance_1086",
    ):
        assert value in runbook
