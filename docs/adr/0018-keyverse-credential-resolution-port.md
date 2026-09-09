# ADR-0018: Consume Keyverse credentials through a value-free application port

- Status: Proposed
- Date: 2026-09-10
- Scope: Naruon runtime credential acquisition
- Related: ContextualWisdomLab/.github#2063, ContextualWisdomLab/keyverse#129, #151, #153

## Context

Naruon currently has bootstrap/runtime settings that can be sourced through Pydantic environment and dotenv discovery. Several tenant-scoped provider and mailbox credentials already live in Naruon-owned encrypted persistence, but root runtime material such as session-signing and encryption keys still requires a migration boundary.

Keyverse is the intended CWL credential authority. Its workload credential data plane, however, is not yet an immutable released dependency. Reading an open Keyverse PR, querying Keyverse tables, copying its encryption implementation, or silently falling back to `.env` after a failed future cutover would violate the repository and organization boundaries.

Naruon therefore needs a consumer-owned port before it needs a transport adapter. The port must express exactly which credential is requested without carrying its secret value in logs, configuration objects, PR fixtures, or interoperability metadata.

## Decision

Naruon introduces `core.credential_resolution` as an application port with these value-free identity dimensions:

- credential authority;
- tenant/workspace identity;
- deployment environment;
- secret namespace;
- secret key;
- immutable/versioned secret identifier;
- runtime purpose.

The port returns a resolved credential only through an implementation of `CredentialResolver`. Until Keyverse publishes and Naruon pins an immutable workload credential-resolution contract, `UnavailableCredentialResolver` is the only integration state introduced by this ADR and fails closed.

This PR does **not** replace current bootstrap settings and does not claim `.env` removal. It creates the seam required for a later shadow-verification and cutover stack. The future Keyverse adapter must authenticate the workload with released identity semantics, bind the request to the reference above, verify TLS/authority, honor version/revocation/lease rules, reject stale or expired material, and provide no environment/dotenv/plaintext-database fallback.

## Alternatives considered

### Import Keyverse source or query its database

Rejected. That couples Naruon to owner internals and an unreleased schema rather than a released bounded-context contract.

### Keep using environment variables as the long-term credential interface

Rejected. Environment and dotenv are process bootstrap transports, not an auditable credential authority with namespace, version, revocation, and workload authorization semantics.

### Build a Naruon-local second vault

Rejected. Naruon owns its product/runtime policy but not the CWL-wide credential authority. A second vault would duplicate custody, rotation, revocation, and audit responsibilities.

## Consequences

Naruon can prepare callers, test doubles, outage behavior, and configuration migration without pretending the Keyverse data plane is already released. The cost is a staged migration: existing root runtime configuration remains until the owner contract is released and an adapter passes shadow, rotation, revocation, outage, rollback, and clean-start acceptance.

The `Proposed` status is intentional. It must not be promoted to `Accepted` solely because this PR merges; acceptance requires an immutable Keyverse owner release plus Naruon integration evidence on the protected branch.

## Verification requirements

Before production cutover:

1. pin an immutable Keyverse workload credential API/client/schema release;
2. verify the workload identity and tenant/environment/purpose binding end to end;
3. exercise current and rotated secret versions and revoked/expired denial;
4. verify Keyverse outage fails closed without `.env`, environment, local-file, or local-vault secret fallback;
5. verify resolved values are absent from logs, traces, metrics, artifacts, browser bundles, exception rendering, and LLM inputs;
6. run Naruon's protected-branch backend, security, CodeQL, dependency, image, coverage, and independent-review gates on one exact head;
7. only then remove the corresponding legacy dotenv/environment discovery paths in a successor change.
