# DAV collection URL canonicalization

## Problem

Naruon's PROPFIND response marked project folders as `DAV:collection` resources but emitted their `DAV:href` values without a trailing slash. RFC 4918 states that wherever a server produces a URL referring to a collection, it SHOULD include the trailing slash. The mismatch could make WebDAV clients treat the same collection URL in multiple forms and complicate member-URL resolution.

## Decision

All Naruon-generated `DAV:href` values that identify collections use the trailing-slash form. This is response canonicalization only: authorization, owner scoping, database lookup, collection membership, and supported PROPFIND semantics are unchanged.

The root project collection already emitted `/api/dav/{owner}/projects/`. Project-folder collections now emit `/api/dav/{owner}/projects/{folder_uid}/`.

## Evidence

- Source-order regression: `ba992e3e49aa2ad9d21fe7af7f727d69faff7b03` requires both addressed and member collection hrefs to use trailing slashes. The predecessor implementation fails the member assertion because it emitted `/projects/demo`.
- Minimal production repair: `a755e4573e833e816b15820535296503d4b04f03` changes only the generated project-folder collection href to `/projects/{folder_uid}/`.
- Acceptance requires exact-head repository CI and an independent post-last-push review; predecessor receipts do not transfer to this source-changing descendant.

## Traceability

Code:

- `backend/api/dav.py::_project_folder_response`
- `backend/tests/test_dav_collection_href_contract.py::test_propfind_emits_trailing_slashes_for_collection_hrefs`

Standard:

Dusseault, L. M. (Ed.). (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). Internet Engineering Task Force. https://doi.org/10.17487/RFC4918

Relevant requirement: RFC 4918 §5.1 states that when a server produces a URL referring to a collection, the trailing-slash form should be used.
