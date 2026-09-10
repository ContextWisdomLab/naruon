# DAV project-collection Depth truthfulness

Observed: 2026-09-11

## Problem

Naruon's `/dav/{owner}/projects/` collection is a server-side registry surface. A direct project URL such as `/dav/{owner}/projects/{folder_uid}/` is emitted as a `DAV:collection`, but Naruon does not yet enumerate the customer-owned provider folder's internal members through this gateway.

Before this repair, a `PROPFIND` with `Depth: 1` against a direct project collection returned HTTP 207 with only the addressed project collection. That response was indistinguishable from a complete depth-one result for an actually empty collection. It therefore asserted a negative fact about provider membership that Naruon had not queried and could not establish.

RFC 4918 defines `Depth: 1` as applying a method to the addressed resource and its internal members, and requires a collection PROPFIND multistatus to include a response for each member URL to the requested depth. Returning only the addressed collection is therefore not a truthful implementation of depth-one traversal when internal membership is unknown.

## Decision

Keep the two supported discovery layers distinct.

- `PROPFIND /dav/{owner}/projects/` with `Depth: 1` continues to enumerate the Naruon-owned project registry's direct `ProjectFolder` members, subject to the existing 256-member product ceiling and 257-row overflow probe.
- `PROPFIND /dav/{owner}/projects/{folder_uid}/` with `Depth: 0` continues to return the selected project collection's own properties after server-authoritative owner/organization lookup.
- `PROPFIND /dav/{owner}/projects/{folder_uid}/` with `Depth: 1` now returns HTTP 501 after confirming that the project collection exists. Naruon cannot truthfully enumerate that customer-owned provider collection until a released source/provider contract supplies direct-member discovery.
- Missing direct project collections continue to return 404 rather than being converted into a generic capability error.

HTTP 501 is used as a product capability boundary, not as a claim that RFC 4918 mandates this status for partial WebDAV servers. Naruon intentionally does not advertise full WebDAV compliance while required class-1 behavior is incomplete. RFC 9110 defines 501 as indicating that the server does not support the functionality required to fulfill a request.

## Rejected alternatives

Returning the addressed collection alone with 207 was rejected because it can make an unknown provider collection appear empty. Returning an arbitrary truncated member list was rejected because it would manufacture incomplete membership without signaling loss. Fetching provider contents directly from this route was rejected because provider execution, credentials, source capability, and conflict semantics belong to the signed source/runner boundary rather than this registry reader.

## Executable lineage

- Predecessor exact head: `6b2f2befa3533c507c885818bf52d66adc51a470`.
- Reality RED: `3c1ba9207b46243712f229ac1f75b76a6eebf867` adds a route-level contract requiring direct project `Depth: 1` to fail closed instead of reporting a false empty collection.
- Minimal causal fix: `dbcad849194153e1dc19bb570424cca5670339ac` preserves the existing DB existence lookup and returns 501 only after the selected project collection is found.
- Regression alignment: `cf08479d7645c027680600a9758849845d384a79` and `8c794f15a19dcba394d6d691bd0c76271c7fa90f` move existing XML-escaping and encoded-percent property-read probes to `Depth: 0`; those tests never established provider child enumeration and must not encode that unsupported assumption.

The production change is confined to `backend/api/dav.py`. The new depth contract is in `backend/tests/test_dav_depth_contract.py`; existing path-safety probes remain in `backend/tests/test_dav_api.py`.

## Remaining boundary

This repair does not implement provider-backed WebDAV member enumeration and does not make Naruon a file-store source of truth. A future implementation must consume a released source/provider contract, preserve signed user/organization/workspace authority, bound result cardinality and payload work, and provide exact-head tests showing that every returned member is authorized and server-authoritative before `Depth: 1` can return a successful direct-project multistatus.

## References

Dusseault, L. (Ed.). (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). RFC Editor. https://doi.org/10.17487/RFC4918

Fielding, R., Nottingham, M., & Reschke, J. (2022). *HTTP semantics* (RFC 9110). RFC Editor. https://doi.org/10.17487/RFC9110
