# ADR-0008: Bound URL evidence and contact redaction to explicit classes

**Status:** Accepted

**Date:** 2026-08-19

**Related issue:** #1247

## Decision

Naruon exposes two deterministic tools through the existing signed tool API:

1. `url_evidence_extractor` accepts only absolute `http` and `https` candidates,
   parses them with the standard URI parser, preserves Unicode source spans, and
   never fetches a result. Userinfo, malformed percent escapes, invalid hosts,
   and other unsafe forms are evidence classifications, not safe URLs.
2. `contact_data_redactor` supports ASCII email addresses and conservative
   Korean/E.164-compatible telephone forms. It returns replacement spans and
   detector-version evidence without returning matched source values.

Both tools accept up to 64 MiB of UTF-8 working text, matching the signed import
working ceiling rather than imposing a separate 1 MiB attachment-sized limit.
URL extraction still bounds candidate size and match count. The redactor warns
that unsupported PII classes remain and that the output is not anonymization or
irreversible de-identification.

## Consequences

- Buyers can inspect where a supported contact or URL was found and what action
  the product took next.
- Repeated URL occurrences retain separate source locations while normalized
  values are deduplicated first-wins.
- Internationalized email addresses, addresses, payment data, identity numbers,
  and other PII remain outside this release's detection claim.
- No database object or external dependency is introduced; the existing tool
  registry and signed-session boundary are reused.

## Rejected alternatives

- Treating a regular expression as a general PII anonymizer.
- Fetching extracted URLs during extraction.
- Returning raw contact values in match evidence or logs.
- Adding an LLM to a deterministic detector path.

## Verification

Focused tests cover Korean/English mixed text, IDNA, IPv6, balanced punctuation,
userinfo, invalid percent encoding, repeated matches, unsupported PII warnings,
overlap handling, and bounded input/match failure. Production behavior remains
subject to protected-branch CI, security, review, and coverage gates.
