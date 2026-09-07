# CardDAV TXT path canonicalization

## Scope

Naruon consumes the optional `path` key advertised by a secure `_carddavs._tcp` TXT record during CardDAV discovery. The value becomes part of an outbound HTTPS request target, so validation must reject ambiguous encodings without changing the provider-advertised identity of reserved path data.

## Decision

The parser applies the following fail-closed contract:

1. Reject malformed percent triplets before decoding.
2. Percent-decode the TXT value exactly once with strict UTF-8 handling for security validation.
3. Reject the value when a valid percent triplet remains after that validation pass, because a second decoder could observe a different request target.
4. Reject traversal segments, backslashes, query or fragment delimiters, absolute-URI syntax, and Unicode control characters in the decoded validation representation.
5. Normalize percent-encoded unreserved/non-ASCII text through the existing single-pass UTF-8 path contract, while preserving percent-encoded RFC 3986 reserved characters in the executed path. The sole structural exception is an encoded leading `/`, which is canonicalized to the required leading path delimiter.
6. Uppercase the hexadecimal digits of preserved reserved escapes so equivalent percent encodings have one wire representation.

This replaces the previous arbitrary five-round recursive decoding budget. Recursive decoding changed legitimate literal-percent paths and left the security meaning dependent on a chosen iteration count. The current contract performs one security decode and rejects nested encodings, while retaining the distinction RFC 3986 makes between a reserved character and its percent-encoded octet. For example, `/users/alice%2Fcalendar` remains distinct from `/users/alice/calendar`, and `/collections/a%3Bb` remains distinct from `/collections/a;b` after validation.

An encoded literal percent remains supported when its decoded form does not begin another percent triplet. Invalid UTF-8 is rejected rather than normalized through the Unicode replacement character.

## Product boundary

This decision protects CardDAV auto-discovery only. It does not grant authorization to arbitrary paths, weaken the existing HTTPS/global-address SSRF controls, or treat TXT records as trusted credentials. Provider account authorization and resource ownership remain separate checks.

## Verification

The focused regression suite covers:

- a singly encoded leading slash;
- Korean UTF-8 path text;
- percent-encoded reserved `/` and `;` data whose wire identity must survive validation;
- nested encoded slash and traversal forms;
- nested encoded percent forms;
- incomplete and non-hex percent triplets;
- invalid UTF-8 octets;
- a safe encoded literal percent.

The RED regression was added first at `43467ed10fb3ec6c3f2075a38acf9a934342ca02`: the previous unconditional `unquote` returned structural `/` and `;` characters for the two reserved-escape cases. The minimal production repair is `882c1dda08276d11bb346774dcc3119f64bc51b9`, which keeps the fully decoded representation for security checks and derives a separate execution representation that protects RFC 3986 reserved escapes. Hosted exact-head execution remains required before the repair is classified GREEN.

## References

Berners-Lee, T., Fielding, R., & Masinter, L. (2005). *Uniform resource identifier (URI): Generic syntax* (RFC 3986). RFC Editor. https://doi.org/10.17487/RFC3986

Daboo, C. (2013). *Locating services for calendaring extensions to WebDAV (CalDAV) and vCard extensions to WebDAV (CardDAV)* (RFC 6764). RFC Editor. https://doi.org/10.17487/RFC6764

MITRE. (2025). *CWE-174: Double decoding of the same data*. Common Weakness Enumeration. https://cwe.mitre.org/data/definitions/174.html
