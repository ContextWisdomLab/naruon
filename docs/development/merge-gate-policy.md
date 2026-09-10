# Merge Gate Policy

This repository's merge gate is evidence-based: required checks must pass,
review threads must be resolved, and the current PR head must have current-head
CodeRabbit or structured OpenCode App robot-review evidence. Human review is not
awaited by default.

## Required gate contract

- Required status checks must pass on the current head SHA.
- Application CI, Bandit, and pull-request image validation run on every pull
  request base, including stacked branches. Application CI and Bandit retain
  direct push checks for `develop` and `master`; image publication remains
  tag-only for `v*`. Validation concurrency is scoped by workflow, repository,
  and PR, while tag publication is never cancelled by a newer run.
- Backend Application CI must provision its own disposable PostgreSQL, install
  the Alembic history on a fresh database, repeat the upgrade, and execute the
  suite with PostgreSQL skips rejected. DB readiness, fixture collection or an
  ORM-only bootstrap is not migrated runtime evidence. Local/Actions use
  `bash scripts/ci/run_backend_postgres.sh`; preserve its redacted logs, JUnit,
  exact head and cleanup result. Optional live API skips are not live evidence.
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
- A review-like check name or status context is not publisher authentication.
  Check evidence requires the `coderabbitai` or `github-code-quality` App slug;
  status evidence requires the corresponding exact `[bot]` creator and Bot type.
  Missing or unrelated publishers cannot replace the OpenCode fallback.
  Successful and skipped check conclusions still block when their own output
  contains the blocking warning/failure evidence described above. Exclude only
  complete known clean lines (`No warnings found` and
  `No actionable comments were generated`), never the whole containing output.
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

### Multiline robot notices and collected regressions (2026-09-06)

At predecessor `550798ccafebea4b1a9a65018e63b9661ff25a53`, a multiline
CodeRabbit approval notice could be mistaken for a substantive blocker even
after an exact-head OpenCode fallback was accepted. The existing fake-GitHub
shell harness reproduced this after adding realistic line breaks: it published
a failure instead of the expected ready state. The common notice-removal
expression now uses jq's `m` flag so dot matches newlines; `s` only changes
anchor semantics. Only the non-greedy marker-delimited notice is removed;
separate blocking warnings must remain blockers. No approval or review rule
is weakened and no external GitHub mutation occurs in this harness.

Run `bash scripts/ci/test_pr_governance_gate.sh` for the full metadata scenarios.
The four-workflow stacked-base regression lives in
`backend/tests/test_stacked_pr_workflow_contract.py`, where Application CI
collects it; the root-level copy was moved, not discarded or duplicated.
Local harness evidence is not a hosted approval or protected merge.

Review finding #3939597997 exposed a second stale-notice path at
`e058f3ead35f9a19d3c3b20c6ab5fc04d2e2cbb2`: a successful current-head
CodeRabbit check or status was overwritten by an `in_progress` governance
result solely because its issue comment still carried the pending notice.
The new success-check fixture failed the expected ready assertion; the fake
publisher explicitly emitted `in_progress`. Pending notices now add a wait
only when CodeRabbit check/status evidence is absent and no qualifying
OpenCode approval exists. Existing pending/failed check handling and separate
substantive-comment blockers remain authoritative. The full shell harness
covers success checks and success statuses with stale notices separately;
the notice-only waiting fixture now correctly contains no check evidence.

Independent readiness review at `fac3437c03d928e45632763530a4f130dfe505fd`
identified two pre-existing metadata risks, not regressions introduced by the
stale-notice repair: name-only publisher matching and success/skipped results
bypassing output inspection. Six isolated fake-GitHub scenarios each emitted
an incorrect success before the fix: an unrelated App check or status creator,
each with and without the pending notice, and success/skipped checks carrying
a pre-merge blocking warning. Publisher authentication now precedes evidence
selection, and output inspection precedes conclusion acceptance. The real
current-head CodeRabbit status creator was checked as `coderabbitai[bot]`, Bot.
These are local metadata-gate findings; no protected-branch bypass or malicious
publication in production was established. Keep the full harness, authoritative
positive cases, fallback and separate-comment blockers intact when repairing
this boundary; do not grant another publisher access to silence a wait state.

Review #3944130242 exposed a regression at `b6d6c286`: output-first matching
also rejected those clean summaries. The new focused harness assertion failed
before repair. Output is now split into lines before matching whole known
clean statements; case, surrounding whitespace, CRLF and terminal punctuation
are covered. An initial whole-string regex attempt still failed and was not
accepted. Eleven scenarios cover clean success/skipped/neutral, an explicit
failure despite clean text, a separate real warning for each passing conclusion,
same-line `except`/`but` qualifications, neutral without skip evidence and an
untrusted publisher with clean text. Unknown wording remains subject to
the existing blocker policy; this is not a general natural-language negation
parser. Publisher authentication and separate-comment evidence are unchanged.

Reference: jqlang. (n.d.). *Regular expressions*. In *jq 1.7 manual*.
https://jqlang.org/manual/v1.7/#regular-expressions

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

1. Prefer branch update or rerun first.
2. If the required context cannot be emitted until the PR lands, document the
   stale context and use only a temporary, reversible ruleset adjustment.
   Capture equivalent temporary evidence before merge, such as a trusted-base
   rerun, scanner artifact, SARIF output, or manual security review evidence
   tied to the current head SHA.
3. Restore the `strix` required context after the hardened workflow emits it
   successfully on the protected branch.
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
- Restore required contexts immediately after the repaired workflow emits them.
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
