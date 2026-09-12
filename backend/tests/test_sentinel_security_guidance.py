"""Governance regression for evidence-backed Sentinel filename findings."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SENTINEL_GUIDANCE = REPOSITORY_ROOT / ".jules" / "sentinel.md"
EMAIL_UPLOAD_SECTION_MARKER = "## 2024-06-25 - "


def _email_upload_lesson() -> str:
    """Return the 2024-06-25 email-upload lesson without adjacent entries."""
    guidance = SENTINEL_GUIDANCE.read_text(encoding="utf-8")
    _, marker, remainder = guidance.partition(EMAIL_UPLOAD_SECTION_MARKER)
    assert marker, "Sentinel email-upload lesson must remain traceable by date"
    section, _, _ = remainder.partition("\n## ")
    return section


def _normalized_email_upload_lesson() -> str:
    """Normalize whitespace and case so policy assertions survive Markdown wrapping."""
    return " ".join(_email_upload_lesson().lower().split())


def test_sentinel_filename_findings_require_a_reproduced_sink() -> None:
    """Require the complete causal-evidence rule, not disconnected security keywords."""
    lesson = _normalized_email_upload_lesson()

    assert "an embedded extension alone is not evidence of executable upload" in lesson
    assert (
        "before classifying a filename finding as high/critical, reproduce a causal "
        "consumer or sink path" in lesson
    )
    assert (
        "such as execution, interpreter handoff, mime/content-type confusion, suffix "
        "stripping or reinterpretation, unsafe shell/process use" in lesson
    )
    assert (
        "do not introduce an embedded-extension denylist unless a sink-backed red "
        "reproduces execution or reinterpretation through the actual consumer path" in lesson
    )


def test_sentinel_does_not_prescribe_an_arbitrary_embedded_extension_denylist() -> None:
    """Keep filename controls at canonical path, terminal suffix, and real sink boundaries."""
    lesson = _normalized_email_upload_lesson()

    assert 'split(".")' not in lesson
    assert "reject if any segment matches" not in lesson
    assert "preserve canonical path handling" in lesson
    assert "bounded decoding" in lesson
    assert "control-character rejection" in lesson
    assert "terminal suffix validation" in lesson
    assert "parser-only handling" in lesson


def test_sentinel_retains_explicit_smtp_crlf_rejection() -> None:
    """Require one complete SMTP rejection clause rather than disconnected keywords."""
    lesson = _normalized_email_upload_lesson()

    assert (
        "for smtp headers, use @field_validator with explicit mode=\"before\" checks that "
        "reject chr(10) and chr(13) across user-controlled fields to, subject, in_reply_to, "
        "and references" in lesson
    )
