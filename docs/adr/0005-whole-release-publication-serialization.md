# ADR-0005: Serialize Docker release image sets at the reusable-workflow caller

- **Status:** Proposed
- **Date:** 2026-09-09
- **Owner:** Naruon release publication
- **Implementation:** PR #1621; not protected-branch authority until normally merged

## Problem

Naruon publishes backend, combined `naruon`, and frontend container images from one version tag. Per-component concurrency prevents two backend jobs, two frontend jobs, or two combined-image jobs for the same ref from evicting one another, but it does not make the three-image release a serialized set. Two workflow runs for the same tag/ref can otherwise interleave their component publications. A downstream deployment that depends only on completion of its own matrix can then run while another same-ref publication is also mutating release tags.

The release boundary therefore needs one lock whose lifetime covers all three image publications while preserving parallelism inside a single release.

## Constraints

- PR image validation keeps #1592's first-attempt cancellation identity; manual reruns must not be cancelled by a newer first-attempt event.
- Tag publication must never cancel an in-progress release for the same repository/ref.
- A queued same-ref release must not replace an earlier pending release merely because it arrived later.
- Backend, combined, and frontend images should still build in parallel inside one release.
- Existing tag/`VERSION` equality checks, multi-architecture builds, OCI metadata, SBOM, provenance, digest evidence, and AKS deployment ordering must remain intact.
- The design must use supported GitHub Actions primitives rather than a repository-local lock service or mutable external coordination record.

## Decision

Keep `.github/workflows/docker-publish.yml` as the event-facing caller. PR image validation remains there. Move tag image publication into `.github/workflows/docker-release-images.yml` as a local reusable workflow invoked with `workflow_call`.

The caller `publish_images` job holds one concurrency group for the entire called workflow:

```yaml
concurrency:
  group: Build and Publish Docker Images-publish-set-${{ github.repository }}-${{ github.ref }}
  queue: max
  cancel-in-progress: false
```

The called workflow owns the backend/naruon/frontend matrix and therefore keeps those three builds parallel after the caller acquires the release-set lock. `deploy_preflight` continues to need the caller job, so deployment remains downstream of completion of every matrix child in the called workflow.

GitHub's current Actions contract documents `queue: max` for workflow/job concurrency, with up to 100 pending jobs or runs in one concurrency group, and disallows combining it with `cancel-in-progress: true`. GitHub also documents `jobs.<job_id>.concurrency` and `jobs.<job_id>.permissions` as supported keywords for jobs that call reusable workflows.

## Alternatives considered

### Keep per-component release groups

Rejected as the complete solution. It prevents a backend publication from evicting another backend publication, but release A and release B can still interleave different components. That is component safety, not release-set serialization.

### Put one queued group on the entire mixed PR/tag workflow

Rejected. PR validation intentionally cancels superseded first attempts while tag publication must queue without cancellation. `queue: max` and `cancel-in-progress: true` are incompatible in one concurrency mapping, and weakening #1592's PR-rerun identity would reintroduce a repaired CI invariant.

### Serialize all three image builds inside one non-matrix job

Rejected. It would establish a lock but unnecessarily removes safe component parallelism and lengthens release publication without improving the release-set invariant.

### Use an environment or external lock service

Rejected for this boundary. Environments introduce deployment/protection semantics not required for image publication, while an external lock adds mutable coordination state and another availability/security dependency when GitHub Actions already provides the required repository/ref queue primitive.

## Consequences

- Same-repository/same-ref release executions are serialized at the release-set boundary.
- Backend, combined, and frontend publications remain parallel within one admitted release.
- Up to 100 later same-group jobs/runs may wait; requests beyond the platform bound can be rejected and must not be described as guaranteed delivery.
- Different tag refs remain independent release groups and can run concurrently.
- Release implementation is split across an event-facing caller and a reusable publication workflow, so governance tests and operations documentation must read both files rather than assuming one workflow contains both PR validation and release publication.
- The decision is **Proposed** until the implementation is normally integrated into protected `develop` and exact-head workflow/review evidence is complete. A predecessor run or a source-only test is not release acceptance.

## Verification and traceability

- Reality RED: `86ea64021487c6b2c9897832d5645db7fbe3b7d7` — requires one whole-set caller lock and a reusable release boundary.
- Source repair: `c8b565ec7b38cd84bf980be9a6672fafe3bd126c` — introduces the caller lock and reusable release matrix.
- Governance contract repair: `e4ab2abd5e1108fbf2acfdd06e6ce42f61d30495` — moves release-only assertions to the reusable workflow and keeps caller+called composition checks.
- Focused regression: `backend/tests/test_docker_workflow_concurrency.py`.
- Broader release contract: `backend/tests/test_release_governance.py`.
- Operability description: `docs/operations/release-deployment-architecture.md`.
- Primary platform authority: GitHub, *Workflow syntax for GitHub Actions*, `jobs.<job_id>.concurrency`; GitHub, *Reusing workflow configurations*, supported keywords for reusable-workflow caller jobs. Accessed 2026-09-09.

## Follow-up

After #1592 and the applicable protected-base security prerequisite land normally, restack/retarget #1621 without dropping this boundary. Require one unchanged exact head with the then-live repository and central required checks terminal-success plus qualifying independent review. The first real tag publication after protected integration must retain digest, SBOM, provenance, and rollback evidence; failure of any component keeps deployment blocked.