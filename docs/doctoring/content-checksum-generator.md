# Content checksum generator — standards and product boundary

**Status:** active PR candidate; not shipped until merged through protected `develop`.

**Traceability:** bounded checksum slice of issue #1247, *Build an auditable data-hygiene utility suite*.

## Product contract

Naruon's `content_checksum_generator` compares the exact UTF-8 byte sequence supplied by the caller. It deliberately does **not** Unicode-normalize input before hashing, because normalization would change the byte-level evidence being compared. The deterministic tool accepts at most 1,048,576 UTF-8 bytes per invocation and exposes only these normal-surface algorithms:

- `sha256` — SHA-256 from FIPS 180-4;
- `sha3_256` — SHA3-256 from FIPS 202;
- `blake2b_256` — BLAKE2b with a 256-bit digest, using the BLAKE2 construction standardized in RFC 7693.

MD5 and SHA-1 are intentionally absent from the normal surface. NIST states that SHA-1 is being transitioned out for applying cryptographic protection by December 31, 2030; Naruon therefore does not introduce SHA-1 as a new customer-facing checksum choice. No legacy-compatibility checksum mode is part of this slice.

A returned digest is an equality/integrity fingerprint for the exact supplied bytes. It does not authenticate a sender, prove provenance, or replace a keyed MAC or digital signature. Customer-facing output carries that warning with every result so the next action is explicit: compare the digest with an independently obtained expected digest when checking content equality; use an authenticated construction when sender or origin authenticity matters.

## Standards status reviewed 2026-09-10

The official NIST publication page still lists FIPS 180-4 (2015) as the final Secure Hash Standard. NIST's March 7, 2023 Crypto Publication Review Board decision says FIPS 180-4 will be revised, including removal of the SHA-1 specification, but that decision is a revision plan rather than a replacement final standard. The official NIST/CSRC publication page still lists FIPS 202 (2015) as the final SHA-3 standard and carries a planning note that NIST decided to update it. NIST's March 12, 2025 decision says FIPS 202 will be updated and SP 800-185 revised through the normal draft/public-comment process. A fresh primary-source review on 2026-09-10 found no successor final publication, so Naruon continues to cite the existing final standards while separately recording the announced revisions. RFC 7693 remains the RFC Editor publication describing BLAKE2.

The implementation uses Python's standard-library `hashlib` bindings only; this slice adds no external cryptographic dependency and no model-mediated decision path. Deterministic checksum behavior therefore remains independent of LLM judgment and credentials.

## Research grounding

Two primary peer-reviewed cryptography papers are directly relevant to the non-SHA-2 choices in this bounded surface:

- Bertoni, Daemen, Peeters, and Van Assche (2008) prove the indifferentiability properties of the sponge construction that underpins Keccak/SHA-3. That work supports treating SHA-3 as a distinct, standardized sponge-based hash construction rather than an alias for SHA-2.
- Aumasson, Neves, Wilcox-O'Hearn, and Winnerlein (2013) introduce BLAKE2 and describe BLAKE2b as the 64-bit-oriented variant, including its software-performance and security design goals. That primary design paper is the research basis for exposing BLAKE2b only under an explicit 256-bit output identifier rather than as an ambiguous generic `blake2` option.

No paper PDF is committed in this slice because redistribution permission for the publisher versions was not established from the primary publication records during this review. The citations and DOI links below are therefore the auditable research traceability; this avoids assuming redistribution rights merely because a paper can be viewed online.

## Acceptance evidence

The regression contract covers published/stable `abc` digest vectors for all three algorithms, exact-byte distinction between canonically equivalent Unicode strings, rejection of SHA-1/MD5 and ambiguous aliases, rejection of text that cannot be represented as valid UTF-8 Unicode scalar values, the one-MiB UTF-8 boundary, and idempotent application registration. Protected-branch integration still requires exact-current-head CI, security, **100% owned production statement/branch coverage where exposed as required by [ADR-0007](../adr/0007-bounded-content-checksum-surface.md)**, and independent review gates before the capability may be described as shipped.

## References (APA 7th)

Aumasson, J.-P., Neves, S., Wilcox-O'Hearn, Z., & Winnerlein, C. (2013). BLAKE2: Simpler, smaller, fast as MD5. In *Applied cryptography and network security* (Lecture Notes in Computer Science, Vol. 7954, pp. 119–135). Springer. https://doi.org/10.1007/978-3-642-38980-1_8

Bertoni, G., Daemen, J., Peeters, M., & Van Assche, G. (2008). On the indifferentiability of the sponge construction. In *Advances in cryptology – EUROCRYPT 2008* (Lecture Notes in Computer Science, Vol. 4965, pp. 181–197). Springer. https://doi.org/10.1007/978-3-540-78967-3_11

National Institute of Standards and Technology. (2015). *Secure hash standard (SHS)* (FIPS PUB 180-4). U.S. Department of Commerce. https://doi.org/10.6028/NIST.FIPS.180-4

National Institute of Standards and Technology. (2015). *SHA-3 standard: Permutation-based hash and extendable-output functions* (FIPS PUB 202). U.S. Department of Commerce. https://doi.org/10.6028/NIST.FIPS.202

National Institute of Standards and Technology. (2022, December 15). *NIST transitioning away from SHA-1 for all applications* (updated February 3, 2025). https://www.nist.gov/news-events/news/2022/12/nist-transitioning-away-sha-1-all-applications

National Institute of Standards and Technology. (2023, March 7). *Decision to revise FIPS 180-4, Secure Hash Standard (SHS)* (updated February 3, 2025). https://www.nist.gov/news-events/news/2023/03/decision-revise-fips-180-4-secure-hash-standard-shs

National Institute of Standards and Technology. (2025, March 12). *Decision to update FIPS 202 and revise SP 800-185*. Computer Security Resource Center. https://csrc.nist.gov/News/2025/decision-to-update-fips-202-and-revise-sp-800-185

Saarinen, M.-J. O., & Aumasson, J.-P. (2015). *The BLAKE2 cryptographic hash and message authentication code (MAC)* (RFC 7693). RFC Editor. https://doi.org/10.17487/RFC7693
