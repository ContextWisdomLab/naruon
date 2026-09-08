# AGENTS.md

<!-- BEGIN cwl-agent-guidance -->
## Agent guidance (CWL governance)

This section applies to every agent (Claude, Codex, Cursor, opencode, …) working
in this repo.

### Security Scan gate

- Every PR runs the central **Security Scan** required gate: `osv-scan` +
  `dependency-review` (diff-scoped) and `trivy-fs` (repo-wide, CRITICAL/HIGH,
  fixable only). It runs on every PR base branch, **including stacked PRs**.
- A failing **`trivy-fs` is a REAL finding, not a flake.** Read the job log — it
  prints each finding's rule id / severity / file — or open the run's SARIF
  results. Then **remediate**: bump the vulnerable dependency (this repo pins
  Python deps in `requirements-*.txt`), fix the `Dockerfile` /
  `docker-compose.*.yml` / `k8s/*.yaml` misconfig, or add a narrow, documented
  `.trivyignore` / `.trivyignore.yaml` entry for a genuine false positive. Never
  weaken, `continue-on-error`, or disable the gate.
- **Worked example (currently blocking PRs here):** KSV-0118 (`runAsNonRoot`
  unset) and KSV-0014 (`readOnlyRootFilesystem` unset), both HIGH k8s
  misconfigs, fire on `k8s/*.yaml` because the Deployments/StatefulSet have no
  `securityContext`. Fix by adding the container `securityContext`
  (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, plus writable volume
  mounts as needed) — do not ignore it.
- A local `trivy` scan with a stale DB misses findings: run
  `trivy image --download-db-only` first, and scan the **merge ref**, not just the PR
  head.
