# Merge Gate Policy

This repository's merge gate is evidence-based: required checks must pass,
review threads must be resolved, and the current PR head must have current-head
CodeRabbit or structured OpenCode App robot-review evidence. Human review is not
awaited by default.

## Required gate contract

- Required status checks must pass on the current head SHA.
- Application CI must run backend pytest and frontend test/lint/build checks on
  pull requests to `master` and `release/**`, while release-branch pushes must
  not create duplicate check noise; push checks are scoped to `master`.
- The robot-review gate prefers CodeRabbit evidence. When the current head has
  CodeRabbit check-run evidence, it satisfies the gate only when current-head
  blocking findings, warnings, and failures are fixed, rebutted with evidence,
  or superseded. Authoritative current-head `Review skipped` evidence satisfies
  that path only when applicable. When no CodeRabbit check-run exists, the gate
  waits for an exact-current-head `APPROVED` review from the `opencode-agent`
  GitHub App. The review body must name the head SHA and include structured
  adversarial validation with `status=passed` and at least two probes whose
  outcome is `falsified`. Stale-head reviews, `github-actions` reviews, and
  insufficient probe evidence do not satisfy the gate.
- PR Governance automation is metadata-only: it must not checkout pull request
  code, clone the head branch, dismiss reviews, enable auto-merge, or use admin
  merge. It may read PR/check/review-thread metadata and post blocker comments;
  the separate human/agent landing path performs any allowed merge action after
  current-head gates are satisfied. Submitted and dismissed review events rerun
  the metadata controller so OpenCode App evidence updates the gate promptly.
- PR Governance runs trusted-base logic only. The workflow materializes the base
  repository script from a trusted tarball and must not execute PR-head scripts.
  Trusted tarball materialization uses bounded retry plus archive validation for
  transient GitHub API truncation and fails closed instead of falling back to
  PR-head or local scripts.
- Pending, queued, requested, waiting, or in-progress checks are wait states, not
  hard failure findings. Success, pass, skipped, and neutral states satisfy the
  gate. Every other required-check state — including failed, cancelled,
  timed-out, action-required, and any unrecognized state — is a blocker: the
  gate fails closed rather than passing states it does not understand.
- If gate evaluation itself errors (for example a transient GitHub API
  failure), the gate publishes a completed/failure check-run instead of leaving
  a previously published result in place.
- Gate blocker comments publish sanitized check names and generic error text
  only; raw CLI diagnostics stay in the workflow run log. Inside Actions the
  gate runs with a pinned system PATH so earlier steps cannot influence tool
  resolution via GITHUB_PATH.
- Authoritative `Review skipped` evidence counts only when the same check
  output carries no blocking warning/failure language alongside it.
- `reviewDecision=CHANGES_REQUESTED` is a blocker until requested changes are
  addressed or superseded on the current head.
- Blocker comments use the idempotent
  `<!-- pr-governance:metadata-gate -->` marker and are patched in place instead
  of duplicated on repeated workflow events.
- GitHub rulesets must use `required_approving_review_count=0` so GitHub does
  not require a human `APPROVED` review when robot-review policy applies.
- GitHub rulesets must keep `required_review_thread_resolution=true`.
- CodeRabbit `request_changes_workflow` stays enabled so the robot can clear
  its own requested-changes review after comments are resolved. CodeRabbit
  GitHub Checks integration stays disabled because GitHub Actions are already
  evaluated by required checks and PR Governance; duplicating that gate inside
  CodeRabbit can strand stale GitHub `CHANGES_REQUESTED` review objects when an
  unrelated scanner is temporarily failing.
- Bypass actors must not be configured for routine delivery.
- Security workflows and scanners are required gates, not optional paths.

## Evidence commands

Use the same head SHA across all checks:

```bash
gh pr view <pr> \
  --json number,headRefOid,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup
gh pr checks <pr> --required
gh api repos/<owner>/<repo>/pulls/<pr>/reviews
gh api repos/<owner>/<repo>/commits/<sha>/check-runs
gh api repos/<owner>/<repo>/rulesets --jq '.[] | {name, enforcement, rules}'
```

## Robot review versus GitHub approval

CodeRabbit review/check evidence satisfies this repo's preferred robot-review
path only after current-head blocking comments, pre-merge warnings, and failure
findings are resolved or superseded. When CodeRabbit evidence is absent, an
exact-current-head `APPROVED` review from the `opencode-agent` GitHub App may
satisfy the fallback path only with the structured adversarial evidence defined
above. A `github-actions` review or an overview comment is not authoritative App
approval. If GitHub reports a missing approving review despite valid robot
evidence, inspect the ruleset before waiting for a human review. The expected
setting is `required_approving_review_count=0`.

## Stale required contexts

A required context can become stale when the PR is fixing the workflow that
emits it. For example, PRs that fix Strix may be blocked by a required `strix`
context before the hardened Strix workflow can emit a valid result.

Handling policy:

This procedure requires explicit maintainer authorization for the exact ruleset
change and substitute evidence. A delivery request alone is not authorization
to weaken a required gate; without it, repair or rerun the canonical owner.

1. Prefer branch update or rerun first.
2. If the required context cannot be emitted until the PR lands, document the
   stale context and use only a temporary, reversible ruleset adjustment.
   Capture equivalent temporary evidence before merge, such as a trusted-base
   rerun, scanner artifact, SARIF output, or manual security review evidence
   tied to the current head SHA.
3. Restore the captured configuration on success, failure, cancellation, or
   expiry. If repair fails, restore before pursuing a different approach.
4. Re-run required-check evidence after restore.

## PR #108/#109 evidence summary

- PR #108 exposed the merge-gate ambiguity: CodeRabbit/robot-review evidence was
  conflated with a GitHub `APPROVED` review, while ruleset configuration could
  still require human approval despite repo policy.
- Issue #109 documents the durable fix: distinguish robot-review evidence from
  GitHub approval objects, keep human approval count at zero, preserve review
  thread resolution, and handle stale `strix` required contexts with explicit
  rollback.
- The root cause was policy/evidence mismatch, not lack of human review.

## Rollback and recovery

- Do not add bypass actors, disable security checks, dismiss reviews, or use admin
  merge for normal delivery.
- Any temporary ruleset change must have captured before/after JSON, owner,
  expiry, head SHA, equivalent temporary evidence, and a named restore
  condition.
- Restore required contexts on success, failure, cancellation, or expiry;
  verify restoration before any further landing.
- If the platform still rejects merge after policy-aligned settings and passing
  checks, record the rejection as an external blocker with the exact command
  output and head SHA.

## Related operations docs

- `docs/operations/release-deployment-architecture.md`
- `docs/operations/open-source-apm.md`
- `docs/operations/email-relay-proxy-boundary.md`
- `docs/operations/postgresql-physical-replication.md`
- `docs/operations/auth-key-management.md`
- `docs/operations/traefik-evaluation.md`
