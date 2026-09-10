# DAV PROPFIND finite-depth boundary

## Decision

Naruon's current DAV surface is a bounded collection-discovery gateway, not a full WebDAV-compliant resource. `PROPFIND` therefore accepts only explicit finite `Depth: 0` and `Depth: 1` traversal. It does not silently coerce missing, `infinity`, or malformed `Depth` values to depth one.

RFC 4918 §9.1 requires a PROPFIND client to submit `Depth: 0`, `Depth: 1`, or `Depth: infinity`, requires WebDAV-compliant resources to support depths zero and one, and permits servers to disable infinite-depth PROPFIND because of performance and security concerns. The same section recommends treating a missing Depth header as `Depth: infinity`. RFC 4918 §9.1.1 permits a server to reject an infinite-depth PROPFIND on a collection with HTTP 403 and recommends the `DAV:propfind-finite-depth` precondition. RFC 4918 §10.2 defines the Depth header grammar as exactly `0`, `1`, or `infinity`.

Naruon applies that protocol meaning without making a WebDAV compliance claim:

- `Depth: 0` returns only the addressed collection representation.
- `Depth: 1` returns the bounded collection/member representation implemented by the current project-folder gateway.
- `Depth: infinity` returns HTTP 403 with an XML `DAV:propfind-finite-depth` precondition because unbounded recursive traversal is not implemented.
- A missing Depth header follows RFC 4918's recommended infinity interpretation and receives the same finite-depth rejection. Naruon does not reinterpret absence as depth one.
- Values outside the RFC 4918 grammar return HTTP 400 instead of being silently normalized to a supported value.

This decision is deliberately consistent with the existing capability-discovery boundary in `dav-authorization-path-decoding.md`: `OPTIONS` advertises `Allow: OPTIONS, PROPFIND` but omits the `DAV` compliance header. Supporting a bounded subset of PROPFIND semantics is not represented as class-1 WebDAV compliance.

## Failure lineage

The predecessor helper `_dav_depth()` used `request.headers.get("Depth", "1")`, returned `"0"` only for zero, and mapped every other value to `"1"`. That produced three distinct semantic errors: a missing Depth header became depth one rather than the RFC 4918 infinity default, an explicit `Depth: infinity` was silently reduced to one level, and malformed values such as `Depth: 2` or `Depth: children` were accepted as depth one.

Reality RED `e0e14695e8365458bb7815c2035c2d3c8c641295` adds route-level acceptance for the bounded policy: missing/infinite depth must return the finite-depth WebDAV precondition and malformed values must return 400. On the predecessor implementation those requests instead succeeded as depth-one PROPFIND responses.

Causal production fix `377693c9aa0b5a6dc7bb2cbd7f9664773af41ed6` makes the parser preserve the three RFC-defined depth values, treats an absent header as infinity, rejects values outside the grammar, and returns the `DAV:propfind-finite-depth` XML error for unsupported infinite traversal. Compatibility-test children `0dc0db0713222cc4078251476d8085a2f2204005` and `a32d65d246c13c969ce98fc4c892e7c4436e341d` make pre-existing successful PROPFIND regressions state their intended finite `Depth: 1` explicitly instead of depending on the former non-standard default. Test-only child `71b9d043d68e5448a541f1f2b4959fcfab66d847` additionally locks the positive `Depth: 0` invariant: the root collection returns exactly its own representation and does not enumerate the `demo` child.

## Invariants and acceptance

Protocol depth is part of request semantics and must not be rewritten merely to obtain a successful response. The server may bound work by refusing infinity, but it must distinguish refusal from successful finite traversal. Authentication and canonical-path authorization still execute before PROPFIND depth handling, so invalid ownership or path representations are not disclosed through the depth response.

Executable acceptance is owned by `backend/tests/test_dav_depth_contract.py`, with compatibility coverage in `backend/tests/test_dav_api.py` and `backend/tests/test_dav_canonical_path_succession.py`. The depth contract covers explicit zero and one, the RFC-recommended missing-header infinity interpretation, explicit infinity refusal, malformed values, and the WebDAV finite-depth precondition. The exact branch head must run these tests together with the repository's full backend, security, and image-validation gates after every source, test, or documentation change. Earlier GREEN runs on `4709189bfe1bca77e020c59a4da2d2e190b2022a` are predecessor evidence only after this source-changing sequence.

No claim is made that Naruon implements infinite-depth traversal, PROPPATCH, COPY, MOVE, locking, CalDAV, CardDAV, or WebDAV class-1 compliance. Those capabilities require their own complete contracts and executable interoperability evidence before advertisement.

## References

Dusseault, L. (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). Internet Engineering Task Force. https://doi.org/10.17487/RFC4918
