# DAV PROPFIND finite-depth boundary

## Decision

Naruon's current DAV surface is a bounded collection-discovery gateway, not a full WebDAV-compliant resource. `PROPFIND` therefore accepts only explicit finite `Depth: 0` and `Depth: 1` traversal. It does not silently coerce missing, `infinity`, or malformed `Depth` values to depth one.

RFC 4918 §9.1 requires a PROPFIND client to submit `Depth: 0`, `Depth: 1`, or `Depth: infinity`, requires WebDAV-compliant resources to support depths zero and one, and permits servers to disable infinite-depth PROPFIND because of performance and security concerns. The same section recommends treating a missing Depth header as `Depth: infinity`. RFC 4918 §9.1.1 permits a server to reject an infinite-depth PROPFIND on a collection with HTTP 403 and recommends the `DAV:propfind-finite-depth` precondition. RFC 4918 §10.2 defines the Depth header grammar as exactly `0`, `1`, or `infinity`; depth one applies the method to the addressed resource and its internal members. RFC 4918 §8.3.1 illustrates the same response shape: a depth-one request to a collection returns one `href` for the collection itself and one for each direct internal member represented in the response.

Naruon applies that protocol meaning without making a WebDAV compliance claim:

- `Depth: 0` returns only the addressed collection representation.
- `Depth: 1` returns the addressed collection representation first and then its direct project-folder members when the collection contains at most 256 members.
- Root `Depth: 1` probes at most 257 rows in PostgreSQL. The extra row is only an overflow sentinel; Naruon never emits a silently truncated 256-member success response.
- A root collection with more than 256 direct project-folder members returns HTTP 403 with the Naruon extension precondition `urn:naruon:dav:project-member-limit`.
- `Depth: infinity` returns HTTP 403 with an XML `DAV:propfind-finite-depth` precondition because unbounded recursive traversal is not implemented.
- A missing Depth header follows RFC 4918's recommended infinity interpretation and receives the same finite-depth rejection. Naruon does not reinterpret absence as depth one.
- Values outside the RFC 4918 grammar return HTTP 400 instead of being silently normalized to a supported value.

The 256-member ceiling is a Naruon product resource policy, not an RFC 4918 limit. RFC 4918 §16 permits WebDAV error bodies to be extended with custom child elements in a namespace other than the reserved `DAV:` namespace and notes that 403 is appropriate when a request should not simply be repeated because the same server-side condition will make it fail again. The numeric status therefore remains meaningful to generic clients while the namespaced precondition lets Naruon-aware clients distinguish the collection-size policy from the RFC-defined infinite-depth refusal.

This decision is deliberately consistent with the existing capability-discovery boundary in `dav-authorization-path-decoding.md`: `OPTIONS` advertises `Allow: OPTIONS, PROPFIND` but omits the `DAV` compliance header. Supporting a bounded subset of PROPFIND semantics is not represented as class-1 WebDAV compliance.

## Failure lineage

The predecessor helper `_dav_depth()` used `request.headers.get("Depth", "1")`, returned `"0"` only for zero, and mapped every other value to `"1"`. That produced three distinct semantic errors: a missing Depth header became depth one rather than the RFC 4918 infinity default, an explicit `Depth: infinity` was silently reduced to one level, and malformed values such as `Depth: 2` or `Depth: children` were accepted as depth one.

Reality RED `e0e14695e8365458bb7815c2035c2d3c8c641295` adds route-level acceptance for the bounded policy: missing/infinite depth must return the finite-depth WebDAV precondition and malformed values must return 400. On the predecessor implementation those requests instead succeeded as depth-one PROPFIND responses.

Causal production fix `377693c9aa0b5a6dc7bb2cbd7f9664773af41ed6` makes the parser preserve the three RFC-defined depth values, treats an absent header as infinity, rejects values outside the grammar, and returns the `DAV:propfind-finite-depth` XML error for unsupported infinite traversal. Compatibility-test children `0dc0db0713222cc4078251476d8085a2f2204005` and `a32d65d246c13c969ce98fc4c892e7c4436e341d` make pre-existing successful PROPFIND regressions state their intended finite `Depth: 1` explicitly instead of depending on the former non-standard default. Test-only child `71b9d043d68e5448a541f1f2b4959fcfab66d847` additionally locks the positive `Depth: 0` invariant: the root collection returns exactly its own representation and does not enumerate the `demo` child.

A subsequent standards audit found a second interoperability defect inside the now-explicit depth-one path. The root project collection returned only its direct folder members and omitted the addressed collection itself. RFC 4918 depth-one semantics include both the resource and its internal members; omitting the target gives clients an incomplete multistatus view even though the request succeeds. Reality RED `268a41a342e7f730c8a6a4e905d414d797aaeebd` requires the project collection and its direct `demo` member to appear together. Minimal production fix `e9666093217674687ef7f0c62248a5bb637097f1` reuses one addressed-collection representation for both depth zero and depth one, prepending it to the direct-member responses without changing authorization or infinite-depth policy.

Resource review then found that "bounded" was still false for member cardinality: root depth-one discovery called `get_project_folders_from_db()` without a SQL limit and materialized every matching project folder before serializing every response. Reality RED `facfdcc1dad83bb5f1b9855c823e39fde3c74b2e` requires the DAV root query to request a 257-row overflow probe and requires a 257-member result to fail closed instead of returning a 207 response. Service child `b784ce93591c496e6b5a0d8b36341c3a4a8b4091` adds an optional SQL `LIMIT` capability without changing existing unbounded callers. DAV fix `093e748cbc7ce34360ef3cdef017957909542d23` uses `LIMIT 257`, returns normal depth-one output only for at most 256 members, and returns the namespaced 403 precondition above on overflow. Compatibility child `e28199395aac868b6d287d24aabea7c3e533811a` updates existing DAV stubs to assert the bounded query contract, and `18b1bd70281c12050083b87d3da3e6e0a47a149a` verifies that the service-level `max_results` parameter is actually compiled into SQL rather than being an API-only hint.

## Invariants and acceptance

Protocol depth is part of request semantics and must not be rewritten merely to obtain a successful response. The server may bound work by refusing infinity or an oversized direct-member set, but it must distinguish refusal from successful finite traversal. For a collection, depth zero is self-only and depth one is self plus direct internal members; returning only children or silently truncating members is not an equivalent representation. Authentication and canonical-path authorization still execute before PROPFIND depth handling, so invalid ownership or path representations are not disclosed through the depth response.

Executable acceptance is owned by `backend/tests/test_dav_depth_contract.py`, with compatibility coverage in `backend/tests/test_dav_api.py` and `backend/tests/test_dav_canonical_path_succession.py`. The depth contract covers explicit zero and one, depth-one target-plus-member shape, the 256-member success ceiling and 257-row overflow probe, the RFC-recommended missing-header infinity interpretation, explicit infinity refusal, malformed values, and the WebDAV error preconditions. The exact branch head must run these tests together with the repository's full backend, security, and image-validation gates after every source, test, or documentation change. Earlier GREEN runs are predecessor evidence after any later source, test, or doctoring commit.

No claim is made that Naruon implements infinite-depth traversal, PROPPATCH, COPY, MOVE, locking, CalDAV, CardDAV, or WebDAV class-1 compliance. Those capabilities require their own complete contracts and executable interoperability evidence before advertisement.

## References

Dusseault, L. (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). Internet Engineering Task Force. https://doi.org/10.17487/RFC4918
