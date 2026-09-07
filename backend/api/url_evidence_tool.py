"""Extract bounded, source-grounded HTTP(S) URL evidence without fetching it."""

from __future__ import annotations

import re
from ipaddress import ip_address
from typing import Any
from urllib.parse import SplitResult, urlsplit

from api.tools import ToolInfo, registry

# Match the signed import working ceiling; candidate and match-count bounds
# still prevent unbounded URL evidence work inside a large document.
MAX_URL_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_URL_EVIDENCE_MATCHES = 128
MAX_URL_EVIDENCE_MATCH_BYTES = 2_048
URL_EVIDENCE_DETECTOR_VERSION = "url_evidence_v1"

_CANDIDATE_PATTERN = re.compile(r"(?<![\w@])https?://[^\s<>\"']+", re.IGNORECASE)
_PERCENT_ESCAPE_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DNS_LABEL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_IPISH_HOST_PATTERN = re.compile(r"[0-9.]+")
_TERMINAL_PUNCTUATION = frozenset(".,;:!?。！，；：！？")
_CLOSING_BRACKETS = {")": "(", "]": "[", "}": "{"}


class URLEvidenceError(ValueError):
    """Expected bounded URL-evidence failure with a stable machine code."""

    def __init__(self, message: str, *, error_code: str) -> None:
        """Initialize a customer-safe validation failure."""
        super().__init__(message)
        self.error_code = error_code


def _bounded_text(text: str) -> None:
    """Reject text that cannot be processed within the tool's byte budget."""
    try:
        byte_length = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise URLEvidenceError(
            "Text must contain valid Unicode scalar values",
            error_code="url_evidence_invalid_text",
        ) from exc
    if byte_length > MAX_URL_EVIDENCE_BYTES:
        raise URLEvidenceError(
            "URL evidence input exceeds the 64 MiB working ceiling",
            error_code="url_evidence_input_too_large",
        )


def _trim_candidate(candidate: str) -> str:
    """Remove prose punctuation while retaining balanced URL punctuation."""
    trimmed = candidate
    changed = True
    while trimmed and changed:
        changed = False
        if trimmed[-1] in _TERMINAL_PUNCTUATION:
            trimmed = trimmed[:-1]
            changed = True
            continue
        opener = _CLOSING_BRACKETS.get(trimmed[-1])
        if opener is not None and trimmed.count(trimmed[-1]) > trimmed.count(opener):
            trimmed = trimmed[:-1]
            changed = True
    return trimmed


def _normal_host(host: str) -> str:
    """Validate and normalize an IP literal or IDNA DNS hostname."""
    if _IPISH_HOST_PATTERN.fullmatch(host) or ":" in host:
        return str(ip_address(host))

    idna_host = host.encode("idna").decode("ascii").lower()
    has_root_dot = idna_host.endswith(".")
    labels_host = idna_host[:-1] if has_root_dot else idna_host
    if not labels_host:
        raise ValueError("missing DNS labels")
    if len(idna_host) > (254 if has_root_dot else 253):
        raise ValueError("hostname exceeds DNS length limit")
    if not all(
        _DNS_LABEL_PATTERN.fullmatch(label) for label in labels_host.split(".")
    ):
        raise ValueError("invalid DNS label")
    return idna_host


def _normalized_url(parsed: SplitResult, host: str, port: int | None) -> str:
    """Build a deterministic URL with lowercase scheme and normalized host."""
    normalized_host = f"[{host}]" if ":" in host else host
    host_with_port = normalized_host if port is None else f"{normalized_host}:{port}"
    userinfo = ""
    if "@" in parsed.netloc:
        userinfo = f"{parsed.netloc.rsplit('@', 1)[0]}@"
    return parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=f"{userinfo}{host_with_port}",
    ).geturl()


