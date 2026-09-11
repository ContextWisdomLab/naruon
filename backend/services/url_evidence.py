"""Bounded, source-grounded extraction of absolute HTTP(S) URLs.

The extractor is deliberately local-only: it identifies and validates syntax,
but never resolves hosts or performs network requests. ``source_locations``
keeps every occurrence when normalized URLs are deduplicated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

_CANDIDATE = re.compile(r"(?i)https?://[^\s<>\"']+")
_TRAILING_PUNCTUATION = ".,;:!?"
_DEFAULT_MAX_INPUT_CHARS = 100_000
_DEFAULT_MAX_MATCHES = 100
_DEFAULT_MAX_MATCH_CHARS = 2_048


@dataclass(frozen=True, slots=True)
class UrlEvidence:
    """One normalized URL and every source location where it occurred."""

    raw_value: str
    normalized_value: str | None
    source_start: int
    source_end: int
    source_locations: tuple[tuple[int, int], ...]
    scheme_code: str
    host_value: str | None
    contains_userinfo: bool
    validation_status: str
    warning_codes: tuple[str, ...]


def _trim_candidate(candidate: str) -> str:
    value = candidate.rstrip(_TRAILING_PUNCTUATION)
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1]
    return value


def _parsed_host(parsed: SplitResult) -> str | None:
    try:
        return parsed.hostname
    except ValueError:
        return None


def _normalize(parsed: SplitResult, host: str) -> str:
    # Rebuild from parsed components so equivalent casing in the scheme/host
    # does not create separate evidence records. Other source spelling stays.
    username = parsed.username
    password = parsed.password
    userinfo = ""
    if username is not None:
        userinfo = username
        if password is not None:
            userinfo += f":{password}"
        userinfo += "@"
    authority_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (parsed.scheme.lower(), f"{userinfo}{authority_host}{port}", parsed.path, parsed.query, parsed.fragment)
    )


def extract_url_evidence(
    text: str,
    *,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
    max_matches: int = _DEFAULT_MAX_MATCHES,
    max_match_chars: int = _DEFAULT_MAX_MATCH_CHARS,
) -> tuple[UrlEvidence, ...]:
    """Extract bounded HTTP(S) evidence without fetching any URL.

    Repeated normalized URLs are represented once, with all source spans in
    ``source_locations``. Offsets use Python's Unicode string indexing.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if max_input_chars < 0 or max_matches < 0 or max_match_chars <= 0:
        raise ValueError("extraction limits must be non-negative and finite")
    if len(text) > max_input_chars:
        raise ValueError("input exceeds the URL evidence limit")

    records: dict[str, UrlEvidence] = {}
    for index, match in enumerate(_CANDIDATE.finditer(text)):
        if index >= max_matches:
            break
        raw_value = _trim_candidate(match.group(0))
        start = match.start()
        end = start + len(raw_value)
        warnings: list[str] = []
        if len(raw_value) > max_match_chars:
            raw_value = raw_value[:max_match_chars]
            end = start + len(raw_value)
            warnings.append("match_too_long")

        try:
            parsed = urlsplit(raw_value)
        except ValueError:
            key = f"invalid:{raw_value}"
            existing = records.get(key)
            if existing is not None:
                records[key] = UrlEvidence(
                    raw_value=existing.raw_value,
                    normalized_value=None,
                    source_start=existing.source_start,
                    source_end=existing.source_end,
                    source_locations=existing.source_locations + ((start, end),),
                    scheme_code=existing.scheme_code,
                    host_value=None,
                    contains_userinfo=existing.contains_userinfo,
                    validation_status="invalid",
                    warning_codes=existing.warning_codes,
                )
                continue
            records[key] = UrlEvidence(
                raw_value=raw_value,
                normalized_value=None,
                source_start=start,
                source_end=end,
                source_locations=((start, end),),
                scheme_code=raw_value.split(":", 1)[0].lower(),
                host_value=None,
                contains_userinfo="@" in raw_value,
                validation_status="invalid",
                warning_codes=("invalid_host",),
            )
            continue
        host = _parsed_host(parsed)
        contains_userinfo = parsed.username is not None or parsed.password is not None
        if contains_userinfo:
            warnings.append("userinfo_present")
        if parsed.scheme.lower() not in {"http", "https"}:
            warnings.append("unsupported_scheme")
        if host is None or not parsed.netloc:
            warnings.append("missing_host")
        try:
            parsed.port
        except ValueError:
            warnings.append("invalid_port")
        if "[" in parsed.netloc and "]" not in parsed.netloc:
            warnings.append("invalid_host")
        if not warnings:
            normalized = _normalize(parsed, host)
            status = "warning" if contains_userinfo else "valid"
        else:
            normalized = None
            status = "invalid"
        key = normalized or f"invalid:{raw_value}"
        existing = records.get(key)
        location = (start, end)
        if existing is not None:
            records[key] = UrlEvidence(
                raw_value=existing.raw_value,
                normalized_value=existing.normalized_value,
                source_start=existing.source_start,
                source_end=existing.source_end,
                source_locations=existing.source_locations + (location,),
                scheme_code=existing.scheme_code,
                host_value=existing.host_value,
                contains_userinfo=existing.contains_userinfo,
                validation_status=existing.validation_status,
                warning_codes=existing.warning_codes,
            )
            continue
        records[key] = UrlEvidence(
            raw_value=raw_value,
            normalized_value=normalized,
            source_start=start,
            source_end=end,
            source_locations=(location,),
            scheme_code=parsed.scheme.lower(),
            host_value=host,
            contains_userinfo=contains_userinfo,
            validation_status=status,
            warning_codes=tuple(dict.fromkeys(warnings)),
        )
    return tuple(records.values())


__all__ = ["UrlEvidence", "extract_url_evidence"]
