# DAV empty-segment canonicalization

Observed: 2026-09-11

## Problem

Naruon's DAV owner/routing path is normalized after ASGI decoding. `_dav_path_segments()` historically discarded empty segments, and `_dav_path_owner_user_id()` strips the route-root/trailing slash characters after authorization checks. Distinct request-target paths such as `user123//projects`, `user123/projects//demo`, and `/dav//user123/projects` must not silently collapse onto the canonical single-slash resource.

RFC 3986 does not define adjacent slash characters as redundant. Section 3.3 defines a path as a sequence of slash-separated segments, permits zero-length segments through `segment = *pchar`, and treats non-dot path segments as opaque to generic URI syntax. Silently dropping an interior empty segment therefore changes URI path structure rather than applying a generic URI normalization rule.

This does **not** claim that RFC 3986 forbids empty segments. Naruon deliberately applies a stricter authenticated DAV route contract: interior empty segments, repeated trailing separators, and an extra separator immediately after the `/dav/` route prefix are rejected rather than collapsed onto another owner resource. A single leading slash remains valid when `_normalize_dav_authorization_path()` is called with an already decoded absolute path, and a single trailing slash remains valid for collection URLs.

## RED → repair

- RED `999d7411b8b5188277ffd899c2257dde36886f61` requires ambiguous interior/repeated empty segments to return HTTP 400 rather than reaching `OPTIONS` successfully.
- RED extension `ce7ddd2c3d6e49909351595d4747cca2594527dc` covers an extra route separator such as `/dav//user123/projects`.
- Initial fix `d2eb3dc44f05e7ebb6915c5477b9c62ba6cfd7ac` rejected every normalized path beginning with `/`. That was too broad: `_normalize_dav_authorization_path()` is also a reusable post-ASGI helper whose established contract accepts one route-root slash.
- Hosted exact-head Application CI `34545435466` on `1a815094991b5c04df955066290a8d33c155c54e` supplied the reality RED: 3 failures / 1955 passes / 2 live-smoke skips. Two failures proved that the helper incorrectly rejected `/alice/docs` and the long `/alice/...` non-recursive path. The third proved that framework-decoded `\..\` traversal was being reclassified from the authorization boundary's 403 to an empty-segment 400.
- Causal repair `2b91bcea871f9151abfaac22702f1c3b1bfc5857` preserves one literal leading slash for the reusable helper, rejects a leading separator created only by backslash normalization, keeps interior/repeated empty-segment rejection, and lets dot-segment traversal continue to the existing owner-authorization fail-closed path. `dav_handler()` separately rejects a captured path beginning with `/`, which is how the registered `/dav/{path:path}` route distinguishes `/dav//...` from its canonical form.

The repair intentionally retains the existing single-backslash compatibility normalization: one framework-decoded backslash separator between ordinary segments becomes one slash and uses the same canonical authorization path. A backslash-created leading separator remains ambiguous and is rejected. Traversal segments are not relabelled as malformed empty-segment syntax; they continue to the pre-existing 403 authorization rejection.

## Decision

Alternatives considered:

- **Continue dropping empty segments:** rejected because distinct URI paths remain indistinguishable at the application boundary.
- **Reject every normalized leading slash in the helper:** rejected after exact-head CI demonstrated that it violates the helper's established already-decoded absolute-path contract.
- **Redirect ambiguous requests to a canonical path:** rejected for this authenticated DAV gateway because redirect semantics introduce another method/body/authentication boundary without product value.
- **Separate route-capture ambiguity from reusable-path normalization:** selected. The route handler rejects the extra separator represented by a captured leading slash, while the normalization helper preserves one genuine route-root slash and rejects only ambiguous separators that would otherwise change resource identity.

Risk: clients that relied on duplicate-slash tolerance now receive HTTP 400. That behavior was never an advertised Naruon contract and represented ambiguous resource identity. Canonical single-slash collection URLs and the helper's single absolute-path leading slash remain supported.

## Acceptance

The route-level regression exercises `OPTIONS` because it proves the request-target invariant before method-specific DAV handling or database access. Existing unit coverage simultaneously locks the reusable helper's one-leading-slash behavior and the single-decode traversal contract. The same canonical path is then used for owner authorization, logging, and PROPFIND routing.

The exact-head workflow after `2b91bcea871f9151abfaac22702f1c3b1bfc5857` is separate merge evidence. Predecessor Docker/Bandit successes and the predecessor Application CI failure are not transferred as GREEN receipts.

## Traceability

- Production: `backend/api/dav.py::_normalize_dav_authorization_path`, `backend/api/dav.py::dav_handler`
- Regressions: `backend/tests/test_dav_canonical_path_succession.py::test_dav_rejects_ambiguous_empty_path_segments`, `backend/tests/test_dav_api.py::test_normalize_dav_authorization_path_treats_route_path_as_already_decoded`, `backend/tests/test_dav_api.py::test_dav_route_rejects_single_decode_traversal`
- Hosted RED: Application CI `34545435466` on `1a815094991b5c04df955066290a8d33c155c54e`
- Causal repair: `2b91bcea871f9151abfaac22702f1c3b1bfc5857`
- PR: `ContextualWisdomLab/naruon#1645`
- Parent authority: `ContextualWisdomLab/naruon#1417`

## Reference

Berners-Lee, T., Fielding, R., & Masinter, L. (2005). *Uniform Resource Identifier (URI): Generic Syntax* (RFC 3986, STD 66). RFC Editor. https://doi.org/10.17487/RFC3986
