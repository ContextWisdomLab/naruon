# DAV unsupported-write request-body boundary

## Decision

Naruon currently does not implement provider-backed DAV write semantics. A `PUT` request that has passed authentication and DAV path validation therefore fails closed with HTTP 501 without consuming or buffering the request body.

The prior implementation called `await request.body()` before returning the already-determined 501 result. That body had no accepted domain meaning: it was not parsed, validated, persisted, forwarded, or used to decide the response. Buffering it nevertheless made memory and receive-path work scale with attacker-controlled request content before an unconditional rejection.

RFC 9110 defines `PUT` in terms of replacing the target resource with request content, while also stating that methods not implemented by the origin server should receive 501. Because this DAV slice does not implement the write operation, reading application content cannot complete any supported PUT semantics. The resource-safe boundary is therefore to reject after authentication/path validation and before application-level body consumption. Transport framing remains the HTTP server's responsibility; this decision does not claim that the network stack receives zero octets.

## RED to fix

- `fe678f6b4b52eecdfee97f1c3852f601cb53eec5` adds `backend/tests/test_dav_unsupported_write_body.py`. A direct ASGI request supplies a receive callback that records every body read. On the predecessor implementation, `dav_handler()` calls `request.body()`, so the regression is RED because `receive_calls` becomes nonzero.
- `90ba3d984863db8464b7b15fd5a216b0558b493f` is the minimal causal production fix. It removes the unused PUT body buffering and its byte-count log while preserving authentication, path validation, the existing warning, response text, and HTTP 501 contract.

## Invariants

- Unsupported provider-backed DAV `PUT` remains authenticated and path-validated before rejection.
- The application does not call `Request.body()`, iterate the request stream, parse content, or allocate a body-sized buffer for a PUT that is unconditionally rejected as not implemented.
- The response remains HTTP 501 until a real write aggregate, conditional semantics, authorization contract, persistence/provider adapter, and executable acceptance are implemented.
- A future write implementation must introduce an explicit content-size policy and streaming strategy rather than silently restoring unbounded buffering.

## Reproducible acceptance

`backend/tests/test_dav_unsupported_write_body.py` is the focused regression. It must return 501 while the custom ASGI receive callback remains uncalled. The existing DAV suite remains responsible for authentication, owner scoping, canonical path handling, capability discovery, traversal/encoding rejection, and provider-backed write fail closure.

This evidence is application-level. It does not prove that an HTTP server or intermediary never reads request bytes, and it is not a generic denial-of-service certification.

## References

Fielding, R., Nottingham, M., & Reschke, J. (2022). *HTTP semantics* (RFC 9110). Internet Engineering Task Force. https://doi.org/10.17487/RFC9110

Thomson, M., & Nottingham, M. (2022). *HTTP/1.1* (RFC 9112). Internet Engineering Task Force. https://doi.org/10.17487/RFC9112
