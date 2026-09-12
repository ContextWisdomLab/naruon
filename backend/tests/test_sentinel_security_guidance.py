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


def test_sentinel_filename_findings_require_a_reproduced_sink() -> None:
    """Do not classify embedded filename segments as exploits without a causal sink."""
    lesson = _email_upload_lesson().lower()

    assert "embedded extension alone" in lesson
    assert "consumer" in lesson or "sink" in lesson
    assert "execution" in lesson
    assert "mime" in lesson
    assert "suffix stripping" in lesson
    assert "shell" in lesson or "process" in lesson
    assert "high/critical" in lesson


def test_sentinel_does_not_prescribe_an_arbitrary_embedded_extension_denylist() -> None:
    """Keep filename controls at canonical path, terminal suffix, and real sink boundaries."""
    lesson = _email_upload_lesson().lower()

    assert 'split(".")' not in lesson
    assert "reject if any segment matches" not in lesson
    assert "terminal suffix" in lesson
    assert "canonical" in lesson
    assert "control" in lesson
    assert "parser" in lesson


def test_sentinel_retains_explicit_smtp_crlf_rejection() -> None:
    """Correcting the filename false positive must not weaken real header injection controls."""
    lesson = _email_upload_lesson()

    assert 'chr(10)' in lesson
    assert 'chr(13)' in lesson
    assert 'mode="before"' in lesson
