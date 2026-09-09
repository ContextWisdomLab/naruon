# Keyverse credential-resolution consumer boundary — standards doctoring

Observed Naruon base: `develop@042b0c70531b229af3acbd0421a2f23098d848b3`  
Consumer PR: `#1630`  
Decision record: `docs/adr/0018-keyverse-credential-resolution-port.md`

## Evidence and interpretation

NIST SP 800-207 rejects implicit trust based only on network location and treats authentication and authorization as explicit decisions before access to an enterprise resource. SP 800-207A carries that principle into cloud-native applications and specifically describes application/service identity as an access-control input; it cites workload identity infrastructure such as SPIFFE as part of the enforcement architecture.

SPIFFE's stable Workload API specification standardizes how a running workload obtains and validates cryptographic workload identity. Its caller-identification requirement is relevant to the future Keyverse adapter: merely reaching a local or network endpoint is not sufficient authority to resolve a secret. The credential request must be bound to an authenticated workload identity and the requested resource dimensions.

OWASP's Secrets Management Cheat Sheet recommends centralized secret storage/provisioning and explicitly treats auditing, rotation, revocation, and expiration as lifecycle requirements. It calls for audit evidence covering who or what requested a secret, approval/rejection, use, expiration, authentication/authorization errors, and administrative updates.

These sources support the following Naruon-side constraints, without defining Keyverse's owner implementation:

1. `CredentialReference` remains value-free and names tenant, environment, namespace, key, version, purpose, and authority so authorization can be resource-specific rather than inferred from network reachability.
2. The future adapter must present a verifiable workload identity and fail closed when identity, authorization, version, revocation, expiration, or authority validation fails.
3. Rotation and revocation are owner lifecycle semantics. Naruon must consume them through the released Keyverse contract rather than reconstructing them from local timestamps or a duplicate vault.
4. Secret values must not appear in reference metadata or routine object rendering. Audit/event records should identify the request and outcome without carrying the secret itself.
5. An unavailable or unreleased Keyverse data plane does not authorize fallback to `.env`, plaintext configuration, or a Naruon-local second credential authority. Existing bootstrap mechanisms remain an explicitly tracked migration state until a verified cutover; they are not silently reclassified as the target architecture.

## What these sources do not establish

The cited standards do not prove that the current Keyverse open PRs provide a production workload secret API, nor do they select a particular transport, KMS, HSM, lease duration, or secret-storage schema for Keyverse. Those are owner decisions and require immutable release evidence before Naruon adopts them.

## APA 7 references

Chandramouli, R., & Butcher, Z. (2023). *A zero trust architecture model for access control in cloud-native applications in multi-cloud environments* (NIST Special Publication 800-207A). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-207A

OWASP Foundation. (n.d.). *Secrets management cheat sheet*. OWASP Cheat Sheet Series. https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

Rose, S., Borchert, O., Mitchell, S., & Connelly, S. (2020). *Zero trust architecture* (NIST Special Publication 800-207). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-207

SPIFFE. (n.d.). *SPIFFE Workload API*. https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