def _evidence_record(candidate: str, source_start: int) -> dict[str, Any]:
    """Parse one delimited candidate and return safe classification evidence."""
    warning_codes: list[str] = []
    parsed: SplitResult | None = None
    host_value = ""
    normalized_value = candidate
    contains_userinfo = False
    validation_status = "valid"

    try:
        parsed = urlsplit(candidate)
        host = parsed.hostname
        if not host:
            raise ValueError("missing host")
        port = parsed.port
        host_value = _normal_host(host)
        normalized_value = _normalized_url(parsed, host_value, port)
    except (UnicodeError, ValueError):
        validation_status = "rejected_malformed_uri"
        warning_codes.append("malformed_uri")
        if parsed is not None:
            contains_userinfo = "@" in parsed.netloc
    else:
        contains_userinfo = "@" in parsed.netloc
        if contains_userinfo:
            validation_status = "rejected_userinfo"
            warning_codes.append("userinfo_present")
        if _PERCENT_ESCAPE_PATTERN.search(candidate):
            validation_status = "rejected_invalid_percent_encoding"
            warning_codes.append("invalid_percent_encoding")

    return {
        "raw_value": candidate,
        "normalized_value": normalized_value,
        "source_start": source_start,
        "source_end": source_start + len(candidate),
        "scheme_code": parsed.scheme.lower() if parsed is not None else "",
        "host_value": host_value,
        "contains_userinfo": contains_userinfo,
        "validation_status": validation_status,
        "warning_codes": warning_codes,
        "detector_version": URL_EVIDENCE_DETECTOR_VERSION,
    }


def url_evidence_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Extract deterministic URL evidence and never perform a network request."""
    if "text" not in params:
        raise URLEvidenceError(
            "Text is required for URL evidence extraction",
            error_code="url_evidence_text_required",
        )
    text = params["text"]
    if not isinstance(text, str):
        raise URLEvidenceError(
            "Text must be a string",
            error_code="url_evidence_invalid_text",
        )
    _bounded_text(text)
    matches: list[dict[str, Any]] = []

    for candidate_match in _CANDIDATE_PATTERN.finditer(text):
        raw_candidate = candidate_match.group(0)
        if len(raw_candidate.encode("utf-8")) > MAX_URL_EVIDENCE_MATCH_BYTES:
            raise URLEvidenceError(
                "A URL candidate exceeds the per-match limit",
                error_code="url_evidence_match_too_large",
            )
        candidate = _trim_candidate(raw_candidate)
        if not candidate:
            continue
        matches.append(_evidence_record(candidate, candidate_match.start()))
        if len(matches) > MAX_URL_EVIDENCE_MATCHES:
            raise URLEvidenceError(
                "URL evidence match count exceeds the bounded limit",
                error_code="url_evidence_match_limit_exceeded",
            )

    unique_values: list[str] = []
    seen_values: set[str] = set()
    warning_codes = ["extracted_urls_are_never_fetched"]
    for match in matches:
        normalized_value = match["normalized_value"]
        if normalized_value not in seen_values:
            seen_values.add(normalized_value)
            unique_values.append(normalized_value)
        warning_codes.extend(match["warning_codes"])

    return {
        "matches": matches,
        "unique_normalized_values": unique_values,
        "match_count": len(matches),
        "unique_match_count": len(unique_values),
        "warning_codes": list(dict.fromkeys(warning_codes)),
        "detector_version": URL_EVIDENCE_DETECTOR_VERSION,
    }


def register_url_evidence_tool() -> None:
    """Register the URL evidence tool once in the existing tool catalog."""
    if registry.get("url_evidence_extractor") is not None:
        return
    registry.register(
        ToolInfo(
            code="url_evidence_extractor",
            name="URL evidence extractor",
            description=(
                "Extract bounded HTTP(S) URL evidence with source spans; URLs "
                "are parsed but never fetched."
            ),
            category="데이터 위생",
            parameters={"text": "string"},
        ),
        url_evidence_handler,
    )
