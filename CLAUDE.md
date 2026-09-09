# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read AGENTS.md first

`AGENTS.md` at the repo root is the canonical agent operating guide. Read it
fully and follow its guardrails before making changes — it records the
release-governance, PR-automation, security-boundary, and anti-pattern rules
that reviews enforce. This file only complements it with commands and a
high-level architecture map; when in doubt, `AGENTS.md` wins. The frontend has
its own `frontend/AGENTS.md` (the installed Next.js differs from training
data — read `node_modules/next/dist/docs/` before writing frontend code).

Default branch is `develop`. PRs use `.github/PULL_REQUEST_TEMPLATE.md` and are
merged by metadata-only robot governance (see
`docs/development/merge-gate-policy.md`); OpenCode Review, Strix Security Scan,
and the merge scheduler come from central workflows in
`ContextualWisdomLab/.github` — do not reintroduce repo-local copies.

## Common commands

### Backend (FastAPI, Python, in `backend/`)

```bash
cd backend
python3 -m pip install -r requirements.txt   # CI: --require-hashes -r requirements-hashes.txt
python3 scripts/migrate_db.py                # Alembic upgrade head (managed path)
python3 -m pytest -q                         # full test suite
python -m pytest tests/test_tasks_api.py -q  # single test file
python -m ruff check .                       # lint (CI-enforced)
uvicorn main:app --reload                    # local dev server only
```

- CI runs backend tests with `PYTHONWARNINGS=error` and
  `DISABLE_BACKGROUND_WORKERS=1`, then fails the job if the pytest output
  contains `Timeout`, `Fatal`, `Warn`, or `Denied`. Match that locally for
  merge evidence.
- Containers never run `uvicorn main:app` directly; the entrypoint is
  `python scripts/start_backend.py`, which validates required settings first.
- `scripts/bootstrap_db.py` is the local/dev-only schema compatibility path;
  Alembic history under `backend/alembic` is authoritative.

### Frontend (Next.js, in `frontend/`, pnpm@11.5.3)

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm test                                    # vitest run
npm test -- src/lib/api-client.test.ts       # single test file
pnpm run lint                                # eslint
pnpm run build
pnpm run typecheck
pnpm run dev
npm run test:e2e -- tests/e2e/dashboard-branding.spec.ts   # Playwright (set LIVE_BASE_URL for live stacks)
```

### Whole-repo verification

```bash
./scripts/verify_threading.sh        # backend threading tests + frontend test/lint/build
bash scripts/ci/test_pr_governance_gate.sh   # PR governance gate self-test
```

Before opening a PR, run the focused tests that cover the changed contract and
put the exact commands in the PR body (see `AGENTS.md` and `CONTRIBUTING.md`).

### Docker Compose stacks

The blessed local stack is `docker-compose.yml` (Postgres+pgvector, an Ollama
container with `gemma4:e2b-it-qat` and `embeddinggemma` baked in via
`Dockerfile.ollama`, the FastAPI backend, and the Next.js frontend). Start it
through the wrapper, which resolves the env file as
`NARUON_ENV_FILE` > `~/.env` > `./.env` and passes it only as an interpolation
source (never mount `~/.env` as a Compose `env_file`):

```bash
./scripts/naruon_compose.sh up -d --build
./scripts/naruon_compose.sh exec backend python import_fixtures.py
```

The other compose files are purpose-specific evaluation/evidence stacks:

- `docker-compose.live-e2e.yml` — live E2E evidence: pre-built
  `BACKEND_IMAGE`/`FRONTEND_IMAGE`, migrate/seed marker containers, nginx at
  `127.0.0.1:18080`.
- `docker-compose.gateway.yml` — Traefik + Keycloak edge/OIDC evaluation
  gateway in front of backend/frontend images.
- `docker-compose.infra.yml` — hardened infra evaluation (Traefik, Prometheus,
  Grafana, Loki, Tempo, otel-collector, Keycloak) with the repo hardening
  contract (`no-new-privileges`, `read_only`, tmpfs mounts).
- `docker-compose.observability.yml` — Prometheus/Grafana/Loki/Tempo only.
- `docker-compose.apm.yml` — minimal Prometheus + Jaeger (OTLP) pair.
- `docker-compose.postgres-ha.yml` — Postgres physical-replication drill
  (primary + `pg_basebackup` replica); driven by `scripts/postgres_ha_drill.sh`.

`DATABASE_URL`, `AUTH_SESSION_HMAC_SECRET`, and `ENCRYPTION_KEY` have no code
defaults anywhere; Compose/Kubernetes/operators must inject them, and startup
fails closed when they are missing.

## Architecture

Naruon is an AI email workspace: a web client/control plane over
member-configured, customer-owned mail, CalDAV/CardDAV, and WebDAV systems. It
is **not** an SMTP/IMAP server, MX host, or mailbox capacity provider — the
customer systems stay the source of truth, and Naruon stores bounded metadata,
indexes, and auditable writeback intent. `ARCHITECTURE.md` and
`docs/architecture/` are the detailed references.

```
Next.js frontend ──> FastAPI backend (control plane) ──> Postgres + pgvector
                            │
                            ├──> contextual-orchestrator consumer boundary
                            │      └──> provider/model routing owned by contextual-orchestrator
                            └──> outbound-only self-hosted connector (connector/)
                                     └──> customer IMAP/POP3/SMTP + CalDAV/CardDAV/WebDAV
