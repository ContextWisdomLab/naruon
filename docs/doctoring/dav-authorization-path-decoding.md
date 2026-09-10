# DAV authorization-path decoding boundary

## Decision

Naruon authorizes DAV paths against the Unicode `path` value supplied by ASGI routing and does not percent-decode that value again. The original request-target bytes, when supplied as ASGI `raw_path`, are used to validate wire-level percent syntax and to determine whether exactly one wire decode would leave another `%HH` escape. Backslashes are normalized to `/` before owner/traversal checks.

This separates two representations that must not be conflated:

- `raw_path`: original request-target path bytes. It is the only representation that can distinguish a literal percent encoded as `%25` from malformed raw `%` syntax or an ambiguous nested encoding such as `%252e` or `%25%32%65`.
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
5. `9a294e3bf3f7330f1ab51a7c6878864481f40d9f` adds RED cases for split nested encodings such as `%25%32%65`. A raw-prefix regex that only recognized `%25` followed by literal hex characters could miss these encodings even though one wire decode produces `%2e` or `%5c`.
6. `1df3aa46bce2e7fa28b6301e9e9cc846fd5cef7f` replaces that raw-prefix heuristic with one `unquote_to_bytes(raw_path)` used only for ambiguity classification, then rejects the request if the resulting bytes still contain a valid `%HH` escape. Authorization itself continues to consume the framework-decoded `path` without another decode.
7. CodeRabbit review on predecessor head `55068845c22c195c68e15429072cdb689245021a` identified a still-valid decoded-control gap: UTF-8 percent encodings such as `%C2%80` become C1 control characters in ASGI `path`, while the raw-byte C0/DEL check cannot classify them.
8. `f5fd8a467e6d17b71288ed09ed38a4dc0f1a2157` adds route-level RED cases for `%C2%80` and `%C2%9F`; `9d0d3af2fc9c193fde1c0b3cc635fc6daa9fed3d` rejects every decoded Unicode General Category `Cc` character before authorization or logging.
9. `dcdd606b7d6f426fc1e4e7c3f004c9d829932351` tightens the direct-handler regression so ESC, LF and CR are required to fail before any `DAV Request` log record is emitted, replacing the weaker predecessor assertion that only required escaped logging.
10. Current-head Codex review on `9edf30727433b3a4fafbc4523424175ad4f426dc` found an acceptance-coverage gap rather than a production defect: the fail-closed no-`raw_path` branch had a negative residual-percent test, but the documented positive invariant for a percent-free decoded path was not executable. `f29706fb88528a1cf1f2e23a2f46c4c4a7816e79` adds a direct-handler `OPTIONS` regression with no `raw_path` and a percent-free owner path, requiring HTTP 200 and capability discovery. No production logic changes in that commit.
11. Fresh capability review then found that the same `OPTIONS` response overstated the implemented surface: it advertised WebDAV classes `1, 2, 3`, `calendar-access`, `addressbook`, and methods including LOCK, COPY, MOVE and PROPPATCH while the current slice operationally implements only authenticated `OPTIONS` discovery and `PROPFIND`; provider-backed writeback remains fail-closed. RED `2b55a02c6a4f9e03d9f8cb1a09a7419d832dfd24` makes the mismatch executable. `6a565ed2c4fb3e18a6d9366fac5c2b7d708c1709` removes the unsupported `DAV` compliance advertisement and limits `Allow` to `OPTIONS, PROPFIND`. `0990d0ff215d6c203f221b5e64bd5954c2eaa909` aligns the existing owned OPTIONS regressions, and `25531c0d1dad1ad57cf1211df050c6067af3d2f0` folds the temporary RED-only test into `test_dav_api.py` so the effective owned file set remains narrow.

The old `0bdaf4fedc001fe43326fa67390f05f83a718238` checks were admitted while #1645 targeted `develop`; they are historical after the PR was retargeted to canonical parent #1417 and do not certify the current `(PR, base ref/SHA, head SHA)` identity. The CodeRabbit `CHANGES_REQUESTED` review on `55068845...` is also predecessor evidence after the C1 RED/fix/test sequence; its finding is retained as repair lineage, not as an unresolved current-head defect. The Codex finding on `9edf307...` is retained as evidence-quality lineage; because later commits change the exact head, predecessor review conclusions are not treated as current-head approval.

## Invariants

