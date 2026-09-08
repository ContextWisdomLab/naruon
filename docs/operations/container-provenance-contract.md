# Container provenance contract

Naruon container images must be reproducible from reviewable, immutable base-image inputs.

## Required invariants

- Every production `FROM` instruction uses both a human-readable image tag and a full `sha256` digest.
- The root, backend, connector, and frontend Dockerfiles keep shared Python and Node base references synchronized where the runtime contract is shared.
- OCI `org.opencontainers.image.base.name` and `org.opencontainers.image.base.digest` annotations are derived from the actual first Dockerfile stage rather than duplicated constants.
- `OCI_IMAGE_BASE_DIGEST` and `OCI_IMAGE_BASE_NAME` are mandatory build arguments. Dockerfiles fail closed when a publishing or validation path omits either value.
- Published multi-platform images preserve annotations at both the manifest and index levels.
- Pull-request validation resolves the pinned Ollama manifest and fails closed when either `linux/amd64` or `linux/arm64` is absent.
- Dependency and image security pins remain governed by executable repository tests; a dependency upgrade must update its hash-locked artifact and the corresponding regression contract together.
- Backend `cryptography==50.0.0` and `protobuf==7.35.1`, Strix `cryptography==50.0.0` and `protobuf==6.33.6`, frontend source pins `postcss==8.5.24` and `jsdom==^30.0.1`, generated-lock resolutions `postcss==8.5.24` and `jsdom==30.0.1`, and the `brace-expansion==5.0.9` and `undici==8.9.0` overrides are parsed and checked structurally.

## Change procedure

1. Update the tag-and-digest reference in the canonical Dockerfile.
2. Synchronize every Dockerfile that shares that runtime.
3. Regenerate affected hash locks without weakening `--require-hashes` installation.
4. Update `CHANGELOG.md` when the runtime or published artifact changes.
5. Run release-governance, repository-hygiene, dependency-pin, application, image-build, and security checks on the exact pull-request head.
6. Merge only after independent review confirms that the OCI annotations describe the image that is actually built.

A mutable tag by itself, a digest without its reviewable tag, an omitted mandatory base-metadata argument, or an annotation that does not match the first stage violates this contract.

## Standards interpretation

The OCI Image Format is the authoritative interoperability contract for image manifests, indexes, configurations, and descriptors. Naruon derives its base-image annotations from the Dockerfile actually used for the build so the published metadata cannot silently diverge from the reviewed build input.

SLSA Build Provenance 1.2 describes provenance as verifiable information about where, when, and how an artifact was produced. It treats externally supplied build parameters as untrusted inputs that must be recorded and verified downstream. Naruon's tag-and-digest base references, exact workflow revision, and generated dependency locks are therefore reviewable build inputs rather than decorative metadata. This repository does not claim a SLSA level solely because it emits OCI annotations.

NIST SP 800-218, SSDF 1.1, recommends protecting software and verifying third-party components throughout the development and delivery lifecycle. Naruon implements that guidance through immutable action and image pins, generated hash locks, exact-head tests, vulnerability scans, and independent review. The newer SSDF 1.2 document remains an initial public draft as of August 2026 and is informative rather than the formal conformance baseline.

## References

National Institute of Standards and Technology. (2022). *Secure software development framework (SSDF) version 1.1: Recommendations for mitigating the risk of software vulnerabilities* (NIST Special Publication 800-218). https://doi.org/10.6028/NIST.SP.800-218

Open Container Initiative. (2025). *OCI image format specification* (Version 1.1.1). https://github.com/opencontainers/image-spec/tree/v1.1.1

Supply-chain Levels for Software Artifacts. (2025). *Build provenance* (SLSA specification Version 1.2). https://slsa.dev/spec/v1.2/build-provenance
