"""Bounded redaction for the explicitly supported contact-data classes.

This module is not a general PII anonymizer. It detects email addresses and
telephone numbers only; unsupported personal-data classes remain untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DETECTOR_VERSION = "contact-data-redactor.v1"
_DEFAULT_MAX_INPUT_CHARS = 1_048_576
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.!#$%&'*+/=?^`{|}~-])"
    r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+"
    r"(?![\w.!#$%&'*+/=?^`{|}~-])",
    flags=re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{5,}\d)(?!\w)")
_UNSUPPORTED_ID_PATTERN = re.compile(r"^\d{6}-\d{7}$")


@dataclass(frozen=True, slots=True)
class ContactMatch:
    """A redaction span without retaining the detected personal value."""

    data_class: str
    source_start: int
    source_end: int
    replacement_start: int
    replacement_end: int
    detector_version: str = DETECTOR_VERSION


@dataclass(frozen=True, slots=True)
class ContactRedactionResult:
    """Redacted text and auditable, value-free detector output."""

    redacted_text: str
    matches: tuple[ContactMatch, ...]
    match_counts: dict[str, int]
    warnings: tuple[str, ...]


def _phone_is_supported(value: str) -> bool:
    if _UNSUPPORTED_ID_PATTERN.fullmatch(value.strip()):
        return False
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15:
        return False
    # International candidates must carry an explicit country prefix. This
    # avoids treating arbitrary long numbers in prose as contact data.
    if value.lstrip().startswith("+"):
        return len(digits) >= 8 and len(digits) <= 15

    # Korean mobile, landline, and business/service numbers. Separators are
    # permitted by the candidate regex, but the digit structure stays strict.
    if digits.startswith("01"):
        return len(digits) in {10, 11}
    if digits.startswith("02"):
        return len(digits) in {9, 10}
    if digits.startswith("0") and len(digits) in {10, 11}:
        return True
    return digits[:2] in {"15", "16", "18"} and len(digits) == 8


def _candidate_spans(text: str) -> list[tuple[int, int, str]]:
    candidates = [(match.start(), match.end(), "email") for match in _EMAIL_PATTERN.finditer(text)]
    candidates.extend(
        (match.start(), match.end(), "phone")
        for match in _PHONE_PATTERN.finditer(text)
        if _phone_is_supported(match.group(0))
    )
    # Email wins when a malformed phone-like candidate overlaps it. The stable
    # sort also makes output deterministic for equal boundaries.
    candidates.sort(key=lambda item: (item[0], item[1], 0 if item[2] == "email" else 1))
    selected: list[tuple[int, int, str]] = []
    for candidate in candidates:
        if selected and candidate[0] < selected[-1][1]:
            continue
        selected.append(candidate)
    return selected


def redact_contact_data(
    text: str,
    *,
    placeholders: bool = False,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
) -> ContactRedactionResult:
    """Redact supported email and telephone forms without retaining values."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if max_input_chars <= 0:
        raise ValueError("max_input_chars must be positive")
    if len(text) > max_input_chars:
        raise ValueError("input exceeds the contact redaction limit")

    output: list[str] = []
    matches: list[ContactMatch] = []
    counts = {"email": 0, "phone": 0}
    source_cursor = 0
    output_cursor = 0
    for start, end, data_class in _candidate_spans(text):
        output.append(text[source_cursor:start])
        output_cursor += start - source_cursor
        counts[data_class] += 1
        replacement = (
            f"[{data_class.upper()}_{counts[data_class]}]"
            if placeholders
            else f"[REDACTED_{data_class.upper()}]"
        )
        replacement_start = output_cursor
        output.append(replacement)
        output_cursor += len(replacement)
        matches.append(
            ContactMatch(data_class, start, end, replacement_start, output_cursor)
        )
        source_cursor = end
    output.append(text[source_cursor:])
    return ContactRedactionResult(
        redacted_text="".join(output),
        matches=tuple(matches),
        match_counts={key: value for key, value in counts.items() if value},
        warnings=("unsupported_pii_classes_not_removed",),
    )


__all__ = ["ContactMatch", "ContactRedactionResult", "DETECTOR_VERSION", "redact_contact_data"]