- The org `code_scanning` ruleset is intentionally **CodeQL-only** (multiple
  code-scanning tools can't converge on one PR ref). Gating is enforced by the
  Security Scan **job result**, not by that rule — do **not** add Trivy,
  Scorecard, or other tools to the `code_scanning` rule.

### Code exploration

- When CodeGraph is available, check `codegraph status` before architecture or
  symbol exploration. Initialize a missing index with `codegraph init`, repair a
  stale or unhealthy index with `codegraph sync`, and use `codegraph explore`
  before broad searches. Otherwise use focused `rg` and file reads. Keep graph
  artifacts local unless repository policy requires them.

### Config & secrets (KV, not env)

- **Org rule:** do **not** read config/secrets via `os.getenv()` / raw
  environment variables at runtime. Read them from a KV / credential registry.
  Org Actions secrets (e.g. `OPENAI_API_KEY`) flow **into** the KV via a
  bootstrap/CI step; runtime reads from the KV — env is only transport into the
  KV, never the runtime source. The reference implementation is
  xtrmLLMBatchPython's pgcrypto-encrypted Postgres credential registry
  (`get_credential(name)`); reuse that pattern (a DB-backed KV is fine) unless a
  dedicated KV is adopted.
- **Applies here:** this service authenticates to external systems (OpenAI, plus
  SMTP/IMAP/POP3 mail) and holds signing/encryption secrets, so new config and
  credentials belong in the registry, not scattered `os.getenv` reads.
- **Already aligned — keep it this way:** per-tenant provider and mail
  credentials (OpenAI keys, mailbox passwords) are stored in the DB-backed,
  Fernet-encrypted tenant credential store and read from there at runtime (see
  `backend/services/llm_provider_selection.py`, `backend/api/tenant_config.py`),
  not from environment variables. Add any new tenant/app secret to that store.
- **Known deviation to migrate:** the bootstrap keys `ENCRYPTION_KEY` and
  `AUTH_SESSION_HMAC_SECRET` are still read from the environment at runtime via
  pydantic-settings (`backend/core/config.py`). Treat these as the root-of-trust
  that unlocks the registry and keep env strictly as bootstrap transport; do not
  add further `os.getenv` secret reads, and migrate toward the KV pattern as it
  is adopted.

### This repo's role in the ecosystem

- **This repo (naruon) is the ECOSYSTEM HUB:** email/PIM that DOM-decomposes
  emails and files (PDF via the newsdom-api sidecar) into a persisted
  content-graph + project-graph knowledge graph in Postgres, and composes the
  ecosystem services below.
- The org is an ecosystem around **naruon** (the hub: email/PIM that
  DOM-decomposes emails/files into a persisted knowledge graph). Its components
  are each a **standalone program that must ALSO work as a git submodule**,
  grown separately and together: **wardnet** = WAF/IDS/AI SOC/LB/APIM;
  **clearfolio** = document viewer; **pg-erd-cloud** = ERD tool;
  **contextual-orchestrator** = LLM cost/perf/upstream-LB gateway (beyond
  LiteLLM); **codec-carver** = STT/omni-modal speech-video codec;
  **fast-mlsirm** = LLM-as-a-Judge calibration + evaluation-item quality (uses
  aFIPC FIPC + kaefa item-fit); **keyverse** = passwordless SSO
  (OIDC/SCIM/ADFS/LDAP/FIDO2/OAuth2.1, eliminate passwords); **newsdom-api** =
  PDF→DOM sidecar; **semantic-data-portal** = upper ontology/catalog/governance
  plane with its own graph engine.

### Research grounding (attach paper PDFs)

- **Org rule:** substantive feature or process PRs should find the relevant
  academic papers and **commit their PDFs into the PR** (e.g. a `docs/papers/`
  or `references/` directory) with full citations, **respecting copyright** —
  attach the PDF only when redistribution is permissible; otherwise cite, link,
  and summarize instead.
- **Example for this repo's domain:** a PR touching the content/project
  knowledge-graph pipeline (DOM decomposition, entity/relation extraction,
  grounded graph retrieval) should ground itself in the relevant layout-analysis
  and knowledge-graph / grounded-retrieval literature.

### Structural topic-model boundary

- Do not implement or describe hard-coded term lists, term frequency,
  embeddings, or LLM-assigned labels as structural topic modeling (STM).
  Fixed business labels are not topic-posterior estimates, and the explicitly
  lexical `keyword_extractor` must not be used as topic evidence.
- Topic inference requires a versioned fitted TEPP model and its frozen
  preprocessing and vocabulary contract. If that fitted model is unavailable,
  fail closed; do not return a default label, template agenda, or substitute
  keyword/embedding/LLM result presented as STM.
<!-- END cwl-agent-guidance -->

## Release governance defaults

- 자동 배포 요청이 있으면 조건 충족 후 기존 canonical release workflow로
  배포까지 진행한다. 보호 브랜치의 exact SHA, 필수 검사·독립 승인,
  패키지 소유권·버전·배포 대상·환경 승인과 rollback 경로를 먼저 검증한다.
  PyPI·Rust registry 키의 존재는 배포 적격성이나 권한 우회를 뜻하지 않는다.
  Secrets는 이름·workflow 연결·접근 범위만 확인하고 값은 읽거나 출력하지 않는다.
  레지스트리 게시 성공과 실제 서비스 배포를 구분하며 immutable digest/version,
  설치·소비 결과, 배포 revision, readiness와 실제 사용자 흐름을 각각 기록한다.
- GitHub Actions used by governed workflows must be pinned to full commit SHAs
  with a trailing version comment, for example `# v6`; major-only refs such as
  `@v6` are not allowed in release or security workflows.
- Security scanners are required gates. Do not use `continue-on-error: true` to
  hide Bandit, Strix, CodeQL, or dependency findings; preserve artifacts with
  explicit `if: ${{ always() }}` upload steps when needed.
- Repository rulesets that require code-scanning tools such as Scorecard or
  Trivy must have matching PR and default-branch workflows that upload those
  tools' SARIF results. If merge is blocked with "Code scanning is waiting for
  results from Scorecard" or another ruleset-required tool, restore the missing
  SARIF workflow and rerun it instead of bypassing or weakening the ruleset.
- PR-scoped Strix scans must include trusted import context for changed backend
  Python entrypoints; do not scan `backend/main.py` or routers as isolated
  single files if that makes real repo modules look missing.
- PR-scoped Strix scans should include changed scanner/workflow/gate code but
  exclude large CI self-test harnesses such as `scripts/ci/test_*.sh` from the
  scanner target. Those harnesses remain covered by Strix self-tests; scanning
  them as source can exhaust model context before security evidence finalizes.
- Prefer upgrading or removing vulnerable dependencies over downgrading patched
  packages unless compatibility evidence is recorded in the PR.
- OpenCode Review, Strix Security Scan, and PR Review Merge Scheduler are
  provided by ContextualWisdomLab central required workflows in
  `ContextualWisdomLab/.github`; do not reintroduce repo-local copies of
  `.github/workflows/opencode-review.yml`, `.github/workflows/strix.yml`,
  `.github/workflows/strix-selftest.yml`, or
  `.github/workflows/pr-review-merge-scheduler.yml`.
- Central LLM review workflows use
  `contextual-orchestrator/orchestrator/free`; do not restore direct GitHub
  Models, Vertex, OpenAI, OpenRouter, or provider-specific fallback credentials.
  Preserve whole-context Strix input, bounded job runtime, ZDR-only
  private-source routing, and fail-closed `Timeout`/`Fatal`/`Warn`/`Denied`
  artifact checks.
- HMAC fallback sessions are local/control-plane compatibility credentials, not
  authoritative workspace-membership evidence. Sensitive tenant security posture
  surfaces must require OIDC/JWKS-backed membership or an explicit dependency
  override in tests; do not allow a signed HMAC `workspace` claim alone to open
  cross-workspace security data.

## PR automation and review defaults

### Agent PR lifecycle playbook

- Select skills by the current task, not by the size of the installed catalog.
  Read each selected `SKILL.md` and its required references completely before
  acting. Discover shared skills through the active tool catalog or
  `~/.agents/skills/<skill>/SKILL.md`; do not commit machine-specific paths.
  Missing tools require an explicit limitation and a safe fallback, never a
  claim that the tool ran. Registration alone does not prove a working service.
- Use these checked-in skills for their matching task:
  [fix-development-mistakes](.agents/skills/fix-development-mistakes/SKILL.md)
  for causal repair,
  [github-actions-privileged-pr-scan](.agents/skills/github-actions-privileged-pr-scan/SKILL.md)
  for privileged scanners, and
  [github-robot-review-gate](.agents/skills/github-robot-review-gate/SKILL.md)
  for gate diagnosis. None authorizes bypassing protection or widening scope.
- Use `agents-md` for agent instructions, `git-commit-format` for commits, and
  `verification-before-completion` before delivery claims. Use `babysit-pr`
  when watching a protected PR. Follow repository commit conventions and use
  truthful attribution, not another skill author's model identity or commands
  copied from an unrelated repository.
- Use `autoresearch` only for measurable optimization with a baseline, an exact
  metric command, scope, constraints, and an experiment/result log. Do not add
  an experiment scaffold to documentation-only work or ordinary review repair.
  Shared-branch recovery must preserve other writers' changes; the skill's
  destructive reset, amend, and generic timeout examples do not override this
  repository's non-force and model-timeout rules.
- Use `adr-author` for architecture decisions and `humanize-korean`/`im-not-ai`
  for Korean prose, preserving meaning, facts, numbers, and proper names. For UI
  changes, use Figma, Storybook, `ui-ux-pro-max`, and `anti-slop-ui` when
  available; verify actual component states, accessibility, responsive layouts,
  and affected locales rather than treating a design artifact as runtime proof.
- After tracing the affected flow, apply Superpowers systematic debugging and
  test-first verification, then use the Ponytail ladder: reuse repository code,
  standard-library or platform behavior, and installed dependencies before
  adding the smallest complete implementation. This ordering never removes
  trust-boundary validation, data-loss protection, accessibility, or the check
  that reproduces a non-trivial fix.
- Use Context7 for current third-party API contracts, DeepWiki for public
  external-repository architecture, and sequential thinking for multi-step
  design or debugging. Send only public metadata to remote MCP services;
  private source and customer data require an organization-approved ZDR
  endpoint.
- Apply the mutation loop only to implementation, remediation, and landing
  tasks. Review-only agents stop after publishing evidence-backed findings and
  must not edit, execute project code, push, approve, or merge.
- For implementation, remediation, or landing tasks, repeat for every open PR:
  fetch the exact remote base and head, inspect
  current-head reviews and unresolved threads, reproduce failed checks from
  their logs, repair the canonical owner, run focused tests plus the applicable
  contract/security suite, push without force, and re-fetch evidence. A new
  head invalidates earlier reviews and checks.
- Before creating a worktree or restacking a branch, compare `git ls-remote`
  with the local remote-tracking ref and start from the verified 40-character
  SHA. Never guess or manually extend abbreviated SHAs in commits, PR bodies,
  release evidence, or gap baselines.
- Inspect `git config --get-all remote.origin.fetch`: a narrow refspec can make
  `git fetch origin <branch>` update only `FETCH_HEAD`. Fetch the exact source
  branch into its explicit `refs/remotes/origin/<branch>` destination, then
  compare it with `git ls-remote` again. A successful fetch is not proof that
  the remote-tracking ref used for the merge is current.

#### Commit Attribution

- Create a conventional commit with truthful agent attribution. Add a
  cryptographic signature or `Signed-off-by` footer when repository rules or
  contributor policy require it, and add a truthful `Co-Authored-By` footer for
  the acting agent; verify that evidence before claiming the commit satisfies
  that policy. Immediately before updating an existing remote
  branch without force, fetch it and require its head to equal the reviewed
  parent. For an initial push, first verify that the exact remote ref is absent,
  then create it with a normal non-force push. Generated GitHub merge refs are
  transport evidence, not authored commits; verify their parent and tree SHAs
  rather than rewriting them.
- Treat concurrent commits and pushes as lineage to reconcile, not as grounds
  for force-pushing. Merge the updated prerequisite into the same stacked
  branch, preserve its complete delta, rerun focused checks, and retarget only
  when the resulting dependency order is verified.
- An "empty commit" message or acknowledgement is not tree evidence. Inspect
  the exact parents with `git show -s --format='%H %P %T' <head>` and compare
  `git diff --name-status <verified-parent> <head>` before carrying checks
  forward. For merge commits, record which parent is the comparison baseline.
  If valid inherited changes disappeared, retain both revisions and read the
  related reviews/comments; do not reverse an unexplained external deletion
  until its intent is resolved. Continue independent work without consuming
  the disputed revision, and invalidate old-head success claims immediately.
- Preserve unrelated dirty or untracked files. If a command changes the wrong
  checkout, stop before editing or pushing. Record before/after SHAs and staged,
  unstaged, and untracked state; preserve displaced commits under a recovery
  ref. Restore only proven agent-owned changes with a ref update guarded by the
  expected old SHA. Stop if ownership or concurrent movement is uncertain.

#### Verification and protected landing

- 검증 대상 worktree는 모든 실행 핸들의 terminal 결과 회수 → 충돌 표시 제거와
  `git diff --check` → commit/tree 고정 → 검증 순서로 다룬다. 검증 중에는
  편집·merge·restack을 하지 않고 읽기 전용 조사만 한다. 관찰 timeout은
  실행 종료가 아니다. 도중 소스가 바뀐 결과는 로그와 함께 오염된 실행으로
  분리하고 특정 HEAD의 통과·회귀 근거로 쓰지 않는다. 재발 수리는
  `.agents/skills/fix-development-mistakes/SKILL.md`를 적용한다.
- 보안 검사 exit 0만으로 전체 범위를 검증했다고 쓰지 않는다. exact-head
  결과의 실제 manifest 목록에 예상 잠금 파일이 있는지 확인한다. 기본
  탐지에서 빠지는 `requirements-*.txt`도 포함하고 취약 버전 RED와 수정
  버전 GREEN을 비교한다. 중앙 탐지 수정은
  [#1969](https://github.com/ContextualWisdomLab/.github/pull/1969), 의존성
  통합 근거는 [#1244](https://github.com/ContextualWisdomLab/naruon/pull/1244)이며,
  열린 PR을 보호 브랜치 반영으로 취급하지 않는다.
- lint/test exit 0과 경고 없는 검증을 구분한다. `eslint --max-warnings 0`과
  원래 출력을 유지하는 React 경고 spy·단언으로 실패를 재현한다. 비동기
  렌더와 입력 이벤트는 `await act`로 기다리며 `console.error`를 끄지 않는다.
  [#1245](https://github.com/ContextualWisdomLab/naruon/pull/1245)의 수리처럼
  남은 다른 화면의 경고와 커버리지 부족은 별도 미완료 항목으로 기록한다.
- Tests invoked with `--noconftest` must bootstrap every required setting in
  the test or trusted workflow step. Use explicit test-only values and fresh
  random secrets; do not weaken production validation or depend on a developer
  shell's environment.
- For warning-strict pytest evidence, use `python -m pytest -W error` and audit
  ini filters, per-test marks, and warning-catching contexts. The environment
  setting `PYTHONWARNINGS=error` alone does not override pytest ignore rules;
  record intentional warning assertions separately and repair deprecated
  dependencies in their existing prerequisite PR instead of hiding warnings.
- Exact changed-line review evidence must be generated only from real
  current-head added or modified lines. Do not invent line 1 for deleted-only,
  binary, oversized, or otherwise ineligible files, and do not relax the
  validator to accept a fabricated receipt; fail closed or repair the canonical
  receipt producer.
- Do not present a heuristic as a security, AI-quality, or completion
  guarantee. State its evidence boundary and replace it at the canonical owner
  when the workflow requires an enforceable contract.
- General JSON Schema validation does not prove that a model endpoint accepts
  the schema. Verify the provider's supported subset for the selected endpoint
  and model before proposing schema changes; retain semantic checks at the
  canonical owner when the wire format cannot express an invariant. For
  OpenAI Structured Outputs, check the current guide before using composition
  keywords: `allOf`, `if`/`then`/`else`, and root-level `anyOf` are unsupported
  as of 2026-09-06; nested `anyOf` has separate subset constraints.

  - OpenAI. (n.d.). [*Structured model outputs*](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas). Retrieved September 6, 2026.

- An offline/source reproduction without the original model response is a
  counterexample, not the proven cause of a hosted failure. Bind a causal claim
  to the exact source SHA, request schema, sanitized response/error evidence,
  and run ID/attempt; keep missing evidence explicit. Synthetic counterexamples
  belong in unit tests and cannot stand in for actual provider execution.
- Close HTTP error responses at the resource-owning transport boundary on
  success and failure. Parsers receiving borrowed streams must not close them
  unless their contract explicitly transfers ownership; test that ownership
  transfer and exception paths. Do not rely on garbage collection to release
  sockets. Reproduce `ResourceWarning` with warning-strict tests and deterministic
  cleanup assertions at the acquiring caller, not by adding cleanup to every
  helper or hiding the warning.
- Pending or queued reviews and checks are wait states. Continue safe work on
  another gap. Before calling a PR merge-ready, freshly verify the exact head
  and base, live rulesets, required checks, unresolved threads, and applicable
  current-head CodeRabbit or structured OpenCode fallback evidence. After the
  merge, verify the merge commit and protected target branch.
  Read each job's name alongside its ID, head SHA, status, and conclusion so a
  successful `Detect changed scope` job is never counted as the later
  dependency-review or security job's success, even within the same run.
- Never authenticate review evidence by its display name or status context.
  Verify the check App or exact Bot creator against the owner contract; reject
  missing or unrelated publishers. Inspect blocking output even when the check
  conclusion is success or skipped. Cover forged publishers with and without
  pending notices, missing/wrong-type creators, and trusted positive cases.
  [Governance repair #1531](https://github.com/ContextualWisdomLab/naruon/pull/1531#issuecomment-5559591367)
  records the counterexamples; an open repair PR is not protected integration.
- Ready for review is review admission, not merge authorization. Keep a PR
  Draft while its delta, ownership, conflict repair or required foundation is
  incomplete. Once the bounded slice is independently reviewable and its
  current-head local checks pass, mark it Ready to obtain independent review;
  do not require that review before leaving Draft. The central OpenCode
  entrypoint declines dispatch for a live Draft, so that requirement would
  prevent review from starting. Pending hosted checks remain required; Ready
  does not waive them, accept a Proposed contract, or authorize a merge.
  Immediately before the transition, re-fetch the head/base and confirm the
  local receipts still match. Read back the state and head afterward; a moved
  head invalidates those receipts and needs revalidation. Record the transition
  and verify fresh workflow/review evidence. Never toggle Draft repeatedly or
  add an empty commit to requeue.

  - GitHub. (n.d.). [*Changing the stage of a pull request*](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/changing-the-stage-of-a-pull-request). Retrieved September 6, 2026.
  - ContextualWisdomLab. (2026). [*Required OpenCode review admission*](https://github.com/ContextualWisdomLab/.github/blob/43024633eba9d96b0456970391360da5a171fbda/.github/workflows/opencode-review.yml#L360-L369) [Workflow source].

- Audit workflow triggers and concurrency as parsed YAML behavior, not by text
  search. PR review and repair groups use
  `<workflow>-<repository>-<PR number>` with `cancel-in-progress: true`, so a
  new head cancels only the older run for the same workflow, repository, and
  PR. Metadata-only PR Governance is the deliberate exception: it serializes
  the same PR's state publication with `cancel-in-progress: false`. Release,
  deployment, migration, and provenance jobs also remain serialized and are not
  canceled by review concurrency.
- Prefer central required or reusable workflows over repository-local copies.
  Remove duplicate scanners, arbitrary sleeps, runner-held polling, and
  per-PR organization queue sweeps once a current-head dispatcher or central
  control-plane workflow owns that job. On `converted_to_draft`, `closed`, or
  an obsolete head, revalidate the live PR state before canceling queued or
  running review work; `ready_for_review` must start fresh current-head work.
- A queued workflow record is not proof of an occupied runner. Inspect jobs and
  preserve current-head release, deployment, image, migration, SBOM,
  provenance, and security evidence. Do not use administrative merge bypass.
  The stale-context procedure in `docs/development/merge-gate-policy.md`
  requires explicit maintainer authorization for the exact ruleset change and
  substitute evidence; a delivery request alone is not that authorization.
  Restore the captured configuration on success, failure, cancellation, or
  expiry, and block further landing until restoration is verified. It never
  authorizes suppressing a product or security finding.
- Model-backed OpenCode, Strix, and Noema workflows request only
  `contextual-orchestrator/orchestrator/free` with the gateway token.
  Provider discovery, capability routing, and fallback belong to the
  orchestrator; consumer workflows do not carry provider names, model names,
  direct-provider credentials, or paid fallbacks. Production consumption
  requires an immutable released owner API/client/schema; an open PR or
  unreleased branch is proposed evidence, not a consumable contract. Verify the
  requested logical model, endpoint, served-model metadata, and terminal
  response in the same run.
- Keep private-source review fail closed and ZDR-only. Never log or copy bearer
  tokens, provider credentials, request payloads, or secret-derived values.
  Repair shared sidecar startup, credential bootstrap, timeout handling, and
  response normalization where all review paths converge.
- Do not impose a shared application/agent/gateway wall-clock timeout on
  model work. The default is unset; only explicit user cancellation, a provider
  terminal result, or a configured administrator limit ends it. OpenCode,
  Strix, and Noema jobs must permit at least two hours, but that job budget is
  not a model timeout and does not create a three-hour maximum.
- On GitHub 401, 403, rate limit, or repeatedly truncated responses, fail closed
  instead of inferring current state. Use bounded retry and archive validation,
  then continue only work grounded in already fetched exact SHAs until access is
  restored.
- Do not close a PR merely to reach zero open PRs. Close only with explicit user
  direction, no valid delta, a malicious change, or a verified successor that
  carries the predecessor's complete delta and records the lineage.
- 미완료 이슈는 `Refs`와 남은 수용 기준으로 참조한다. 부정문에서도 자동 종료
  키워드와 이슈 번호의 조합을 쓰지 않는다. 병합 전 `closingIssuesReferences`를
  조회해 실제 완료된 수용 기준과 대조한다. #1365에서 부정문이 #1022 자동 종료로
  해석된 사례처럼, 문장의 의도만으로 GitHub 동작을 추정하지 않는다.
- 작업 중 재현·수리한 반복 오류는 같은 owner의 `AGENTS.md`에 지속 반영한다.
  재사용할 규칙과 적용 스킬·절차만 남기고 exact-head 로그·실험·실패 이력은
  기존 PR·doctoring·Gap 원장에 연결한다. 일시적인 큐 상태를 영구 규칙으로
  만들거나 기존 규칙을 중복 복사하지 않으며 문서 검사와 실제 렌더 검수를 수행한다.
- Keep the handoff in the existing PR and `docs/product-technical-gap-baseline.md`:
  owner, worktree, full head/base SHAs, changed contract, reproduction command,
  exit status, pass/fail/skip counts, evidence link, and next safe action. Record
  skipped PostgreSQL or browser paths as unverified, even when the command exits
  zero. Local tests, protected merge, published release, and live operation are
  separate claims; source/config assertions do not prove network behavior.
- Track protected source SHA, actual consumer pin, configuration scope and
  revision, API readback, and the matching execution's run ID, attempt, and
  terminal result separately. A merged parser fix does not update a repository
  variable or prove successful dispatch. Retain sanitized evidence for each
  stage; never include secret values or secret-derived fingerprints.
- Schema or parser support is not authorization. Before changing an allowlist,
  read the owner decision and require explicit authorization for the exact
  principal and resource. Do not infer it from test fixtures or a known bot
  sender. Keep an unresolved authorization decision pending; do not broaden
  access to make a check pass. Before restoring an agent-owned temporary
  change, compare the current value and revision with the recorded write, stop
  on concurrent drift, and preserve the restoration receipt after readback.
- GitHub re-runs retain the original `github.actor` privileges and event SHA/ref;
  `github.triggering_actor` can differ. Inspect which identity fields the exact
  workflow checks before choosing a re-run. Do not blindly rerun a dispatch
  whose gate rejects the re-run initiator, and do not treat a re-run as evidence
  for a newer head. Verify an authorized execution on the intended event/head.

  - GitHub. (n.d.-a). [*Contexts reference*](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#github-context).
  - GitHub. (n.d.-b). [*Re-running workflows and jobs*](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).

- When filtering reviews, bind the root `headRefOid` before iterating
  `.reviews[]`; inside that iterator, `.` is the review, not the PR. A useful
  read-only snapshot is `gh pr view <pr> --repo ContextualWisdomLab/naruon
  --json headRefOid,reviews --jq '.headRefOid as $head | {head: $head,
  reviews: [.reviews[] | select(.commit.oid == $head)]}'`. Empty output or
  omitted/paginated evidence is not approval; verify checks, unresolved threads,
  and live rules separately under the merge-gate policy.

Evidence basis: Souppaya, M., Scarfone, K., & Dodson, D. (2022). *Secure
Software Development Framework (SSDF) Version 1.1: Recommendations for
Mitigating the Risk of Software Vulnerabilities* (NIST SP 800-218). National
Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-218.
SSDF PS.1 and PS.3 ground accountable protected changes and retained integrity
and provenance evidence without prescribing repository-specific tooling. The
redistributable NIST publication is retained at
`docs/papers/nist-sp-800-218.pdf`; NIST states that SP 800 publications are not
subject to U.S. copyright, while attribution remains required.

- Follow `docs/development/merge-gate-policy.md` for PR gate interpretation.
- PR Governance must stay metadata-only: no PR-head checkout, no admin merge, no
  review dismissal, and no security-check suppression.
- Pending/queued checks, pending CodeRabbit evidence, and a missing structured
  OpenCode fallback approval are wait states, not hard failures. Hard blockers
  should be reported through the idempotent
  `<!-- pr-governance:metadata-gate -->` comment path.
- CodeRabbit gating is evidence-preferred. When the current head has CodeRabbit
  check-run evidence, pending evidence is a wait state and blocking evidence is
  a blocker. When no CodeRabbit check-run exists, require an exact-current-head
  `APPROVED` review from the `opencode-agent` GitHub App whose body names the
  head SHA and contains structured adversarial validation with `status=passed`
  and at least two falsified probes. Reject stale-head, `github-actions`, and
  insufficient-probe approvals.
- The GitHub check-runs API silently refuses to move a completed check-run back
  to a non-completed status (the PATCH returns 200 but the run stays
  completed), which pins a stale failure to the head. Gate publishers must
  create a fresh check-run for completed→non-completed transitions instead of
  patching the completed one.
- OpenCode Agent approvals must be gated on current-head GitHub Checks. If a
  completed check run or status context failed, or the check rollup cannot be
  verified, the OpenCode review must request changes or explain the verification
  failure instead of approving.
- When OpenCode requests changes because Strix or another GitHub Check failed,
  it must access the failed check logs and annotations, cite the exact failure
  phrase, map each actionable failure to a concrete repository `path:line`, and
  provide root cause, fix direction, regression-test direction, and a
  source-backed suggested diff. A review that only cites a workflow URL, check
  name, or generic failure summary is not sufficient. If Strix output contains
  multiple model vulnerability reports, include every model-reported
  vulnerability separately with the model name, title, severity, endpoint, and
  Code Locations/path:line evidence when present.
- Strix logs may print the report's `Model ...` line after the title, endpoint,
  and Code Locations block. Failed-check evidence parsers and OpenCode review
  validators must attribute each vulnerability to that in-report model line, not
  to a previous failed routing attempt.
- OpenCode Agent PR reviews must be general-purpose and meticulous rather than
  narrowly scenario-specific. Configure the review prompt to use all relevant
  MCP sources: CodeGraph for structural source evidence, DeepWiki for repo docs,
  Context7 for current library/API behavior, and web search only for bounded
  external lookups. The agent may directly read changed files and focused hunks
  in read-only mode when MCP evidence is insufficient, but must not edit files
  or execute project code during the review.
- OpenCode Agent findings should be concrete and directly usable: each blocking
  finding should name the observable impact, the trigger condition or affected
  workflow, the smallest source-backed fix, and an exact verification command or
  test target when the repository already has one. Avoid generic architecture
  advice unless it maps to the cited `path:line`.
  When GitHub reports a merge conflict, include a concrete conflict-resolution
  direction instead of only saying the PR is blocked: name the base/head branch,
  tell the author to merge or rebase the latest base branch into the PR branch,
  resolve conflict markers in the changed files, rerun the focused checks, and
  push the same branch.
  For Greptile-style specificity, carry a P1/P2/P3 priority in each finding,
  cite the evidence type that justifies it (nearby implementation, matching
  existing example, cross-file counterpart, current official docs, or failed
  check/log evidence), flag unrelated PR scope drift as scope risk instead of
  burying it in style notes, and make `suggested_diff` a GitHub
  suggestion-ready minimal diff when possible. Include one compact Mermaid
  graph in the human-readable review body that maps the changed surface to the
  main risk, fix, and verification path.
- OpenCode `Review Overview` comments are durable gate evidence. Publish them
  through an idempotent marker such as `<!-- opencode-review-overview -->` and
  update the existing comment instead of deleting it after approval, failed
  checks, or check-rollup lookup failures.
- Keep CodeRabbit `request_changes_workflow` enabled for robot approval, but
  keep CodeRabbit GitHub Checks integration disabled. GitHub Actions are already
  evaluated by required checks and PR Governance; letting CodeRabbit also gate
  on Actions can strand a stale GitHub `CHANGES_REQUESTED` review when an
  external scanner such as direct-OpenAI Strix is quota-blocked after comments
  are fixed.
- `STARTUP_FAILURE` in required PR governance/check metadata is a hard blocker
  and should use the same idempotent metadata-gate comment path.
- Required-check state handling fails closed: only explicit pass states
  (success, pass, skipped, neutral) satisfy the gate and only explicit pending
  states wait; any unrecognized state is a blocker. Gate blocker comments
  publish sanitized names and generic error text — raw CLI diagnostics belong
  in the workflow run log, never in PR comments.
- Trusted-base governance materialization must tolerate transient GitHub API
  truncation such as `unexpected end of JSON input` with bounded retries and
  archive validation; do not convert that infrastructure flake into a CodeRabbit
  or review blocker.

## Workspace and task tracking defaults

- First-run frontend sessions should open the Today execution dashboard while
  preserving explicit Dashboard, Email, and Calendar startup choices.
- A successful HTTP response and `Array.isArray` do not establish dashboard
  readiness. Validate each consumed member before storing it: null records,
  malformed display fields, task states, and calendar capabilities must enter
  the existing unavailable/retry state, not crash rendering or become empty
  success. Keep valid empty arrays distinct and test each affected source.
- Workspace navigation changes must keep the desktop primary nav and the
  tablet/mobile drawer in sync for Mail, Calendar, Tasks, Projects, Context
  Search, AI Hub, Data, Security, and Settings; add route and responsive E2E
  coverage instead of documenting unavailable destinations as implemented.
- Workspace destination pages must show actionable detail surfaces, not inert
  marketing placeholders. Calendar needs month/week/detail/coordination and
  CalDAV writeback states; Tasks needs source-linked ticket boards/details;
  Search needs result/detail graph/timeline states; Projects needs decision logs;
  Data needs repository/ingestion/embedding/quality/WebDAV queues; Security and
  Settings need governance and operational control surfaces. Keep provider writes
  labeled as future work until source-backed integrations exist.
- Browser frontend writes to signed backend routes must use the HttpOnly
  `naruon_session` cookie through the same-origin Next.js `/api/*` proxy, which
  translates the server-readable cookie into backend `Authorization: Bearer`.
  Browser code must not store bearer/session tokens in `localStorage` or
  `sessionStorage`, and must not emit or forward public identity headers such as
  `X-User-Id`, `X-Organization-Id`, `X-Group-Id`, `X-Group-Ids`, `X-User-Role`,
  or `X-Dev-Auth-Token`; tests/mocks must exercise the signed-session cookie
  path.
- Frontend Docker, Compose, and publish workflows must not compile or inject a
  public `NEXT_PUBLIC_API_URL` into browser bundles. Browser API calls stay on
  same-origin `/api/*`; only server-side Next.js route handlers should read
  runtime `BACKEND_INTERNAL_URL`, with the exact Docker-network opt-in when
  running local Compose.
- JWT/session verification must reject unsupported critical headers (`crit`)
  before trusting payload claims; do not rely only on library defaults for this
  boundary.
- Session authority is a server-side verification result, not a token payload
  claim. HMAC and OIDC paths must pass `session_verifier` from the code path that
  validated the signature/key; never derive it from `_session_verifier` or a
  similar user-controlled JWT claim.
- Private backend `/api/*` routers must be registered with the default
  `get_auth_context` signed-session dependency; only explicitly documented
  public endpoints such as `/` may omit it. Keep runtime feature/configuration
  endpoints signed-session protected; if the browser needs unauthenticated
  bootstrap data, add a narrowly scoped non-`/api` endpoint that cannot reveal
  operational feature flags or provider state.
  Prometheus `/metrics` must stay disabled by default and, when enabled, sit
  behind a trusted scrape path or reverse proxy access policy. Admin/provider
  registry endpoints must enforce role checks in addition to authentication. LLM
  provider `base_url` values must fail closed unless they are HTTPS, exact-host
  allowlisted by `ALLOWED_LLM_BASE_URL_HOSTS`, and resolve only to global
  addresses. Runtime LLM calls that use a custom provider `base_url` must build
  their `httpx` client through `build_llm_provider_http_client` so TCP connects
  only to prevalidated global IP addresses while TLS/SNI still uses the
  allowlisted hostname; do not hand a freshly validated URL to a generic client
  that can resolve DNS again at connect time.
- Dynamic tool registration (`POST /api/tools`), update (`PATCH
  /api/tools/{code}`), and deletion (`DELETE /api/tools/{code}`) must fail closed
  until durable signed-session tenant/workspace ownership, administrative
  authorization, built-in immutability, and a real provider/adapter execution
  target are implemented and verified. Do not substitute a process-global
  registry or placeholder success. A mock or placeholder handler must never
  report successful work. Preserve the built-in catalog and supported
  `POST /api/tools/{code}/execute` path; the mutation restriction is not a ban on
  all POST requests. Keep behavioral tests for rejected writes, unchanged
  built-ins, signed-session scope, and actual execution results with the product
  implementation; documentation alone does not establish runtime readiness.
- OIDC issuer and JWKS URLs are outbound identity-provider fetch surfaces. They
  must use HTTPS, must not include userinfo or fragments, must reject localhost
  and non-global IP literals, and must be exact-host allowlisted by
  `ALLOWED_OIDC_HOSTS` before any JWKS preload or token verification path can
  use them. Allowlisted OIDC hostnames must also resolve only to global
  addresses, and JWKS retrieval must connect to the already validated pinned
  address while preserving TLS/SNI for the allowlisted hostname.
- Email-derived tasks must stay source-linked to the email/thread and tenant
  owner scope. Do not expose new sequential database ids through task APIs; use
  opaque public ids for user-visible ticket tasks. Task titles are plain text:
  reject HTML-like execution item markup at the backend boundary rather than
  storing user-supplied tags for later UI rendering. Parsed email display fields
  must not persist active HTML/script markup, and email API list/detail/thread
  responses must sanitize stored subject/body/snippet/address display fields
  before returning them. Preserve message/thread identifiers separately from
  UI-safe subject/body, address, and attachment display text.
- Email file import must keep frontend file pickers, `/api/emails/import-files`,
  and `services.email_import_service` in the same source-backed contract:
  supported uploads are `.eml`, `.zip`, and `.mbox`; imported email and
  attachment vectors must use the active organization LLM provider's
  `embedding_model` and `base_url` when configured, fit provider vector
  dimensions to storage, and fall back to zero vectors only when provider
  embedding generation is unavailable. Tests must cover the local
  `embeddinggemma` path so Data workspace imports do not silently bypass the
  selected embedding model.
- Home/Today dashboard reply-wait surfaces must read signed
  `/api/emails/pending-replies` data instead of inferring pending replies from
  generic inbox fixtures or static copy. Tests and E2E mocks must verify the
  HttpOnly `naruon_session` cookie proxy path and must not add public identity
  headers.
- TenantConfig/provider account settings must be scoped by signed-session
  `user_id` and `organization_id`; do not query provider credentials or API keys
  by `user_id` only. Frontend Settings onboarding must use bearer-session API
  calls for account config, CalDAV/WebDAV source readiness, and runner token
  rotation, and mocks must not reintroduce public identity headers.
- Self-service mailbox configuration routes must enforce owner-required
  RBAC/ABAC through `services.access_policy`; system/platform admins may not use
  user-facing `/api/config` routes to read or mutate another user's mailbox
  credentials. Cross-user administration needs a dedicated audited admin route.
- Workspace-scoped resources must carry `workspace_id` through both
  `AccessRequest` and `ResourcePolicy`, and SQL scopes for WebDAV/Data/Security
  surfaces must filter the current workspace in addition to owner and
  organization. Do not expose same-organization cross-workspace records.
- User-owned mailbox/provider account endpoints must not treat `system_admin`
  or `platform_admin` JWT roles as an owner session. Elevated operators need
  separate audited support flows; `/api/accounts/config` must reject forged or
  orgless privileged sessions before credential lookup, and tests must exercise
  the real signed bearer path rather than only dev public-header overrides.
- HMAC fallback sessions must not authorize `system_admin` or `platform_admin`
  roles. Platform-wide operators require the OIDC/JWKS path or a separately
  audited support flow so compromise of an HMAC session secret cannot mint
  platform administrator claims.
- `AUTH_SESSION_HMAC_SECRET` validation must enforce byte length, distinct
  character count, character-class diversity, placeholder/public-fixture
  rejection, and an explicit estimated entropy floor; keep runtime-secret tests
  aligned so long low-entropy strings cannot pass by length alone.
- Reply-wait task escalation must reuse the server-authoritative pending reply
  path, create or update source-linked `reply_sla` ticket tasks by opaque task
  id, and sanitize generated task titles from email subjects before persistence.
  Do not create duplicate reminder tasks for the same pending sent-mail message.
- Mail connection updates and workers must validate server-side SMTP, POP3,
  IMAP, and relay destinations before persistence or network connection. POP3
  credentials are required for POP3 sync;
  missing credentials must fail the sync path instead of logging a successful
  no-op. Do not place sensitive credential values, secret-derived values, or
  password-shaped field names in logs or raised exception text; use generic
  operation phrases such as "account configuration incomplete" instead of
  credential-type labels.
- SMTP, IMAP, and POP3 host validation must reject legacy numeric IP literal
  forms such as decimal integers, hexadecimal integers, and octal dotted forms
  before DNS or socket connection; `socket.getaddrinfo` may resolve those forms
  to loopback/private addresses even when `ipaddress.ip_address` rejects them.
- GitHub Actions `run:` blocks must not directly interpolate `${{ github.* }}`,
  `${{ inputs.* }}`, or other expression data into shell conditions or commands.
  Pass expression values through step `env:` keys first, then quote shell
  variables such as `"$IS_PR_EVIDENCE_RUN"` inside the script. PR base/head
  SHA values from manual workflow inputs must be regex-validated as git SHAs
  before any fetch, diff, or artifact metadata use.
- Privileged `pull_request_target` scanner jobs must treat PR-head blobs as
  non-executable input data. When copying PR-head files into temporary scan
  scopes, strip executable bits instead of preserving `100755` modes. PR-scoped
  Strix workflow runs should use the explicit `STRIX_TARGET_PATH=__PR_SCOPE__`
  sentinel so the trusted base checkout is never presented as the PR scan
  target. Strix child processes that inspect untrusted PR scope data must set
  package-manager lifecycle script guards such as `NPM_CONFIG_IGNORE_SCRIPTS`,
  `PNPM_CONFIG_IGNORE_SCRIPTS`, and `YARN_ENABLE_SCRIPTS=false`; do not allow a
  scanner dependency install to execute PR-provided `package.json` scripts.
- Test harness HTTP smoke helpers must not use broad URL opener APIs such as
  `urllib.request.urlopen`; keep URL scheme validation and use explicit HTTP or
  HTTPS clients so Bandit/Strix do not normalize test-only SSRF patterns into
  production examples.
- Screenshot and browser-capture helper scripts must build navigation targets
  from a fixed localhost origin and an explicit route allowlist before calling
  Playwright `page.goto`; do not concatenate raw route or URL strings, and log
  capture failures with fixed message templates plus sanitized fields.
- Alembic migrations must use structured Alembic/SQLAlchemy operation APIs such
  as `op.create_index` and `op.drop_index` for schema objects. Do not build DDL
  with `sa.text(f"...")` or interpolated identifier strings, even when the
  current identifiers are static.
- Infrastructure Docker Compose services must inherit the repo hardening
  contract: `no-new-privileges:true`, `read_only: true`, read-only config
  mounts, and explicit `tmpfs` entries for the few runtime paths that must be
  writable.
- Settings account screens must be source-backed by signed-session APIs rather
  than static provider examples. Display only masked secret presence flags, keep
  blank secret fields out of save payloads so stored values are preserved, and
  do not reintroduce public identity headers in frontend account mocks.
- New database tables and columns must use at least two-word `snake_case` names;
  avoid single-token columns such as `id`, `title`, `status`, or `priority` on
  newly introduced objects.
- Public audit/event identifiers that may use human-readable prefixes must not
  be stored in artificially short `varchar(n)` columns; use opaque source UIDs
  that fit seeded smoke data and provider evidence without truncation.
- Conceptual ERDs, API schemas, persistence models, and fixtures must not mark a
  reusable business identifier such as `document_ref`, `model_id`, `topic_id`,
  or `label_id` as an unscoped primary or foreign key. Use an opaque immutable
  reference that binds the full scope or an explicit composite identity with the
  applicable snapshot revision, model version, request/result scope, or label
  version. Define the required identity tuple for each entity; require only the
  dimensions relevant to that entity. Never join snapshots, model artifacts,
  topic components, or label evidence by a bare document, model, topic, rank,
  label, or display value.
- When reviews find public/private identifier leaks, stale API fixture shapes, or recurring bug patterns, update tests, frontend mocks, E2E mocks, README examples, architecture docs, and explicitly record the anti-pattern in `AGENTS.md` so the same bug pattern does not reappear in copied examples.
- `/api/llm/summarize` confidence uses an integer percentage in `0..100`, not
  a `0..1` ratio: `1` means `1%`. Frontend consumers must reject fractional,
  non-finite, out-of-range, and non-number values without rounding, coercion,
  or unit inference; absent or invalid confidence stays unavailable, not `0%`.
  Unit/E2E fixtures and pilot/full-product smoke data must use this contract.
  Keep boundary and rendered-output tests with the product consumer; guidance
  does not prove that the consumer fix has been released.
- Memoized id-to-record Maps must be first-wins (`if (!map.has(key)) map.set(...)`).
  `new Map(items.map((item) => [String(item.id), item]))` is last-wins and
  desynchronizes first-wins label maps from the selected node or edge when
  ids collide. Keep a rendered selection test that repeats an id and asserts
  the first instance is the one opened. Do not treat a source-substring scan
  as the only selection-path contract; fire the vis-network `selectNode` /
  `selectEdge` callbacks with mixed numeric and string ids.
- When reviews find missing browser security headers or tabnabbing hardening,
  update both backend header tests and frontend link tests. Global backend
  responses must include `Referrer-Policy`, and `target="_blank"` links must
  use explicit `rel="noopener noreferrer"`.
- When robot review cites an obsolete Strix provider policy, update the docs and
  tests to the current `contextual-orchestrator/orchestrator/free` contract
  before accepting a rollback suggestion; do not reintroduce generic
  `LLM_API_KEY` or direct-provider credential forwarding to satisfy old comments.
- When reviews find inert navigation/dead-space controls, either wire them to an
  implemented workspace route/API or remove the control; do not leave
  high-traffic drawer/sidebar entries as permanent `준비 중` copy.
- AI Hub tabs must be backed by signed source evidence from `/api/ai-hub/surface`
  or a narrower signed API. Do not reintroduce static model-score fixtures,
  fake workflow logs, or provider names that are not derived from prompt,
  provider, or audit data.
- Data document repository assets must be backed by signed
  `/api/data/quality-surface` evidence from scoped email and attachment rows.
  Do not reintroduce static file lists, sequential attachment/email ids, raw
  message ids, raw thread ids, message bodies, provider URLs, usernames,
  credentials, or claims that Naruon itself stores customer file capacity.
- Icon-only workspace controls must carry localized `aria-label` text matching
  the visible app language; do not rely on the SVG icon alone for Calendar,
  Tasks, drawer, modal, or toolbar actions.
- Execution steps resulting in `Timeout`, `Fatal`, `Warn`, or `Denied` outputs are considered hard failures. Tests must run without these warnings to be considered passing.
- Strix success artifacts must also be scanned for `Timeout`, `Fatal`, `Warn`,
  or `Denied` output before accepting clean evidence. Filter only narrowly known
  third-party Strix internal warnings, such as the
  `strix.core.execution` non-lifecycle continuation line, before artifact upload;
  fail closed on any remaining warning-class report log output.
- DB-affecting API slices need both mocked fast tests and a real PostgreSQL
  bootstrap/smoke path before PR merge evidence is considered complete.
- Required DB evidence must reject collection skips and expected failures as
  well as fixture skips. Check the actual process exit status: a printed pytest
  error can still exit zero when expected-failure metadata is retained. Exercise
  these cases with real pytest reports, not only source-string assertions.
- For long-running verification, redirect output directly to task-owned durable
  files and capture the final runner exit separately. A disconnected observation
  pipe can fail test output and cleanup; partial progress or a missing tool
  handle is not completion or permission to restart a process still alive.
  Verify the full redacted report, explicit skip reasons, exit status and
  absence of that run's labelled containers, volumes and networks independently.
  Keep failed attempts and retry receipts separate; do not infer the original
  pipe-closure cause from a successful retry or alter application timeouts.
- Negative configuration probes must use task-owned decoy files or controlled
  readers and key-only assertions. Never read an operator file to prove that it
  should not be read, or let assertion introspection print credential mappings.
  Isolate inherited provider and replica settings as well as the primary DB URL;
  Compose's env-file selection does not control Python's configuration sources.
  Preserve normal operator defaults outside the explicitly selected test path.
- On cancellation, stop task-owned process groups and retain the cancellation
  exit status. Sanitize reports before potentially blocking teardown, bound
  cleanup, and test both an interrupted worker and interruption during cleanup.
  Delete only the generated test project and raw temporary report after safe
  redaction. These cleanup bounds are not application or model timeouts.
  The shared database runner remains proposed in
  [CI owner #1562](https://github.com/ContextualWisdomLab/naruon/pull/1562)
  until protected integration; its branch-local results do not prove hosted CI.
- ORM `Base.metadata.create_all()` success is not migration evidence. On an
  isolated empty PostgreSQL database, run `scripts/migrate_db.py` from `backend/`,
  rerun it, and verify the recorded Alembic head. Also exercise upgrades from
  supported historical revisions and data-preserving rollback where supported.
  An already-stamped database needs a forward repair; editing an old revision
  alone will not rerun it. Integrate the existing migration owner prerequisite,
  rerun the combined revision graph, and never stamp past a failure or create a
  fake legacy table to make the consumer pass.
- After migration succeeds, run the affected application tests against that
  migrated database, not a replacement ORM-only schema. Migration-created
  indexes and constraints must remain active for supported size limits and
  high-entropy content cases; do not shrink inputs, drop indexes, or omit failing
  cases to manufacture passing evidence. Record migration and application-test
  results separately and repair the shared schema owner when they disagree.
- A rollback check must persist representative records before downgrade and
  compare their values and portable identities after downgrade and re-upgrade.
  A successful command or an empty schema proves no data preservation. Retain
  non-rebuildable identity/provenance history; destructive retirement requires
  a separately authorized migration with recovery evidence.
- A session-level advisory lock that spans item commits or rollbacks needs a
  held physical connection; keeping the ORM session object does not preserve
  backend ownership. Budget any separate lease connection explicitly and test
  a supported one-slot pool. Do not replace the lock with a transaction-level
  lock that ends coordination at the first item commit.
- On uncertain acquisition, work cancellation, or unconfirmed unlock,
  invalidate before session-close rollback can wait on a broken connection.
  Abort a disconnected cycle instead of reconnecting without a lease. Advance
  recovery cursors only through the last completed item or healthy item
  rollback, so unattempted prefetched rows are not skipped after interruption.
- Test lease lifetime on real PostgreSQL across commit and rollback with a
  same-pool reader and an independent replica. Cover actual task cancellation,
  cleanup ordering, connection loss, strict unlock confirmation, and resumption
  of unattempted work while retaining representative source bytes. Source-only
  checks do not prove these runtime outcomes or exactly-once provider execution.
- A conflict rollback expires loaded ORM records even when commit expiration is
  disabled. Await refresh/reload before fallback reads; savepoint rollback already
  removes failed new inserts, so do not expunge them again. A cached `get()` is
  not a fresh authority check: revalidate configuration in the database before
  processing another workspace when deletion must revoke further work.
- Reproduce competing manual writes and configuration deletion with a second
  real database session. Assert lease exclusion during work and availability
  after cleanup; keep assertions outside handlers that intentionally catch
  per-item errors. A test named "between workspaces" must finish the first
  workspace before injecting its failure, not only execute a matching branch.
- When a backend container reports missing `DATABASE_URL` or
  `AUTH_SESSION_HMAC_SECRET`, verify the runtime path injects the operator env
  through `scripts/naruon_compose.sh`, Kubernetes secrets, or an explicit
  orchestrator secret. Do not add code defaults, and do not mount or declare the
  full `~/.env` as a Compose `env_file` because unrelated local secrets may leak
  into the backend container.
- Backend container entrypoints must pass through `python scripts/start_backend.py`
  before `uvicorn` imports `main:app`. Do not reintroduce Dockerfile, Compose,
  live-E2E, or gateway commands that call `uvicorn main:app` directly and expose
  Pydantic import tracebacks for missing runtime settings.
- DAV/WebDAV/CalDAV routes are private integration surfaces unless explicitly
  documented otherwise. Register them with the default signed-session dependency,
  require the signed-session dependency in handler signatures, enforce route
  owner scope before capability/discovery/read/writeback responses, reject
  ownerless DAV paths instead of treating them as shared roots, escape XML
  response fields before interpolation, and keep path values separate from
  log-safe display values.
- Self-hosted runner WebSocket routes must validate both a signed bearer session
  and a server-side WorkspaceRunnerConfig registration token before accepting the
  socket. Do not use the raw path token as identity, a log value, or the sole
  active-connection key.
- Self-hosted connector command handlers must never return placeholder or mock
  success for IMAP/SMTP execution. If no local customer-network adapter is
  configured, fail closed with `adapter_not_configured` and
  `provider_write_executed=false`; if an adapter is configured, wrap only the
  adapter's actual result in the standard runner response envelope.
- Calendar UI actions must request `/api/calendar/writeback-intent` with
  server-authoritative source selection and provenance. Do not wire browser
  actions back to legacy `/api/calendar/sync` unless a trusted backend credential
  dependency and source-owner contract are explicitly in scope.
- Calendar writeback UI must fail closed while the signed source registry is
  loading or errored; do not emit intent POSTs without a confirmed opaque
  `target_source_id`, and keep tests covering the loading/error boundary.
- Calendar coordination must not present canned ICS documents or fixed
  conflict outcomes as production evidence. Use selectable sources from the
  signed `/api/calendar/writeback-sources` registry, or omit the evaluate call
  until source-backed VEVENT evidence exists. Known `.ics` pairs stay in tests.
- Calendar and WebDAV workspaces must expose the current opaque writeback source
  as a deliberate user selection with capability and ETag/If-Match state.
  Automatic first-source fallback may initialize the control, but intent POSTs
  must use the selected opaque source and `409` responses must render as
  conflicts, not generic errors or completed writes.
- Calendar and WebDAV writeback source selection must resolve through opaque
  `source_uid` values, signed-session organization scope, and persisted
  writeback eligibility, not sequential CalDAV or WebDAV account ids.
  Missing writeback eligibility must fail closed. Browser-visible source ids
  must not reveal or be deterministically derived from account primary keys.
  WebDAV account readiness may expose only source-safe labels and ETag/If-Match
  evidence, never provider URLs, usernames, credentials, or sequential account
  ids. Provider mutations remain future work until connector execution can
  enforce capability, consent, and ETag/If-Match checks.
- DAV/WebDAV folder and write paths must not expose sequential folder primary
  keys or claim provider write success from skeleton endpoints. Browser-visible
  project folders use opaque `folder_uid` values, and `/dav` mutation methods
  must fail closed until source, capability, credential, and ETag/If-Match
  execution exists.
- WebDAV folder listings must stay tenant-scoped by both `user_id` and signed
  session `organization_id`; do not reintroduce user-only folder queries because
  the same principal can exist in multiple B2B tenants.
- Mobile workspace drawers must lock background body scroll while open and keep
  the drawer itself scrollable; responsive E2E screenshots should cover the open
  hamburger state after scrolling the drawer.
- Self-sent knowledge extraction must first prove true self-to-self addressing,
  stay idempotent per source email, preserve email/thread provenance, and store
  only plain-text task titles. Do not create unlinked knowledge tasks from raw
  dict payloads when the source email row is unavailable.
- Self-sent knowledge WebDAV/Notes materialization requests must start from an
  opaque task uid, re-check owner and organization scope server-side, reject
  non-`self_sent_knowledge` tasks, and return intent metadata only until the
  connector/provider write path has source-backed ETag conflict handling.
- Private API services should return deterministic `error_code` values for
  expected failures; route layers must not derive HTTP status from human-readable
  message substrings.
- UI async state for repeated task/action rows must be keyed by the row's opaque
  public id so one row's loading, error, or result state cannot overwrite another
  row.
- Sender ontology and relationship DAG APIs must stay scoped to the signed
  session owner and organization. Source-backed UI panels must request
  `source_message_id` and `source_thread_id` filters instead of presenting a
  global relationship graph as if it were current-thread evidence.
- Sender DAG capture must start from a signed source email lookup, not
  browser-submitted relationship classifications. Route layers should derive the
  thread provenance server-side, persist only scoped ontology metadata, and keep
  provider writes out of relationship capture.
- Unique email and forwarded-import dedupe must use strong scoped signals:
  normalized Message-ID, References/In-Reply-To, persisted duplicate provenance,
  or exact body/attachment fingerprints. Do not merge threads from subject-only
  `Fwd:` or `Re:` similarity, and keep duplicate cleanup intent-only until
  provenance persistence and source-backed import rewiring are implemented.
- Operational dashboards must distinguish live server-observed state from
  planned instrumentation. Show connector registration and active outbound
  runner socket state when available, but label sync lag, provider throttling,
  queue depth, and writeback conflict dashboards as pending until source-backed
  connector events exist.
- Security governance screens must be source-backed by signed
  `/api/security/access-surface` data. Do not ship static RBAC/ABAC rows, fake
  blocked-login logs, unsupported TLS/TDE claims, or permanent Security tab
  placeholders as implemented features. The browser-facing Security API and UI
  must not expose source ids, event ids, decision ids, review ids,
  workspace/org/user/group claims, provider execution flags, raw hosts, or
  resource UIDs; render scoped governance labels instead. New Security mocks and
  E2E fixtures must preserve bearer-session calls and omit public identity
  headers.
- Data workspace repository, ingestion, embedding, and quality surfaces must be
  source-backed by signed `/api/data/quality-surface` data or explicitly labeled
  pending. Do not ship static ingestion logs, fake progress percentages, fake
  vector counts, unsupported embedding model names, static quality totals, or
  provider-write success claims; Data mocks and E2E fixtures must preserve the
  bearer-session call and omit public identity headers.
- Project workspace lists, milestones, task links, and decision logs must be
  source-backed by signed `/api/webdav/folders` and `/api/tasks` data or
  explicitly labeled pending. Do not reintroduce static project names, inert
  report/filter buttons, provider write success claims, or sequential database
  ids in project UI/tests.
- Project workspace folder rendering must prove owner scope before display:
  `/api/webdav/folders` includes server-scoped `owner_user_id` and
  `organization_id`, and the browser filters those folders against decoded
  signed-session claims before building project cards. Keep `folder_uid` as an
  internal opaque key only; do not render it as visible UI text.
- Self-hosted connector APM history must be persisted as scoped control-plane
  signal events before the UI claims durable heartbeat evidence. Do not expose
  runner registration tokens, path tokens, or raw provider credentials in event
  ids, details, logs, Settings mocks, or E2E fixtures.
- A `ForeignKey` column alone does NOT guarantee SQLAlchemy flush ordering.
  The unit of work orders cross-mapper INSERTs only through
  `relationship()`-derived dependencies, so a parent+child pair added in one
  `session.add_all([...]); commit()` without a relationship can emit the child
  INSERT first and raise `ForeignKeyViolationError` on real PostgreSQL (SQLite
  and mocked sessions hide it). Every FK table pair must have a `relationship()`
  in at least one direction; `tests/test_model_relationship_integrity.py` guards
  this. Do not "fix" the symptom by flushing parents manually in one seeding
  helper while leaving the model relationship missing.
- `@pytest.mark.postgres` smoke tests exercise the real schema, so raw-SQL
  seeding must match the live models exactly: use the current table names
  (`email_records`, not `emails`), the correct `RETURNING` column per table,
  and include every `NOT NULL` column the ORM default would have filled
  (`created_at`, `observed_at`, `parse_content_type`, `parser_key`). Under
  asyncpg, `INSERT ... SELECT`/`UNION` parameters default to `text`, so cast
  integer FK params explicitly (`CAST(:email_id AS INTEGER)`).
- Postgres smoke seeding of `EncryptedString` columns
  (`credentials_encrypted`, provider `api_key`, runner tokens) must set a
  Fernet `ENCRYPTION_KEY` for the test (monkeypatch `settings.ENCRYPTION_KEY`)
  and store `get_fernet().encrypt(...)` output, never plaintext placeholders —
  the API read path decrypts and fails closed without a key.
- Org-scoped listing endpoints accumulate rows across smoke runs on a shared
  database. Smoke tests that assert an exact count must use a unique
  `organization_id` per run (e.g. `f"org-...-{uuid.uuid4().hex[:12]}"`), not a
  hardcoded `"org-acme"`, or the count drifts as history builds up.
- Every `create_async_engine` in a test must be `await engine.dispose()`d on all
  paths (including skips). A leaked pooled connection surfaces later as a GC
  `ResourceWarning`, which fails an unrelated downstream test under CI's
  `PYTHONWARNINGS=error`.
- Model column defaults must be timezone-aware: use
  `default=lambda: datetime.datetime.now(datetime.timezone.utc)`, never the
  deprecated `datetime.datetime.utcnow`, whose `DeprecationWarning` is fatal
  under `PYTHONWARNINGS=error`.
- Provider-backed AI Hub agent cards and the security access surface are
  admin/authoritative-verifier gated; HMAC bearer sessions cannot carry
  tenant-admin roles or satisfy `_require_authoritative_workspace_scope`. Smoke
  tests must assert the deny-first boundary (member persona sees no agent cards)
  or authenticate through an authoritative-verifier `AuthContext` override —
  do not weaken the endpoint to make the test pass.

## Development environment and tooling defaults

### Evidence discipline

- Treat every PR head as an immutable evidence boundary: re-read the current
  head and protected base before relying on reviews, Checks, screenshots, or
  release claims; a new push invalidates prior evidence.
- Separate focused test success, protected-branch merge, immutable artifact
  publication, and deployed/runtime verification. Record the exact commit,
  command, exit status, viewport/locale/state, and any unverified scope.
- For UI changes, inspect the rendered page at the tested viewport and retain
  a screenshot receipt; DOM assertions and a successful build are not visual
  inspection. Do not claim locale, responsive, production, or deployment
  coverage that was not actually exercised.
- A queued or failed external review is a wait/finding state, not permission
  to force-push, dismiss a review, bypass protection, or close a PR with a
  still-valid delta. Preserve valid successor work and fix the canonical
  owner when the defect is shared.
- Automatic publication is allowed only after the canonical release path
  proves exact artifact identity, environment approval, and a tested rollback
  route; package-secret presence is not release evidence.
- When the foreground browser cannot be inspected (for example, the host is
  locked), a headless render may provide bounded visual evidence only if the
  exact head, fixed local origin, viewport, route, locale, state, and image
  receipt are recorded and the images are opened for direct inspection. Mark
  foreground interaction and live-product behavior as unverified; screenshots
  and DOM assertions must not be presented as proof of those broader claims.

### Package Manager

- Backend: use the project-local `backend/.venv`, `uv sync --project backend
  --locked`, and `uv run --project backend --frozen python -m pytest` with the
  relevant test paths. Keep `backend/uv.lock`; never install into a system
  Python runtime or treat a one-off `PYTHONPATH=.` workaround as a root fix.
- Clean-lock evidence requires an exact `uv sync --locked` in a task-owned
  project environment before testing. `uv run --frozen` alone can retain
  extraneous packages and mask a missing dependency. Do not prune a shared
  environment; use a dedicated worktree environment and keep supplemented-local
  results separate from a clean-lock run.
- Frontend: use Corepack and the `packageManager` pin in
  `frontend/package.json`, `corepack pnpm --dir frontend install
  --frozen-lockfile`, and its existing test/lint/build scripts. The test script
  uses Vitest; do not append Jest-only `--runInBand`.
- For this playbook's source-only contracts, run from the repository root:
  `uv run --project backend --frozen python -m pytest -q --noconftest
  backend/tests/test_agent_llm_authority_docs.py
  backend/tests/test_release_governance.py`. This bypass is limited to tests
  that do not need application fixtures; API/DB validation must use conftest.
- Keep `CLAUDE.md` as complementary guidance; do not replace an existing file
  with a symlink or copy the whole playbook into it.

### Local tooling and cleanup

- If CodeGraph is not initialized for this repository, agents may run
  `codegraph init -i` autonomously without asking first; keep generated
  `.codegraph/` and `.cursor/rules/codegraph.mdc` artifacts local unless a
  future repository policy explicitly says to commit them. OpenCode PR review
  uses the project `opencode.jsonc` MCP servers for CodeGraph, DeepWiki,
  Context7, and web search. It must initialize CodeGraph before review so
  structural findings cite graph-backed evidence instead of relying only on grep
  or raw file reads; use Context7 for current library docs, DeepWiki for
  repository documentation, and web search only for bounded external lookups.
- StepSecurity `harden-runner` will trigger false-positive `suspicious_file_access` lockouts on Next.js build and dev server executions (e.g., `router_init.js` checksum matches). Configure `disable-file-monitoring: true` in the `harden-runner` step rather than disabling the workflow or using `continue-on-error`.
- Next.js 15+ Turbopack resolves workspace roots by scanning upward for `package-lock.json`. Do not create or leave a `package-lock.json` in the user's home directory (`~/`), as it will cause Turbopack to spawn infinite background worker node processes attempting to compile the entire home directory.
- `pydantic-settings` strictly rejects unexpected environment variables by default. When sharing a common `.env` file between frontend and backend services, you must explicitly set `extra="ignore"` in the `SettingsConfigDict` to prevent fatal startup crashes.
- Backend startup must not add code defaults for `DATABASE_URL` or
  `AUTH_SESSION_HMAC_SECRET`. Support explicit env files from the operator,
  repository root, and backend working directory, and require Compose/Kubernetes
  to inject the mandatory values so missing runtime configuration fails before
  deployment rather than during `uvicorn main:app` import.
- Python standard library `re` flags (`re.IGNORECASE`) must be passed via the `flags=` keyword argument. Do not use inline `(?i)` at the start of the expression, as it will trigger `DeprecationWarning` regressions in Python 3.11+ test suites.
- Next.js builds in memory-constrained CI environments (e.g., GitHub Actions) can fail with OOM errors due to PostCSS worker explosion. Set `POSTCSS_WORKERS: "1"` and `DISABLE_POSTCSS_WORKERS: "true"` in the build environment to limit memory usage.
- Release version bumps must keep `VERSION`, `CHANGELOG.md`,
  `frontend/package.json`, FastAPI app metadata, runtime-config responses, and
  Docker runtime packaging synchronized. The backend should read the release
  version from `VERSION`; do not add a new hardcoded API version string.
- Before opening a PR, new committers should run the focused tests that cover
  the changed contract and include exact commands in the PR body. For release
  and Docker changes, at minimum verify `python -m pytest
  backend/tests/test_release_governance.py backend/tests/test_runtime_config_api.py
  -q`, `corepack pnpm --dir frontend test` when frontend
  behavior changes, and a Docker build of the affected image.
- GHCR publishing evidence for the combined `naruon` image must include the
  exact image name, tag, local image ID, push result, and registry verification
  from GitHub Packages or an equivalent manifest/API query. Publish the package
  with public visibility unless a repository policy explicitly says otherwise.
  Do not treat a local tag as published evidence. GitHub's REST Packages API and
  GraphQL package mutations currently do not expose a supported package
  visibility change operation for GHCR container packages; when API checks show
  `visibility: private`, complete the public conversion through the logged-in
  GitHub package settings UI (`Package settings` -> `Danger Zone` -> `Change
  visibility`) and then verify anonymous pull/token access before declaring the
  image public.
- Docker image security inspection is part of release evidence. Use a current
  container scanner such as Trivy or Grype against the exact pushed image tag
  and treat high/critical actionable findings as blockers until fixed or
  documented with precise non-applicability evidence.
- Docker Compose and Podman live-E2E work must clean up only resources created
  by that task, identified by exact IDs and project labels. Use an isolated test
  project and free loopback ports; preserve pre-existing services and persistent
  volumes. System-wide pruning or forced storage repair requires separate
  authorization covering the identified affected resources. Verify cleanup of
  the task-owned resources; do not infer ownership from a `naruon*` name match.
- Keep contributor setup friction low: document any new required environment
  variables, model tags, package-manager version pins, or live-E2E ports in the
  same PR that introduces them, and avoid hidden local-only defaults that make
  another committer's PR fail after checkout.

### Upstream gateway failure boundary

- An HTTP 500/502 or wrapper-exhausted message from a model-backed workflow is
  transport evidence, not proof of a product or consumer defect. Preserve the
  exact status, phase, duration, served-model field, and retry count, then
  route provider discovery, failover, and capability repair to the CO
  canonical owner. Do not add consumer-side paid fallbacks or downgrade a
  failed verdict to clean.

- CodeQL compatibility results require lineage, not just a check name. Record
  the exact PR head, workflow run, job, target language, and log/annotation
  evidence before acting on a failure. If a failed compatibility result is
  visible but its run or job log endpoint returns `404`, classify the cause as
  untriaged infrastructure or publication evidence, keep the gate blocked,
  and wait for the current-head CodeQL dispatch; do not blind-rerun the same
  head or weaken the gate. A later successful result counts only when its run
  and target SHA match the exact current head.

- GitHub Actions run-list access is a separate evidence surface from the PR
  check rollup. A `gh run list` or Actions API `403` can occur while ordinary
  REST/PR reads still work; record it as unavailable run-detail evidence, not
  as a failed job or proof that the process stopped. Keep the exact PR head,
  use the available check rollup and job/log endpoints when authorized, and
  retry only after the access limit or permission condition changes.

- `CLEAN` with no reported required Checks is not protected-merge evidence.
  Stacked or non-protected bases can legitimately report no required checks;
  retain the exact head/base and verify the target protected branch's ruleset,
  qualifying review, and hosted checks before treating a PR as merge-ready.

- Before pushing a repair, compare the worktree branch with the PR's live
  `headRefName`, head owner, base ref, and exact head. A similarly named branch
  can be a different PR source; never assume a successful push updated the
  intended PR. If the source branch cannot be safely updated, preserve the
  commit on its own branch and open a stacked successor that names the
  predecessor and proves the inherited delta.

- A review bot's `skipped` result on a non-default stacked base is not a
  qualifying review and must not be promoted to approval. Keep the successor
  linked to its predecessor, record the exact head/base, and require an
  independently qualifying review on a supported base before protected merge.

## Phase 10 development rules

- **Stepwise execution**: Each phase requires an atomic PR, GitHub PR Tracking,
  Push, and Robot Review. A phase ends only when its PR is protected-merged or a
  successor's exact tree, effective diff, tests, and lineage record independently
  prove complete-delta succession. While it waits, continue independent work
  that does not consume or contradict the pending delta.
- **TDD + DDD**: Practice TDD, micro TDD, nano TDD, Domain Driven Development, and Context Driven Development.
- **API Wiring**: Always work with API wiring completed.
- **Collaboration**: Respect other agents' concurrent work; do not overwrite or dismiss unfamiliar changes.
- **Subagent Delegation**: Actively delegate tasks to Subagents.
- **UI/Browser Testing**: Use a real browser for testing (do not rely on assumptions).
- **Strict Errors**: Treat `Timeout`, `Fatal`, `Warn`, and `Denied` outputs as hard failures.
- **Goal**: Converge open PRs through protected merges or verified full-delta
  succession, never through count-only closure.

- When the gate exhausts fallbacks after the primary model produces a finding at or above threshold and then fails with a retryable error (like `NOT_FOUND`), ensure the final output explicitly reports `Strix quick scan failed with a non-recoverable error.` to prevent downgrading the finding to pass or misleadingly reporting an unavailability error.

## Code-owner review gates — disabled (on hold)

As of 2026-08-04, code-owner review requirements (`require_code_owner_reviews` in branch
protection, `require_code_owner_review` in rulesets) are disabled across the ContextualWisdomLab
org: there is a single maintainer (solo developer), so a code-owner approval gate can never be
satisfied. This is ON HOLD until the org has multiple maintainers — do NOT re-enable these
settings or add CODEOWNERS-based merge gates before then.