- Authorization never recursively percent-decodes a framework route value.
- Malformed raw percent triplets fail with HTTP 400 when `raw_path` is available.
- A raw `%25` that decodes to a literal percent is allowed when the first wire decode does not leave a valid `%HH` escape.
- Any raw representation whose first wire decode leaves a valid percent triplet, including contiguous `%252e` and split `%25%32%65`, is rejected as ambiguous before authorization.
- Percent-encoded C0/DEL control characters fail before owner or DAV operation handling.
- Framework-decoded Unicode control characters in General Category `Cc`, including C1 controls produced from UTF-8 percent encodings, fail before authorization or request logging.
- Invalid UTF-8 replacement/surrogate values in the framework-decoded path fail before authorization.
- `.` and `..` segments, including those produced by the framework's single decode and Windows-separator normalization, remain unauthorized.
- If `raw_path` is unavailable, a residual `%` in the decoded path fails closed because its wire provenance cannot be established. Percent-free decoded paths remain supported and must not be rejected solely because an ASGI server omits `raw_path`.
- The normalization and raw-validation path is linear in input length; there is no recursive or fixed-round decode loop.
- `Allow` advertises only methods operationally supported by the current target resource. A handler that intentionally returns 501 is not advertised as supported.
- The partial DAV gateway does not emit a `DAV` compliance header until the resource actually satisfies the corresponding WebDAV/extension requirements. In particular, current discovery support is not represented as class 1/2/3, CalDAV `calendar-access`, or CardDAV `addressbook` compliance.

## Capability-discovery decision

HTTP Semantics defines `Allow` as the methods advertised as supported by the target resource. It is not a roadmap or a list of methods that the router can syntactically receive. RFC 4918 likewise defines the `DAV` response header as a compliance advertisement: class 1 requires all WebDAV MUST requirements; class 2 adds locking requirements; class 3 is also a conformance claim. RFC 4918 requires capabilities such as PROPPATCH, COPY and MOVE for DAV-compliant resources. Naruon's current partial discovery gateway does not implement those contracts and explicitly returns 501 for provider-backed write operations. Advertising them would cause standards-aware clients to select behaviors the resource cannot honor.

The extension tokens are equally normative, not descriptive labels. RFC 4791 §5.1 states that advertising `calendar-access` in `DAV` indicates support for all MUST-level CalDAV requirements. RFC 6352 §6.1 states that `addressbook` indicates support for all MUST-level requirements and REQUIRED CardDAV features. Naruon does not yet implement those complete contracts, so neither token may be emitted merely because calendar/address data is a future or partial product concern.

The current decision is therefore fail-closed capability discovery: return HTTP 200 to authenticated `OPTIONS`, advertise `Allow: OPTIONS, PROPFIND`, and omit `DAV`. When full WebDAV/CalDAV/CardDAV behavior is implemented, each compliance token and method must be introduced together with its normative contract, authorization, conditional/write semantics, interoperability fixtures and executable acceptance. Some additional method names remain registered so those requests can receive an explicit 501 response; methods not registered follow the framework's method handling. Neither route registration nor an intentional 501 qualifies a method for `Allow`.

## Reproducible acceptance

The owned executable acceptance is `backend/tests/test_dav_api.py`. Required evidence includes raw, singly encoded, contiguous nested and split nested traversal cases; encoded-percent data; malformed triplets; slash/backslash variants; encoded C0/DEL and decoded C1 controls; invalid Unicode; direct-handler pre-log rejection of control characters; both negative residual-percent and positive percent-free behavior when `raw_path` is absent; route-level TestClient behavior; accurate OPTIONS capability advertisement; and a large input that exercises the non-recursive path. The current exact branch must run this test plus Ruff and the repository security/CI gates after every source, test or document change. A predecessor-head pass is not current-head evidence.

Issue #1344 stays open until current-base exact-head hosted checks, current-head independent review and all valid findings are complete. This document does not claim protected integration, release, deployment, broader DAV writeback support, or a security certification.

## References

ASGI Team. (n.d.). *HTTP & WebSocket ASGI message format*. ASGI 3.0 documentation. Retrieved September 10, 2026, from https://asgi.readthedocs.io/en/latest/specs/www.html

Berners-Lee, T., Fielding, R., & Masinter, L. (2005). *Uniform Resource Identifier (URI): Generic Syntax* (RFC 3986). Internet Engineering Task Force. https://doi.org/10.17487/RFC3986

Daboo, C. (2011). *CardDAV: vCard extensions to Web Distributed Authoring and Versioning (WebDAV)* (RFC 6352). Internet Engineering Task Force. https://doi.org/10.17487/RFC6352

Daboo, C., Desruisseaux, B., & Dusseault, L. (2007). *Calendaring extensions to WebDAV (CalDAV)* (RFC 4791). Internet Engineering Task Force. https://doi.org/10.17487/RFC4791

Dusseault, L. (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). Internet Engineering Task Force. https://doi.org/10.17487/RFC4918

Fielding, R., Nottingham, M., & Reschke, J. (2022). *HTTP semantics* (RFC 9110). Internet Engineering Task Force. https://doi.org/10.17487/RFC9110

The MITRE Corporation. (n.d.). *CWE-174: Double Decoding of the Same Data* (CWE List Version 4.20). Common Weakness Enumeration. Retrieved September 10, 2026, from https://cwe.mitre.org/data/definitions/174.html
