# Release and Deployment Architecture

## 확인된 사실 / Confirmed

- `ARCHITECTURE.md` defines the current runtime as Next.js frontend → FastAPI
  backend → PostgreSQL with pgvector, with the protected-document LLM provider
  description tracked separately as governance drift until its canonical repair
  lands.
- `docker-compose.yml` is the local development stack for db/backend/frontend.
- `.github/workflows/app-ci.yml` runs backend pytest and frontend test/lint/build
  checks on pull requests without release-branch push duplication.
- `.github/workflows/docker-publish.yml` is the event-facing Docker workflow. It
  validates backend/frontend/combined images on supported PR bases and accepts
  `v*` tag events only for release publication.
- PR #1621 proposes a release boundary in which the tag caller invokes
  `.github/workflows/docker-release-images.yml`; that reusable workflow owns the
  backend/naruon/frontend publication matrix, exact tag/`VERSION` equality check,
  stable `X.Y.Z` version validation, OCI metadata, multi-architecture GHCR
  publishing, SBOM, provenance, and digest evidence. This is **active-PR
  evidence, not protected-branch authority** until the stack is normally merged.
- Under the #1621 proposal, the caller `publish_images` job holds one
  repository+ref concurrency group with `queue: max` and
  `cancel-in-progress: false` for the full reusable-workflow execution. This
  serializes same-ref release image sets while leaving the three component builds
  parallel inside one admitted release. See
  [`ADR-0005`](../adr/0005-whole-release-publication-serialization.md).
- The release workflow disables docker/metadata-action automatic latest handling
  and declares `latest` explicitly only after `VERSION` has passed the stable
  `X.Y.Z` guard. A prerelease/build-suffixed `VERSION` fails before registry
  publication rather than moving `latest` to an unstable image.
- `deploy_preflight` and `deploy_to_aks` depend on completion of the release
  publication caller, so an AKS deployment cannot start until the whole called
  image matrix succeeds.
- `docker-compose.live-e2e.yml` is the live E2E stack: it uses pre-built images,
  seeds deterministic email data, scales backend replicas, and exposes the stack
  through nginx at `127.0.0.1:18080`.

## 플랫폼 제약 / Platform constraints

GitHub Actions currently permits `queue: max` on concurrency groups, allowing up
to 100 pending jobs or workflow runs in one group; additional members can be
rejected when that bound is reached. `queue: max` cannot be combined with
`cancel-in-progress: true`. Reusable-workflow caller jobs support `concurrency`
and `permissions`. These platform facts are part of the release design rather
than an application-level guarantee: Naruon does not promise unbounded release
queueing.

Docker metadata-action v6.2.0 uses `flavor.latest` to control automatic latest
handling. Naruon sets `latest=false` there and keeps one explicit raw `latest`
tag after the stable-version guard, avoiding a second implicit latest source.

Primary references, accessed 2026-09-09:

- GitHub. *Workflow syntax for GitHub Actions* — `jobs.<job_id>.concurrency`.
- GitHub. *Reusing workflow configurations* — supported keywords for jobs that
  call reusable workflows.
- Docker. *metadata-action v6.2.0 README* — flavor/latest and semver guidance at
  exact action commit `dc802804100637a589fabce1cb79ff13a1411302`.

## 가설 / Hypothesis

- The next protected release candidate should verify backend, combined `naruon`,
  and frontend GHCR manifests for `linux/amd64` and `linux/arm64` before
  production promotion.
- Deployment promotion should use image digests rather than mutable tags after
  the tag workflow produces digest evidence.
- The first tag execution after ADR-0005 reaches protected `develop` is required
  release evidence for the whole-set serialization path; source regression tests
  or predecessor PR checks do not prove an actual publication run.

## 운영 절차 / Operating path

1. Build images locally or in CI from the release branch and run the full
   repository security/test gates on one exact head.
2. Run live Docker E2E against the candidate images and preserve the evidence.
3. Confirm that `VERSION` is stable numeric `X.Y.Z`, the planned tag is exactly
   `v$(cat VERSION)`, CHANGELOG and required review state are current, and SBOM /
   provenance plus rollback expectations are recorded. Do not use this path for
   prerelease/build-suffixed versions.
4. Push `v$(cat VERSION)` only after the protected source and review evidence are
   current. Do not recreate or move a release tag to manufacture a rerun.
5. Let the release-set caller acquire the same-ref publication lock; backend,
   combined, and frontend image jobs may run in parallel only inside that one
   admitted set.
6. Require all component publications to succeed before deployment preflight.
   A failed image publication blocks deployment rather than publishing a clean
   release claim for a partial set.
7. Record GHCR digests, manifest platforms, SBOM/provenance receipts, live E2E
   evidence, GitHub Release/tag identity, and rollback instructions in the
   release evidence record.
