# DAV authorization-path decoding boundary

## Decision

Naruon authorizes DAV paths against the Unicode `path` value supplied by ASGI routing and does not percent-decode that value again. The original request-target bytes, when supplied as ASGI `raw_path`, are used only to validate wire-level percent syntax and reject encodings whose first decode would leave another `%HH` sequence. Backslashes are normalized to `/` before owner/traversal checks.

This separates two representations that must not be conflated:

- `raw_path`: original request-target path bytes. It is the only representation that can distinguish a literal percent encoded as `%25` from malformed raw `%` syntax or an ambiguous nested encoding such as `%252e`.
- `path`: framework-decoded Unicode path. Authorization, owner extraction and traversal checks consume this representation without another percent-decoding pass.

The ASGI HTTP specification defines `path` as having percent-encoded and UTF-8 byte sequences decoded into characters. It defines `raw_path` as the original path bytes and notes that `raw_path` is optional. Therefore a second application `unquote()` over a route parameter is not a neutral normalization step: it can create a second interpretation of data that the framework has already decoded.

RFC 3986 §2.4 warns that implementations must not decode the same string more than once. CWE-174 describes the corresponding weakness as double decoding that can introduce dangerous input after an earlier validation step.

## Failure lineage

Issue #1344 identified the prior recursive-unquote loop as the wrong authorization boundary. PR #1645 initially replaced the loop with one explicit `unquote()`, but its helper-only tests did not account for framework decoding. That intermediate state also rejected legitimate encoded-percent data because `%25` became `%` and was then classified as a malformed escape.

The current repair is intentionally narrower:

1. `c91988398414db3cd0226749aaa336c268543dbc` adds route-level RED cases for framework-decoded nested traversal, literal encoded percent data, malformed raw escapes, encoded control characters, invalid UTF-8 replacement, single-decode traversal, and a large non-recursive path.
2. `eafcc8d4720e58bb04d3029774e5c31f38a6e1e0` removes application percent-decoding from authorization normalization and validates raw request-target syntax before owner checks.
3. ASGI specifies that `raw_path` may be absent. `b6931bf55a4a3320e103b417ee384c82f12444ac` therefore adds a second RED case: if raw provenance is unavailable and the decoded path still contains `%`, Naruon must not guess whether that percent came from valid encoded data, malformed wire syntax or a nested encoding.
4. `42b5af38f21231aa4cad5f2e0ce0768f81fc1ee4` makes that fallback fail closed while permitting percent-free decoded paths on ASGI servers that omit `raw_path`.

The old `0bdaf4fedc001fe43326fa67390f05f83a718238` checks were admitted while #1645 targeted `develop`; they are historical after the PR was retargeted to canonical parent #1417 and do not certify the current `(PR, base ref/SHA, head SHA)` identity.

## Invariants

- Authorization never recursively percent-decodes a framework route value.
- Malformed raw percent triplets fail with HTTP 400 when `raw_path` is available.
- A raw `%25` that would decode to a literal percent is allowed when it does not form a second `%HH` sequence.
- A raw encoding such as `%252e` or `%2525` that would expose another valid percent triplet is rejected as ambiguous before authorization.
- Percent-encoded C0/DEL control characters fail before owner or DAV operation handling.
- Invalid UTF-8 replacement/surrogate values in the framework-decoded path fail before authorization.
- `.` and `..` segments, including those produced by the framework's single decode and Windows-separator normalization, remain unauthorized.
- If `raw_path` is unavailable, a residual `%` in the decoded path fails closed because its wire provenance cannot be established. Percent-free decoded paths remain supported.
- The normalization path is linear in input length; there is no recursive or fixed-round decode loop.

## Reproducible acceptance

The owned executable acceptance is `backend/tests/test_dav_api.py`. Required evidence includes raw, singly encoded and nested traversal cases; encoded-percent data; malformed triplets; slash/backslash variants; encoded controls and invalid Unicode; route-level TestClient behavior; and a large input that exercises the non-recursive path. The current exact branch must run this test plus Ruff and the repository security/CI gates after every source or document change. A predecessor-head pass is not current-head evidence.

Issue #1344 stays open until current-base exact-head hosted checks, current-head independent review and all valid findings are complete. This document does not claim protected integration, release, deployment, broader DAV writeback support, or a security certification.

## References

ASGI Team. (n.d.). *HTTP & WebSocket ASGI message format*. ASGI 3.0 documentation. Retrieved September 10, 2026, from https://asgi.readthedocs.io/en/latest/specs/www.html

Berners-Lee, T., Fielding, R., & Masinter, L. (2005). *Uniform Resource Identifier (URI): Generic Syntax* (RFC 3986). Internet Engineering Task Force. https://doi.org/10.17487/RFC3986

The MITRE Corporation. (n.d.). *CWE-174: Double Decoding of the Same Data* (CWE List Version 4.20). Common Weakness Enumeration. Retrieved September 10, 2026, from https://cwe.mitre.org/data/definitions/174.html
