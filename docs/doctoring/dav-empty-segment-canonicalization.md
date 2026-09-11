# DAV empty-segment canonicalization

Observed: 2026-09-11

## Problem

Naruon's DAV owner/routing path was normalized after ASGI decoding. `_dav_path_segments()` discarded empty segments, and `_dav_path_owner_user_id()` stripped leading/trailing slash characters. As a result, distinct request-target paths such as `user123//projects`, `user123/projects//demo`, and a path whose captured DAV suffix begins with `/` could collapse onto the same owner/project route as the canonical single-slash path.

RFC 3986 does not define adjacent slash characters as redundant. Section 3.3 defines a path as a sequence of slash-separated segments, permits zero-length segments through `segment = *pchar`, and treats non-dot path segments as opaque to the generic URI syntax. Therefore silently dropping empty segments changes URI path structure rather than applying a generic URI normalization rule.

This does **not** claim that RFC 3986 forbids empty segments. Naruon deliberately applies a stricter DAV route contract: interior empty segments, repeated trailing separators, and an ASGI-captured leading separator are rejected instead of being collapsed onto a canonical owner resource. A single trailing slash remains valid for collection URLs.

## RED → repair

- RED `999d7411b8b5188277ffd899c2257dde36886f61` requires ambiguous interior/repeated empty segments to return HTTP 400 rather than reaching `OPTIONS` successfully.
- RED extension `ce7ddd2c3d6e49909351595d4747cca2594527dc` covers the leading empty segment produced when the captured DAV suffix begins with `/`.
- Causal fix `d2eb3dc44f05e7ebb6915c5477b9c62ba6cfd7ac` rejects a normalized path that starts with `/` or contains `//` before owner comparison, logging, or DAV project routing.

The repair intentionally leaves the existing single-backslash compatibility normalization intact: one framework-decoded backslash separator is mapped to one slash and then routed through the same canonical authorization path. Multiple separators become ambiguous and fail closed.

## Decision

Alternatives considered:

- **Continue dropping empty segments:** rejected because distinct URI paths remain indistinguishable at the application boundary.
- **Redirect every ambiguous request to a canonical path:** rejected for this authenticated DAV gateway because redirect semantics would add another method/body/authentication boundary and are unnecessary for a malformed Naruon route identity.
- **Reject ambiguous empty segments before routing:** selected. It is deterministic, preserves one resource identity per accepted route, requires no provider call, and happens before request logging and method-specific behavior.

Risk: clients that previously relied on duplicate slash tolerance now receive HTTP 400. That behavior was never an advertised Naruon contract and represented ambiguous resource identity; canonical single-slash collection URLs remain supported.

## Acceptance

The route-level regression exercises `OPTIONS` because it proves the invariant applies before method-specific DAV handling or database access. The same normalized path is subsequently used for owner authorization, logging, and PROPFIND routing, so rejecting ambiguity at this boundary prevents downstream segment collapsing for every registered DAV method.

Hosted exact-head workflow results and independent review remain separate merge evidence; this document records the source contract and does not promote predecessor receipts.

## Traceability

- Production: `backend/api/dav.py::_normalize_dav_authorization_path`
- Regression: `backend/tests/test_dav_canonical_path_succession.py::test_dav_rejects_ambiguous_empty_path_segments`
- PR: `ContextualWisdomLab/naruon#1645`
- Parent authority: `ContextualWisdomLab/naruon#1417`

## Reference

Berners-Lee, T., Fielding, R., & Masinter, L. (2005). *Uniform Resource Identifier (URI): Generic Syntax* (RFC 3986, STD 66). RFC Editor. https://doi.org/10.17487/RFC3986
