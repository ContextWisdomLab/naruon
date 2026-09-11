# DAV PROPFIND XML extensibility boundary

## Decision

Naruon's bounded PROPFIND parser follows RFC 4918 XML extensibility rules while keeping its intentionally narrow implemented DAV semantics. Unexpected XML elements and extension attributes are processed as if absent. Recognized `DAV:propfind` directives retain their syntax-before-semantics validation, and unsupported `propname`, selected `prop`, and `allprop` + `include` semantics continue to fail closed with HTTP 501 rather than being coerced to the supported bounded `allprop` profile.

RFC 4918 Section 17 requires WebDAV processors to process unexpected elements and attributes, including elements defined for another context, as if they were not present. It also states that extension attributes may be added and that element ordering is irrelevant unless otherwise stated. Consequently, an extension element beside `DAV:allprop`, or inside the `EMPTY` `DAV:allprop`/`DAV:propname` structural element, must not by itself turn a request into HTTP 400. Direct character content remains invalid because element-containing productions cannot be extended with text.

The `DAV:prop` and `DAV:include` containers are different: their child elements are property names by definition, not ignorable structural extensions. Naruon therefore continues to reject property values, nested child content, and mixed character data in those name-only selectors before returning 501 for the unsupported valid mode.

`DAV:allprop` + `DAV:include` recognition is order-insensitive. Naruon still returns 501 because include semantics are not implemented; changing XML element order cannot convert the same defined request into malformed input.

## Failure and repair lineage

Source-order RED `c0b154d70a62f3f46e98b866dbc62a0d15d7f4ea` adds route-level cases proving that an unexpected command extension beside `DAV:allprop`, an extension child of `DAV:allprop`, and reordered `DAV:include` + `DAV:allprop` must not be rejected solely because of extension placement or ordering.

The first production edit `8d6815db3c04c4b5aecd24bbbae6ad49f86ce1fd` contained unrelated handler-shape drift while applying the parser change. It is not acceptance evidence. Forward repair `db35735e62551264bb1ba2709fb95eeaa252651a` restores the predecessor handler exactly and confines the effective production delta to XML-extension processing: recognized directive filtering, order-insensitive `allprop`/`include`, and an EMPTY-directive validator that ignores extension children while retaining XML-S-only parent text checks. No force push or destructive rebase was used.

Test correction `12cdf2914d40956b6306d4559442f8d69b7c69f6` removes an older assertion that treated a child element inside `DAV:allprop` as invalid merely because the DTD calls `allprop` EMPTY. RFC 4918 Section 17 explicitly permits extension elements even for EMPTY element types. The replacement assertion preserves the actual grammar invariant: direct non-whitespace character content is invalid.

## Acceptance

The current branch must satisfy the complete DAV test suite, including:

- unexpected `propfind` extension element + `allprop` returns the supported 207 profile;
- extension children inside `allprop` are ignored for processing;
- `include` + `allprop` is recognized independent of order and returns the truthful unsupported-mode 501;
- direct non-XML-S character content remains 400;
- existing malformed XML, XXE, body-size, Depth, authorization, collection-cardinality, and unsupported-write regressions remain GREEN.

Repository-hosted exact-head checks and a qualifying independent post-last-push review remain required. Predecessor approvals or workflow runs do not transfer to a source-changing descendant.

## References

Dusseault, L. (2007). *HTTP extensions for Web Distributed Authoring and Versioning (WebDAV)* (RFC 4918). Internet Engineering Task Force. https://doi.org/10.17487/RFC4918

Bray, T., Paoli, J., Sperberg-McQueen, C. M., Maler, E., & Yergeau, F. (Eds.). (2008). *Extensible Markup Language (XML) 1.0 (Fifth Edition).* World Wide Web Consortium. https://www.w3.org/TR/xml/
