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
  `trivy --download-db-only` first, and scan the **merge ref**, not just the PR
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

- When available, use `autoresearch` for an autonomous review-repair loop,
  `babysit-pr` for protected-merge observation, and `git-commit-format` before
  committing; use `agents-md` when changing this file. If one is unavailable,
  perform the same steps directly: keep an
  evidence log, poll current-head checks without treating pending work as a
  failure, and use the repository's conventional commit history as the format
  contract. Use CodeGraph before broad source searches when an index exists;
  apply `humanize-korean` to Korean prose when that shared skill is available.
  Prefer repository-local
  `fix-development-mistakes`, `github-actions-privileged-pr-scan`, and
  `github-robot-review-gate` skills for their matching repair, privileged
  scanner, and review-gate work; read the selected `SKILL.md` completely.
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
- For every open PR, repeat: fetch the exact remote base and head, inspect
  current-head reviews and unresolved threads, reproduce failed checks from
  their logs, repair the canonical owner, run focused tests plus the applicable
  contract/security suite, push without force, and re-fetch evidence. A new
  head invalidates earlier reviews and checks.
- Before creating a worktree or restacking a branch, compare `git ls-remote`
  with the local remote-tracking ref and start from the verified 40-character
  SHA. Never guess or manually extend abbreviated SHAs in commits, PR bodies,
  release evidence, or gap baselines.
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
- Preserve unrelated dirty or untracked files. If a command changes the wrong
  checkout, stop before editing or pushing, record the reflog evidence, restore
  only the affected branch with a non-destructive detached-head and branch-ref
  move, and verify the original checkout and untracked files afterward.
- Tests invoked with `--noconftest` must bootstrap every required setting in
  the test or trusted workflow step. Use explicit test-only values and fresh
  random secrets; do not weaken production validation or depend on a developer
  shell's environment.
- Exact changed-line review evidence must be generated only from real
  current-head added or modified lines. Do not invent line 1 for deleted-only,
  binary, oversized, or otherwise ineligible files, and do not relax the
  validator to accept a fabricated receipt; fail closed or repair the canonical
  receipt producer.
- Do not present a heuristic as a security, AI-quality, or completion
  guarantee. State its evidence boundary and replace it at the canonical owner
  when the workflow requires an enforceable contract.
- Pending or queued reviews and checks are wait states. Continue safe work on
  another gap. Before calling a PR merge-ready, freshly verify the exact head
  and base, live rulesets, required checks, unresolved threads, and applicable
  current-head CodeRabbit or structured OpenCode fallback evidence. After the
  merge, verify the merge commit and protected target branch.
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
  The only permitted temporary required-context adjustment is the documented
  stale-context procedure in `docs/development/merge-gate-policy.md`: capture
  equivalent current-head evidence, make a reversible ruleset change, restore
  the context after protected-branch repair, and rerun its evidence. It does not
  authorize suppressing a product or security finding.
- Model-backed OpenCode, Strix, and Noema workflows request only
  `contextual-orchestrator/orchestrator/free` with the gateway credential.
  Provider discovery, capability routing, and fallback belong to the
  orchestrator; consumer workflows do not carry provider names, direct-provider
  credentials, or paid fallbacks. Verify the requested logical model, endpoint,
  served-model metadata, and terminal response in the same run.
- Keep private-source review fail closed and ZDR-only. Never log or copy bearer
  tokens, provider credentials, request payloads, or secret-derived values.
  Repair shared sidecar startup, credential bootstrap, timeout handling, and
  response normalization where all review paths converge.
- Do not impose a shared application, agent, or gateway wall-clock timeout on
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
  -q`, `corepack pnpm@11.5.3 --dir frontend test --runInBand` when frontend
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
- Docker Compose and Podman live-E2E work must clean up after itself. Stop
  stale `naruon*` containers, remove unused volumes/layers with
  `podman system prune --all --volumes --force` when safe, and verify
  `podman ps` has no stale Naruon services. If Podman reports broken storage
  metadata such as missing overlay layers or `readlink ... overlay: invalid
  argument`, run `podman system check --repair --force` before relying on
  `podman system df` or additional image scans.
- Keep contributor setup friction low: document any new required environment
  variables, model tags, package-manager version pins, or live-E2E ports in the
  same PR that introduces them, and avoid hidden local-only defaults that make
  another committer's PR fail after checkout.

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
