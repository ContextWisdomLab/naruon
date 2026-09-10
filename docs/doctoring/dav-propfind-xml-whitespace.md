# DAV PROPFIND XML whitespace boundary

## Decision

Naruon's bounded PROPFIND parser tolerates formatting whitespace between element-only grammar nodes, but the tolerated set is the XML 1.0 `S` production only: space (`#x20`), tab (`#x9`), carriage return (`#xD`), and line feed (`#xA`). It does not use Python's broader Unicode `str.strip()` classification as a substitute for XML grammar.

This matters because RFC 4918 defines `DAV:propfind` and its `prop`/`include` property-name containers as XML element-only/name-only syntax. Python considers characters such as U+00A0 NO-BREAK SPACE to be whitespace for `str.strip()`, while XML 1.0 does not include U+00A0 in production `S`. Treating U+00A0 as ignorable formatting would silently convert character data into grammar whitespace and could classify an invalid request as a supported `allprop` or a valid-but-unsupported `prop`/`include` mode.

The parser therefore uses an explicit XML-space predicate. Normal XML indentation remains accepted; non-XML Unicode spacing characters remain character content and are rejected before semantic-mode classification.

## Failure lineage

Source-order RED `e5a19a246af2fe2bf324ab0baf57eb7fd26bcfb6` adds route-level requests containing U+00A0 in three positions that the predecessor's `.strip()` checks treated as empty: `propfind` root text, `allprop` content, and `include` mixed content. Each request must return HTTP 400.

Minimal production fix `39a3e05bc5ffd62dc6b1096733fb2600b6468e82` replaces broad Unicode-strip truth tests with `_has_non_xml_space_content()`, whose accepted formatting set is exactly XML `S`. The same predicate is used for root text, directive tails, `allprop`, `propname`, and the `prop`/`include` property-name-container validator so syntax-before-semantics does not diverge by branch.

This is a grammar correction, not a Unicode-path policy. DAV path canonicalization and C0/C1 rejection remain owned by the existing authorization-path contract. No request-body size, Depth, collection-cardinality, authorization, provider-writeback, or dependency behavior changes here.

## Acceptance

`backend/tests/test_dav_propfind_body_contract.py::test_unicode_spaces_are_not_silently_treated_as_xml_whitespace` is the executable regression. Exact-head repository CI and independent review are still required after the source/test/doc sequence; predecessor GREEN or approval does not transfer.

## References

Bray, T., Paoli, J., Sperberg-McQueen, C. M., Maler, E., & Yergeau, F. (Eds.). (2008). *Extensible Markup Language (XML) 1.0 (Fifth Edition).* World Wide Web Consortium. https://www.w3.org/TR/xml/

Dusseault, L. (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). Internet Engineering Task Force. https://doi.org/10.17487/RFC4918