```

Naruon owns product behavior and model-call authorization, but not provider/model routing.
Production model work requires an immutable released `contextual-orchestrator`
API/client/schema; a missing or incompatible owner contract fails closed instead
of falling back to a direct provider. The Ollama/MLX paths in local Compose are
explicit non-production development fixtures. Central model-backed GitHub Actions
are owned by `ContextualWisdomLab/.github` and use `orchestrator/free`; do not copy
that pool selection into Naruon runtime. Verify protected release evidence before
claiming the owner contract is available; an open PR or unreleased branch is only
proposed evidence.

- `backend/` — FastAPI app (`main.py`, routers in `api/`, domain logic in
  `services/`, SQLAlchemy models in `db/`, Alembic in `alembic/`). Owns
  persistence, canonical email threading
  (`services/threading_service.py` is the only thread-id assignment owner),
  vector search, AI summaries, ticket tasks, and server-authoritative
  calendar/WebDAV writeback intents. Authorization is deny-first RBAC + ABAC.
- `frontend/` — Next.js workspace shell (Today dashboard, Mail, Calendar,
  Tasks, Projects, Context Search, AI Hub, Data, Security, Settings). Browser
  writes go through the same-origin `/api/*` proxy, which converts the HttpOnly
  `naruon_session` cookie into the backend `Authorization: Bearer` session.
  Never store tokens in `localStorage`/`sessionStorage` or emit public identity
  headers (`X-User-Id`, `X-Organization-Id`, etc.).
- `connector/` — the self-hosted connector: an outbound-only WebSocket client
  to the control plane (`wss://naruon.net/ws/runner/{registration_token}`) that
  executes only configured local adapters (IMAP fetch, SMTP send,
  ETag/If-Match-guarded CalDAV/WebDAV PUT). Without an adapter it fails closed
  with `adapter_not_configured` and `provider_write_executed=false` — never
  return placeholder success.
- `Dockerfile` — three stages: `backend-runtime`, a pnpm frontend build, and a
  combined non-root image that serves both; `k8s/` and `render.yaml` deploy it.
- Provider writes are explicit opt-in (`execute_provider=true`) and
  conflict-aware (opaque `source_uid` selection, capability checks,
  ETag/If-Match); intents are the default response.
- Auth: signed HS256 bearer sessions (HMAC via `AUTH_SESSION_HMAC_SECRET`) or
  enterprise OIDC/JWKS; private `/api/*` routers register the default
  `get_auth_context` dependency. Naruon owns domain tools, authorization, and
  context assembly; provider/model routing belongs to `contextual-orchestrator`.
  Existing direct-provider `base_url` surfaces are legacy migration debt and must
  not be extended as production routing authority; keep their SSRF controls until
  they are removed. OIDC/SMTP/IMAP/POP3 hosts remain strict egress allowlists
  that resolve only to pinned global addresses.
- CI (`.github/workflows/`): `app-ci.yml` (backend ruff+pytest, frontend
  test/lint/build), plus `bandit`, `codeql`, `trivy`, `scorecard`,
  `pr-governance`, `docker-publish` (GHCR on `v*` tags matching `VERSION`), and
  `mail-smoke`. Actions are pinned to full commit SHAs.
- Topic intelligence is **not implemented**. Never use lexical frequencies,
  embeddings, zero-shot labels, or request-time LLM labels as an STM result.
  The retained `keyword_extractor` is lexical metadata only. Any future adapter
  is blocked on a versioned fitted TEPP artifact/API with frozen preprocessing,
  mixed-membership uncertainty and diagnostics; absence or incompatibility
  fails closed. Start at `docs/topic-intelligence/README.md` and
  `docs/adr/0001-topic-measurement-authority.md`.

## Key conventions

- Treat `Timeout`, `Fatal`, `Warn`, or `Denied` in any execution output as a
  hard failure; tests must pass without them.
- TDD is expected: add or update tests before production code changes, and
  keep each PR an atomic, focused change.
- Never expose sequential database ids through APIs or UI — use opaque public
  ids (`task_uid`, `source_uid`, `folder_uid`, `document_id`). New tables and
  columns use at least two-word `snake_case` names (`task_title`, not `title`).
- Alembic migrations use structured operations (`op.create_index`, …), never
  `sa.text(f"...")` DDL.
- Services return deterministic `error_code` values; routes must not derive
  HTTP status from message substrings. Error responses stay honest and do not
  leak internals or credential-type details (see "Error-message contract" in
  `README.md`).
- Never commit `.env`, real mailbox exports, or credentials; email fixtures in
  `backend/tests/fixtures` stay small and synthetic.
- Release bumps keep `VERSION`, `CHANGELOG.md`, `frontend/package.json`, and
  FastAPI app metadata synchronized; the backend reads its version from
  `VERSION`.
- When a review uncovers a recurring bug pattern, record the anti-pattern in
  `AGENTS.md` and update the affected tests/mocks/docs in the same PR.
