# ADR-0007: Bound the customer content-checksum algorithm surface

**Status:** Proposed

**Date:** 2026-08-15

**Decision owner:** Naruon maintainers

**Capability maturity:** deterministic tool contract proposed on an unmerged branch; production authority requires protected-branch integration and verification

**Scope:** Naruon's customer-facing deterministic content-checksum utility only. This ADR does not define sender authentication, signatures, password hashing, key derivation, or external artifact-signing policy.

**Related issue:** #1247

## Context

A checksum utility is useful for comparing exported email/document text, audit evidence, and workflow payloads, but an unconstrained generic hash selector creates two avoidable product risks. First, legacy algorithms such as MD5 or SHA-1 can be misread as recommended security controls. Second, digest output can be mistaken for proof of who produced a value even though an unkeyed hash authenticates neither sender nor origin.

Naruon's deterministic tool registry already supplies a stable execution boundary. The smallest defensible slice is therefore an explicit modern algorithm allowlist with bounded exact-byte input and a machine-visible authenticity warning, rather than a wrapper over arbitrary `hashlib` names.

## Decision

1. The normal customer surface accepts exactly `sha256`, `sha3_256`, and `blake2b_256`.
2. MD5, SHA-1, aliases, case variants, and unknown names fail closed; no compatibility guessing is performed.
3. Text is encoded as UTF-8 exactly as supplied and is not Unicode-normalized before hashing.
4. One invocation accepts at most 1,048,576 encoded bytes so the generic tool endpoint cannot become an unbounded hashing sink.
5. The result records the selected algorithm, hexadecimal digest, encoded byte length, encoding, and an explicit warning that the digest does not authenticate a sender or replace a MAC/signature.
6. The implementation uses the Python standard library and remains deterministic and independent of model judgment or LLM credentials.
7. A future legacy compatibility mode requires a separate reviewed decision with an explicit non-security acknowledgement; this ADR does not authorize one.

## Consequences

- Buyers can compare exact content evidence without being steered toward a legacy digest.
- Canonically equivalent Unicode strings may intentionally produce different digests when their UTF-8 byte sequences differ; this is correct for exact-byte evidence.
- Callers that need origin authenticity must select an authenticated construction outside this tool.
- Algorithm expansion is a product/security decision rather than a free-form runtime option and requires tests plus standards review.

## Verification

The implementation contract requires stable vectors for all three algorithms, exact UTF-8 behavior, equivalence with incremental hashing of the same UTF-8 byte sequence across chunk boundaries, rejection of non-allowlisted names, byte-boundary tests, idempotent registry startup, 100% owned production statement/branch coverage where exposed, and current-head security/review gates before protected integration.

This ADR remains Proposed while the implementation is outside protected `develop`. It may be marked Accepted only after the decision and its exact implementation are normally integrated under the live protected-branch contract; a Draft PR or passing branch-local test suite is not acceptance authority.

Standards status and APA 7 references are maintained in [`docs/doctoring/content-checksum-generator.md`](../doctoring/content-checksum-generator.md).

## Alternatives rejected

- **Expose every `hashlib` algorithm:** transfers a cryptographic policy decision to callers and makes legacy options look supported.
- **Default to SHA-1 or MD5 for interoperability:** creates a new normal-surface dependency on algorithms Naruon should not recommend for security-labelled use.
- **Normalize Unicode before hashing:** destroys the exact byte-level comparison contract and can make different source evidence converge silently.
- **Describe a digest as authentication:** an unkeyed checksum does not establish sender or provenance identity.