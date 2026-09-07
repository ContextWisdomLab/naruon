# Auditable data-hygiene tools

**Status:** active PR candidate; not shipped until protected-branch integration.

## Customer contract

Use `url_evidence_extractor` when the next action is to review links found in
email or document text. It returns source-grounded records with Unicode spans,
normalized host values, validation status, warning codes, and a deduplicated
normalized-value list. It does not resolve DNS, open sockets, follow redirects,
or fetch URLs.

Use `contact_data_redactor` when a customer needs a safe working copy for the
supported contact classes. It returns deterministic `[EMAIL_n]` and
`[PHONE_n]` placeholders, source/replacement spans, counts, and a detector
version. Repeated values reuse a placeholder within one invocation.

## Explicit limits

- URL scope is absolute HTTP(S) URI references. `mailto:`, `ftp:`, relative
  references, and unsupported schemes are not extracted.
- Contact scope is ASCII email syntax and conservative Korean/E.164-compatible
  telephone syntax. Internationalized email local-parts, addresses, identity
  numbers, payment data, names, and arbitrary PII are not covered.
- Inputs are capped at 64 MiB, matching the signed import working ceiling rather
  than limiting attachment-sized text to 1 MiB. URL candidates are capped at
  2,048 UTF-8 bytes and 128 matches per invocation.
- Warnings are part of the output contract. A redacted result is not a claim of
  anonymization, irreversible de-identification, or regulatory compliance.

## Standards and research traceability (APA 7th)

Berners-Lee, T., Fielding, R., & Masinter, L. (2005). *Uniform resource
identifier (URI): Generic syntax* (RFC 3986). RFC Editor.
https://doi.org/10.17487/RFC3986

Boeckl, K., & Lefkovitz, N. (2020). *NIST Privacy Framework: A tool for
improving privacy through enterprise risk management, version 1.0*.
National Institute of Standards and Technology.
https://doi.org/10.6028/NIST.CSWP.01162020

International Telecommunication Union. (2010). *The international public
telecommunication numbering plan* (Recommendation ITU-T E.164).
https://www.itu.int/rec/T-REC-E.164

McCallister, E., Grance, T., & Scarfone, K. (2010). *Guide to protecting the
confidentiality of personally identifiable information (PII)* (NIST SP
800-122). National Institute of Standards and Technology.
https://doi.org/10.6028/NIST.SP.800-122

These authoritative standards define URI syntax, numbering-plan context, and
privacy-risk boundaries; they do not turn this narrow detector into a complete
PII classifier. No paper PDF is committed because redistribution permission for
additional publisher material was not established.

## Verification

Run:

```bash
uv run --project backend --group dev pytest -q \
  backend/tests/test_url_evidence_tool.py \
  backend/tests/test_contact_data_redactor.py
```

The browser/API call must use the existing signed-session cookie/bearer path;
public identity headers and real customer mail data are not test inputs.
