"""Bounded email and phone redaction with source-span evidence."""

from __future__ import annotations

import re
from typing import Any

from api.tools import ToolInfo, registry

# Match the signed import working ceiling so large email/document text is not
# rejected by this optional working-copy tool at an unrelated 1 MiB boundary.
MAX_CONTACT_REDACTION_BYTES = 64 * 1024 * 1024
CONTACT_REDACTION_DETECTOR_VERSION = "contact_data_v1"

_EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
)
_PHONE_CANDIDATE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])\+?[0-9][0-9()\s.-]{6,24}[0-9](?![A-Za-z0-9_])"
)
_ADJACENT_PHONE_BOUNDARY = re.compile(r"(?<=\d)\s+(?=\+?\d)")
_DATE_PATTERN = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


class ContactRedactionError(ValueError):
    """Expected bounded redaction failure with a stable machine code."""

    def __init__(self, message: str, *, error_code: str) -> None:
        """Initialize a customer-safe validation failure."""
        super().__init__(message)
        self.error_code = error_code


def _bounded_text(text: str) -> None:
    """Reject text that cannot be processed within the byte budget."""
    try:
        byte_length = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContactRedactionError(
            "Text must contain valid Unicode scalar values",
            error_code="contact_redaction_invalid_text",
        ) from exc
    if byte_length > MAX_CONTACT_REDACTION_BYTES:
        raise ContactRedactionError(
            "Contact redaction input exceeds the 64 MiB working ceiling",
            error_code="contact_redaction_input_too_large",
        )


def _valid_phone(candidate: str) -> bool:
    """Apply a conservative Korean/E.164-compatible phone policy."""
    stripped = candidate.strip()
    digits = re.sub(r"\D", "", stripped)
    if not 8 <= len(digits) <= 15:
        return False
    if _DATE_PATTERN.fullmatch(stripped):
        return False
    if "." in stripped and len(stripped.split(".")) == 4:
        return False
    if stripped.startswith("+"):
        return True
    if not digits.startswith("0"):
        return False
    return True


def _phone_candidates(text: str) -> list[tuple[int, int, str]]:
    """Return valid phones, recovering adjacent whitespace-separated numbers."""
    candidates: list[tuple[int, int, str]] = []
    search_start = 0
    while match := _PHONE_CANDIDATE_PATTERN.search(text, search_start):
        candidate = match.group(0)
        if _valid_phone(candidate):
            candidates.append((match.start(), match.end(), candidate))
            search_start = match.end()
            continue
        restart_after_boundary: int | None = None
        for boundary in _ADJACENT_PHONE_BOUNDARY.finditer(candidate):
            if restart_after_boundary is None:
                restart_after_boundary = match.start() + boundary.end()
            first_phone = candidate[: boundary.start()]
            if _valid_phone(first_phone):
                first_end = match.start() + boundary.start()
                candidates.append((match.start(), first_end, first_phone))
                search_start = match.start() + boundary.end()
                break
        else:
            search_start = restart_after_boundary or match.end()
    return candidates


def _contact_candidates(text: str) -> list[tuple[str, int, int, str]]:
    """Return non-overlapping email and phone candidates in source order."""
    candidates: list[tuple[str, int, int, str]] = [
        ("email", match.start(), match.end(), match.group(0))
        for match in _EMAIL_PATTERN.finditer(text)
    ]
    candidates.extend(
        ("phone", start, end, value)
        for start, end, value in _phone_candidates(text)
    )
    candidates.sort(
        key=lambda candidate: (
            candidate[1],
            0 if candidate[0] == "email" else 1,
            candidate[2],
        )
    )
    selected: list[tuple[str, int, int, str]] = []
    last_end = -1
    for candidate in candidates:
        if candidate[1] < last_end:
            continue
        selected.append(candidate)
        last_end = candidate[2]
    return selected


def _redaction_placeholder(
    category: str,
    source_value: str,
    placeholders: dict[tuple[str, str], str],
    next_numbers: dict[str, int],
) -> str:
    """Return a stable class-scoped placeholder without exposing source data."""
    key_value = (
        source_value.casefold()
        if category == "email"
        else re.sub(r"\D", "", source_value)
    )
    key = (category, key_value)
    if key not in placeholders:
        next_numbers[category] += 1
        placeholders[key] = f"[{category.upper()}_{next_numbers[category]}]"
    return placeholders[key]


def contact_data_redactor_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Redact supported contact classes and return immutable span evidence."""
    text = params["text"]
    _bounded_text(text)
    candidates = _contact_candidates(text)
    placeholders: dict[tuple[str, str], str] = {}
    next_numbers = {"email": 0, "phone": 0}
    output_parts: list[str] = []
    matches: list[dict[str, Any]] = []
    cursor = 0
    output_length = 0

    for category, start, end, source_value in candidates:
        prefix = text[cursor:start]
        output_parts.append(prefix)
        output_length += len(prefix)
        placeholder = _redaction_placeholder(
            category, source_value, placeholders, next_numbers
        )
        replacement_start = output_length
        output_parts.append(placeholder)
        output_length += len(placeholder)
        matches.append(
            {
                "class_code": category,
                "source_start": start,
                "source_end": end,
                "replacement_start": replacement_start,
                "replacement_end": output_length,
                "detector_version": CONTACT_REDACTION_DETECTOR_VERSION,
                "placeholder": placeholder,
            }
        )
        cursor = end

    suffix = text[cursor:]
    output_parts.append(suffix)
    redacted_text = "".join(output_parts)
    return {
        "redacted_text": redacted_text,
        "matches": matches,
        "match_counts": {
            "email": sum(match["class_code"] == "email" for match in matches),
            "phone": sum(match["class_code"] == "phone" for match in matches),
        },
        "detector_version": CONTACT_REDACTION_DETECTOR_VERSION,
        "warnings": [
            "unsupported_pii_classes_not_removed",
            "ascii_email_and_korean_e164_phone_scope_only",
            "output_is_not_anonymization_or_irreversible_de_identification",
        ],
    }


def register_contact_data_redactor() -> None:
    """Register the contact redactor once in the existing tool catalog."""
    if registry.get("contact_data_redactor") is not None:
        return
    registry.register(
        ToolInfo(
            code="contact_data_redactor",
            name="Contact data redactor",
            description=(
                "Redact supported email and Korean/E.164-compatible phone "
                "forms with source and replacement spans."
            ),
            category="데이터 위생",
            parameters={"text": "string"},
        ),
        contact_data_redactor_handler,
    )
