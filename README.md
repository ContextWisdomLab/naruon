# Naruon AI Email Workspace

[![Application CI](https://github.com/ContextualWisdomLab/naruon/actions/workflows/app-ci.yml/badge.svg)](https://github.com/ContextualWisdomLab/naruon/actions/workflows/app-ci.yml)
[![Bandit Security Scan](https://github.com/ContextualWisdomLab/naruon/actions/workflows/bandit.yml/badge.svg)](https://github.com/ContextualWisdomLab/naruon/actions/workflows/bandit.yml)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ContextualWisdomLab/naruon)

Full-stack AI workspace with a FastAPI backend, Next.js frontend, vector search,
AI summaries, hardened email threading, and relay/proxy contracts for external
mail/calendar/file systems.


## Quick Links
- [Installation & Setup](#five-minute-local-path)
- [Architecture](docs/architecture/)
- [Topic-intelligence documentation set](docs/topic-intelligence/README.md)
- [Architecture decisions](docs/adr/README.md)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## North-star scope contract

- Naruon is not an SMTP server, IMAP server, MX host, or mailbox capacity
  provider. It is a web client/control plane that works through member-configured
  providers and customer-owned systems.
- Customer mail, CalDAV/CardDAV, and WebDAV accounts remain the source of truth;
  Naruon stores bounded metadata, indexes, preferences, and auditable action
  intent rather than replacing those systems.
- Private-network protocols use an outbound-only self-hosted connector to
  `naruon.net`; GitHub self-hosted runners are CI smoke infrastructure, not the
  production connector itself.
- Calendar/file/contact writeback is opt-in, server-authoritative, and
  conflict-aware through source capabilities, provenance, ETags/If-Match, and
  audit logs.
- Access control is universal RBAC plus ABAC: data-region, consent, workspace,
  group, source capability, and customer-policy denies take precedence over broad
  role allows. A permitted `platform_admin` can cross organization and resource
  ownership boundaries for platform operations, but not data-region or consent
  denies.
- Keycloak is the default enterprise OIDC evaluation target; Casdoor remains a
  lighter alternative. Traefik and OpenTelemetry are evaluated for edge policy and
  open-source observability.
- PR automation is metadata-only inside this repository and uses current-head
  robot-review evidence plus required checks. Human approval is not awaited by
  default under repo policy.
- OpenCode Review, Strix Security Scan, and PR Review Merge Scheduler are
  supplied by the ContextualWisdomLab central required workflows from
  `ContextualWisdomLab/.github`. This repository does not carry repo-local
  OpenCode, Strix, or merge-scheduler workflow copies; branch updates,
  auto-merge, and mechanical merge actions run as the target repository's
  `github-actions[bot]` through the central workflow. Pending CodeRabbit or
  required-check evidence is a wait state, not a hard blocker.
- Local OpenCode contributor runs use contextual-orchestrator's fixed loopback
  OpenAI-compatible endpoint at `http://127.0.0.1:8100/v1`. Set a short-lived
  owner-issued `CONTEXTUAL_ORCHESTRATOR_TOKEN`; do not substitute an upstream
  provider key. OpenCode sends it as the standard `Authorization` header, which
  the Fetch transport removes on a cross-origin redirect. This value configures
  OpenCode only, not Naruon.
- Topic intelligence is not currently a live Naruon capability. The lexical
  `keyword_extractor` is metadata only; Naruon fails closed rather than present
  keyword, embedding, or LLM labels as Structural Topic Modeling. The product,
  technical, architecture, contract, security, UML, conceptual ERD, test, and
  operability records are indexed in
  [`docs/topic-intelligence/`](docs/topic-intelligence/README.md).
- Security governance is source-backed through signed
  `/api/security/access-surface`. The endpoint reads scoped WebDAV, CalDAV, and
  connector evidence plus durable `security_audit_events`, reuses the deny-first
  RBAC/ABAC policy engine, and returns no sequential account ids, browser-facing
  source/event/decision identifiers, provider-write execution flags, raw
  credentials, legacy unscoped audit rows, or fake security posture claims.
  HMAC fallback sessions are not accepted as authoritative workspace-membership
  evidence for this security posture surface; enterprise OIDC/JWKS or an
  explicit server-side membership path must establish the workspace boundary.
- Data quality is source-backed through signed `/api/data/quality-surface`.
  The endpoint summarizes scoped repositories, workspace documents, recent
  email-attachment file assets, ingestion inventory, embedding coverage,
  quality checks, and connector evidence from existing rows, returns
  `provider_write_executed=false`, and does not expose provider credentials,
  raw usernames, server URLs, message bodies, raw message/thread ids, or
  sequential ids. The Data workspace lets operators upload a signed-session
  workspace document, request document reparse, embedding regeneration intent,
  HWP conversion intent, and explicit WebDAV document materialization. The
  materialization route re-reads the selected `document_id` from the signed
  workspace, derives the provider path and Markdown content server-side, and
  dispatches `write_webdav` only when the caller explicitly requests
  `execute_provider=true`.
- Projects are source-backed through signed `/api/webdav/folders` and
  `/api/tasks`. The workspace derives project boundaries from customer-owned
  WebDAV folders, task progress from opaque public ticket ids, and labels
  provider writes as deferred intent work.
- Custom LLM provider `base_url` calls fail closed unless the host is
  exact-allowlisted, HTTPS-only, and resolved to global addresses. Runtime calls
  use a pinned-address `httpx` transport so DNS is not resolved a second time
  after validation.
- OIDC issuer and JWKS URLs follow the same outbound fetch posture:
  exact-allowlisted HTTPS hosts must resolve only to global addresses, and JWKS
  preload fetches connect to the validated pinned address while keeping TLS/SNI
  on the allowlisted hostname.
- Session authority is assigned by the verified HMAC or OIDC code path, not by a
  `_session_verifier` JWT payload claim supplied inside the token.

## Agentic Ontology & Auto-Organization

- **Sender ontology**: The backend classifies sender relationships and returns a
  deterministic next-action hint, such as reply/task tracking for colleagues or
  summary-first handling for newsletters. Relationship graph reads can be
  filtered by source message/thread ids so the Search workspace can show the
  sender DAG beside the originating mail context. If no relationship exists for
  the selected search result, the browser can call signed
  `/api/ontology/relationships/capture-source`; the backend re-reads the source
  email under owner/organization scope and derives the thread provenance
  server-side before storing the relationship.
- **Self-sent knowledge capture**: IMAP-imported emails sent from a user to the
  same address now create one idempotent, source-linked `self_sent_knowledge`
  ticket task with a plain-text memo title. The Tasks workspace can request a
  signed WebDAV/Notes materialization intent for that task and shows the planned
  customer-owned target with `provider_write_executed=false`; connector-side
  WebDAV/CalDAV PUT adapters now enforce `If-Match`, and
  `execute_provider=true` dispatches the signed materialization command to an
  active outbound runner. Durable retry queues and extended execution audit
  workflows remain future work.
- **Pending reply dashboard**: the Today dashboard reads signed
  `/api/emails/pending-replies?limit=3` data and shows sent-mail reply waits in
  Home KPIs and judgment points. Pending replies are calculated from
  customer-owned mailbox metadata; Naruon does not host the mailbox or fabricate
  provider writes.
- **Overdue reply follow-up**: Home and Tasks can call signed
  `POST /api/tasks/reply-sla-escalations` to convert overdue pending sent-mail
  replies into opaque, source-linked `reply_sla` ticket tasks. Escalation reuses
  server-side reply tracking, keeps generated titles plain text, and does not
  mutate the customer's email provider.

## Five-minute local path

```bash
cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import base64
import secrets

env_path = Path(".env")
env_values = {}
for line in env_path.read_text().splitlines():
    if "=" not in line or line.lstrip().startswith("#"):
        continue
    key, value = line.split("=", 1)
    env_values[key] = value

db_password = secrets.token_urlsafe(32)
env_values.update(
    {
        "POSTGRES_DB": "ai_email",
        "POSTGRES_USER": "naruon_local",
        "POSTGRES_PASSWORD": db_password,
        "DATABASE_URL": (
            "postgresql+asyncpg://naruon_local:"
            f"{db_password}@localhost:5432/ai_email"
        ),
        "AUTH_SESSION_HMAC_SECRET": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    }
)

existing_lines = env_path.read_text().splitlines()
existing_keys = {
    line.split("=", 1)[0]
    for line in existing_lines
    if "=" in line and not line.lstrip().startswith("#")
}
required_lines = [f"{key}={value}" for key, value in env_values.items() if key not in existing_keys]
env_path.write_text("\n".join(existing_lines + required_lines) + "\n")
PY
./scripts/naruon_compose.sh up -d --build
./scripts/naruon_compose.sh exec backend python import_fixtures.py
curl -s http://localhost:8000/api/emails
python3 -m webbrowser http://localhost:3000
```

### Apple Silicon / MLX local path (OS별 로컬 API 모델 서버 사용)

기본 `docker-compose.yml`는 Linux Ollama 컨테이너를 그대로 유지합니다. Apple Silicon
로컬 실 테스트(또는 외부 MLX/OpenAI-compatible 서비스)만 분리하려면 임시 오버라이드 파일을 붙여 실행합니다.

```bash
# 다음 블록은 로컬 실사용 검증용 샘플입니다. 민감한 쿼리로 대체할 수 있지만,
# 현재 실검증에서는 아래 두 키워드로 테스트합니다.
cat > .env.mlx <<'EOF'

# 기존 보안값은 그대로 두고, 로컬 모델 경로만 오버라이드
OPENAI_API_KEY=mlx
ALLOWED_LLM_BASE_URL_HOSTS=localhost,127.0.0.1,host.docker.internal
ALLOW_LOCAL_LLM_PROVIDERS=true
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_EMBEDDING_MODEL=embeddinggemma
OPENAI_MODEL=gemma4:e2b-it-qat
# 포트 충돌이 있으면 아래 두 값으로 변경
NARUON_FRONTEND_HOST_PORT=127.0.0.1:3000
NARUON_BACKEND_HOST_PORT=127.0.0.1:8000
# Linux에서만 host-gateway가 필요합니다.
NARUON_MLX_EXTRA_HOSTS=host-gateway
NARUON_MLX_ALLOWED_LLM_BASE_URL_HOSTS=localhost,127.0.0.1,host.docker.internal
NARUON_MLX_OPENAI_API_KEY=mlx
NARUON_MLX_BASE_URL=http://host.docker.internal:11434/v1
NARUON_MLX_EMBEDDING_MODEL=embeddinggemma
NARUON_MLX_LLM_MODEL=gemma4:e2b-it-qat
EOF

# 로컬에서만 쓰는 compose 오버라이드는 임시 파일로 만들고 커밋하지 않습니다.
# OS 분기 없이 환경변수 하나로 host.docker.internal 매핑을 제어합니다.
# Linux에서 host-gateway가 필요한 환경이면 .env.mlx에서 NARUON_MLX_EXTRA_HOSTS를 덮어씁니다.
# Apple Silicon 검증 기준: 백엔드는 host.docker.internal:11434의 MLX(OpenAI-compatible)
# 엔드포인트로 바로 연결해 Ollama 컨테이너 의존을 피합니다.
mlx_compose_override="$(mktemp "${TMPDIR:-/tmp}/docker-compose.mlx.XXXXXX.yml")"
cat > "$mlx_compose_override" <<'EOF'
services:
  backend:
    depends_on:
      db:
        condition: service_healthy
    environment:
      ALLOW_LOCAL_LLM_PROVIDERS: "true"
      ALLOWED_LLM_BASE_URL_HOSTS: ${NARUON_MLX_ALLOWED_LLM_BASE_URL_HOSTS:-localhost,127.0.0.1,host.docker.internal}
      OPENAI_API_KEY: ${NARUON_MLX_OPENAI_API_KEY:-mlx}
      OPENAI_BASE_URL: ${NARUON_MLX_BASE_URL:-http://host.docker.internal:11434/v1}
      OPENAI_EMBEDDING_MODEL: ${NARUON_MLX_EMBEDDING_MODEL:-embeddinggemma}
      OPENAI_MODEL: ${NARUON_MLX_LLM_MODEL:-gemma4:e2b-it-qat}
    extra_hosts:
      - "host.docker.internal:${NARUON_MLX_EXTRA_HOSTS:-host.docker.internal}"
    ports:
      - "${NARUON_BACKEND_HOST_PORT:-127.0.0.1:8000}:8000"
  frontend:
    ports:
      - "${NARUON_FRONTEND_HOST_PORT:-127.0.0.1:3000}:3000"
EOF

NARUON_ENV_FILE=.env.mlx \
docker compose --env-file .env.mlx -f docker-compose.yml -f "$mlx_compose_override" up -d --build

# 혹시 모델 엔드포인트 미노출이 있을 경우는 위 명령 직전에 로컬 MLX 서버/게이트웨이를
# 먼저 확인합니다. (호스트는 본인 환경별로 달라질 수 있음)
curl -sf http://127.0.0.1:11434/v1/models >/dev/null && \
  echo "MLX/OpenAI-compatible server is reachable" || \
  echo "MLX endpoint is not reachable on 127.0.0.1:11434"
```

실 메일 임포트 + 요약/초안 검증:

```bash
# 아래 두 --query는 실 사용자 공개 테스트 키워드입니다.
MAIL_DIR="/Users/seonghobae/Library/Mobile Documents/com~apple~CloudDocs/Downloads/mail"
if [ ! -r "$MAIL_DIR" ]; then
  echo "ERROR: cannot read $MAIL_DIR (Apple CloudDocs 권한 또는 path 접근 권한 점검 필요)"
  echo "대체: 실 메일 파일을 별도 로컬 폴더에 복사한 뒤 MAIL_DIR을 교체해 재실행"
  exit 1
fi

AUTH_SESSION_HMAC_SECRET="$(grep -E '^AUTH_SESSION_HMAC_SECRET=' .env | cut -d= -f2-)"
python3 backend/scripts/private_mail_http_smoke.py \
  --mail-dir "$MAIL_DIR" \
  --base-url http://127.0.0.1:3000 \
  --frontend-base-url http://127.0.0.1:3000 \
  --api-base-url http://127.0.0.1:8000 \
  --session-secret "$AUTH_SESSION_HMAC_SECRET" \
  --query "중공업 전력PU 회의록" \
  --query "중공업 기전PU 회의록" \
  --match-mode all-terms \
  --limit 20 \
  --batch-size 6 \
  --require-browser-visible \
  --llm-smoke \
  --print-session-token
```

`--print-session-token`이 켜진 경우 스크립트가 같은 토큰을 브라우저로 전파하는
`/auth/session` 호출 예시를 출력합니다. 위 출력의 JS 한 줄을 앱 콘솔에서 실행하면
`naruon_session` 쿠키가 갱신되어 API로 임포트한 메일이 브라우저와 동일 세션에서 보입니다.
`session_check=ok` 로그는 세션 클레임이 브라우저에서 확인되었음을 뜻하고,
`session_check=failed(...)`는 토큰 검증/클레임 파싱 문제가 있음을 뜻합니다.
`--require-browser-visible`은 동일 토큰을 `Cookie: naruon_session=...`로 주입해
`/api/emails` 응답을 조회해 브라우저 프록시 경로까지 반영 확인이 되도록 합니다.

동기화 지연이 큰 환경에서는 재시도 옵션을 조정할 수 있습니다.

```bash
  --search-retry-attempts 5 \
  --search-retry-delay-seconds 1.2 \
  --inbox-retry-attempts 5 \
  --inbox-retry-delay-seconds 1.2
```

실제 브라우저 검증 순서:

1) 브라우저에서 `http://127.0.0.1:3000` 접속 후 `"/mail"`로 이동
2) 방금 입력한 키워드 중 하나로 검색
3) `/mail` 결과 목록에서 임포트된 메일을 열어 상세가 정상 표시되는지 확인
4) 동일 이메일 상세 화면에서 요약/초안 버튼이 작동하고(`llm=ok`, `draft=ok` 또는 UI 동작),
   브라우저 세션 값(`session_check=ok`)이 스크립트 출력에 남아있는지 확인
   - 브라우저에서 동일 이메일을 선택한 뒤 LLM 요약/초안 버튼 동작 확인
5) 세션 불일치 의심 시 `session_check=failed(...)` 또는 `session_check=skipped(...)`가
   출력되면 `--print-session-token`의 콘솔 스니펫을 다시 실행하고 새로고침 후 2~4단계를 반복

실행 전 체크(빠른 사전 진단):

```bash
# Podman/Docker 런타임 연결 확인
podman system connection ls

# MLX(OpenAI-compatible) 엔드포인트 노출 확인
curl -sf http://127.0.0.1:11434/v1/models | head

# 기존 웹 서비스(Nginx/프록시)가 3000/8000/11434를 가로채고 있지 않은지 확인
lsof -iTCP:3000 -sTCP:LISTEN
lsof -iTCP:8000 -sTCP:LISTEN
lsof -iTCP:11434 -sTCP:LISTEN
```

백엔드 API를 바로 확인하려면(필요 시):

```bash
curl -s http://127.0.0.1:3000/api/emails?limit=10
# 아래는 동일 샘플로 API 직접 점검하는 예시입니다.
curl -s -X POST http://127.0.0.1:3000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "중공업 전력PU 회의록", "limit": 3}'
```

세션이 다르게 보이면 `/auth/session` 동기화 콘솔 코드를 다시 실행한 뒤 새로고침 합니다.

What you should see: the fixture import loads a three-message `Quarterly plan`
conversation. `/api/emails` returns one threaded inbox item with `reply_count`
greater than 1, and the frontend shows conversation history oldest to newest.
First-run frontend sessions open the Today execution dashboard by default, with
explicit entry points to the email workspace and calendar-first workspace.

The fixture importer uses real OpenAI embeddings only when `OPENAI_API_KEY` is
set. With the default empty key it writes local zero-vector embeddings so the
threading proof path works offline.

Backend settings read environment variables first, then `.env`, `../.env`, and
`~/.env`. `DATABASE_URL`, `AUTH_SESSION_HMAC_SECRET`, and `ENCRYPTION_KEY` still
have no code defaults; Compose and Kubernetes must inject them explicitly before
runtime. `docker compose build backend frontend` is intentionally allowed to
parse without local secrets because image builds do not need database or session
credentials. `docker compose up` still fails closed inside the database/backend
startup path when `POSTGRES_PASSWORD`, `AUTH_SESSION_HMAC_SECRET`, or
`ENCRYPTION_KEY` are missing. For Compose, `./scripts/naruon_compose.sh` reads
`${NARUON_ENV_FILE}` when set, otherwise uses `~/.env` if present, and falls back
to the project `.env`. It passes that file to Docker Compose only as an
interpolation source so the backend service receives the whitelisted variables
in `docker-compose*.yml`, not every local secret present in `~/.env`. The
backend image starts through
`python scripts/start_backend.py`, which checks the same required settings before
`uvicorn` imports the app. A direct `docker run` therefore still needs explicit
environment injection through `--env`, an orchestrator secret, or a minimal
Naruon-specific env file containing only the backend settings needed by the
container.

## Manual development path

Backend:

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 scripts/migrate_db.py
python3 -m pytest -q
uvicorn main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm test
npm run lint
npm run build
npm run dev
```

`next.config.ts` applies a best-effort local guard for build worker fan-out and
static generation concurrency (`NEXT_BUILD_CPUS=2`,
`NEXT_STATIC_GENERATION_MAX_CONCURRENCY=2`,
`NEXT_STATIC_GENERATION_MIN_PAGES_PER_WORKER=50`) so constrained CI/build
machines do not fan out excessive Node/PostCSS workers. Treat the Next.js CPU
knob as experimental and enforce authoritative limits through CI, Docker, or the
runner. Raise those values only with explicit build evidence.

## Threading proof points

- Canonical thread IDs are assigned in `backend/services/threading_service.py`.
- Parser output preserves raw `Message-ID`, `In-Reply-To`, `References`, and
  `Reply-To` headers.
- Importers persist the canonical service-assigned `thread_id`; they do not
  recompute their own thread IDs.
- Signed email file imports accept `.eml`, `.zip`, and `.mbox` uploads through
  `/api/emails/import-files`; imported email and attachment vectors use the
  active organization embedding model such as local `embeddinggemma` when an
  LLM provider is configured.
- Duplicate ZIP/forward candidates can be checked through signed
  `/api/emails/unique-thread-intent`. The intent uses normalized Message-ID and
  strong body fingerprint matches, returns canonical thread metadata, and does
  not execute provider writes or irreversible DB merges.
- IMAP imports store the strong body fingerprint when message body content is
  available, preserving the older lightweight fingerprint only as a fallback.
- Subject-only `Fwd:` or `Re:` matching is not a valid duplicate/thread merge
  signal. Forwarded threading must come from Message-ID, References,
  In-Reply-To, or future persisted duplicate provenance.
- Replies include `In-Reply-To` and `References` headers in the send payload.
- Development sends are explicit simulations unless a real SMTP path is wired.

## API smoke examples

The backend accepts only signed bearer sessions. For local smoke tests, generate
a local-only `AUTH_SESSION_HMAC_SECRET`, start the API with that exact value, and
then mint a short-lived fixture token from the same shell:

```bash
export AUTH_SESSION_HMAC_SECRET="$(python3 - <<'PY'
import secrets

print(secrets.token_urlsafe(48))
PY
)"
export NARUON_DEV_BEARER="$(python3 - <<'PY'
import base64, hashlib, hmac, json, os, time

secret = os.environ["AUTH_SESSION_HMAC_SECRET"].encode()
payload = {
    "ver": 1,
    "iss": "naruon-control-plane",
    "aud": "naruon-api",
    "sub": "default",
    "role": "organization_admin",
    "org": "default",
    "groups": [],
    "workspace": "default",
    "exp": int(time.time()) + 300,
}
enc = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
header = enc(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
body = enc(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
sig = enc(hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest())
print(f"{header}.{body}.{sig}")
PY
)"
```

```bash
curl -s http://localhost:8000/api/emails \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  | jq '.emails[] | {subject, thread_id, reply_count}'
curl -s http://localhost:8000/api/emails/thread/thread-root@example.com \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  | jq '.thread[] | {message_id, in_reply_to, references}'

# Requires a tenant OpenAI key because search generates a query embedding.
curl -s -X POST http://localhost:8000/api/search \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  -H 'content-type: application/json' \
  -d '{"query":"Quarterly plan"}'

# Send remains honest in local/dev mode: missing SMTP config returns 400.
curl -s -X POST http://localhost:8000/api/emails/send \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  -H 'content-type: application/json' \
  -d '{"to":"alice@example.com","subject":"Re: Quarterly plan","body":"Thanks"}'

# Convert email-derived execution items into source-linked ticket tasks.
TASK_BODY="$(cat <<'JSON'
{
  "source_email_id": "<root@example.com>",
  "thread_id": "thread-root@example.com",
  "items": ["담당자 확인"]
}
JSON
)"
curl -s -X POST http://localhost:8000/api/tasks/from-email \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  -H 'content-type: application/json' \
  -d "$TASK_BODY"

# Request a customer-owned calendar writeback intent. This selects a trusted
# server-side source and returns no provider secret. Provider execution is
# explicit opt-in and requires If-Match/ETag evidence.
curl -s http://localhost:8000/api/calendar/writeback-sources \
  -H "Authorization: Bearer $NARUON_DEV_BEARER"
curl -s -X POST http://localhost:8000/api/calendar/writeback-intent \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  -H 'content-type: application/json' \
  -d '{"action":"update","summary":"담당자 확인 회의","target_source_id":"caldav-primary","execute_provider":true}'

# Review source-backed Security governance without exposing provider secrets.
curl -s http://localhost:8000/api/security/access-surface \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  | jq '{scope_kind, sources, policy_decisions}'

# Review source-backed Data repository, ingestion, embedding, and quality state.
curl -s http://localhost:8000/api/data/quality-surface \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  | jq '{workspace_id, audit_event, repositories, quality_checks}'
curl -s -X POST http://localhost:8000/api/data/documents \
  -H "Authorization: Bearer $NARUON_DEV_BEARER" \
  -H 'content-type: application/json' \
  -d '{"document_name":"decision-note.md","document_type":"text/markdown","document_content":"# Decision note"}'
curl -s -X POST http://localhost:8000/api/data/documents/doc_example/reparse \
  -H "Authorization: Bearer $NARUON_DEV_BEARER"
```

## Error-message contract

Errors should tell a contributor what failed and avoid leaking internals:

- SMTP not configured: `400 {"detail":"SMTP is not configured"}`. Create a
  tenant config with SMTP host, port, and username before testing real send.
- Local simulated send: `{"status":"simulated","simulated":true}`. Treat as
  payload/header verification only, not delivery proof.
- Search without OpenAI key: `400 {"detail":"OpenAI API key not configured"}`.
  Add a tenant OpenAI key or skip search smoke locally.
- Search backend failure: `500 {"detail":"Search failed"}`. Check backend logs;
  raw exceptions are intentionally not returned to clients.
- Missing thread: `404 {"detail":"Thread not found"}`. Re-import fixtures or
  verify the URL uses the normalized thread id.
- Task creation from a missing or unauthorized source email:
  `404 {"detail":"Source email not found"}`.
- Task creation without usable execution items:
  `422 {"detail":"At least one execution item is required"}`.
- Calendar writeback with no trusted customer-owned CalDAV/CardDAV/WebDAV source:
  `422 {"detail":"No customer-owned writeback source is available"}`. The
  frontend must show this as a writeback-intent failure, not as a completed
  provider calendar write.

## Current scope contract

Runtime auth no longer trusts public `X-User-*`, `X-Organization-*`,
`X-Group-*`, or `X-Dev-Auth-Token` headers. Email rows now carry a nullable
`user_id` owner key, and email/search/network graph endpoints scope reads to the
authenticated user. Local bootstrap and fixture imports default that owner to
`default`; production
multi-user use still needs a verified OIDC provider plus an audited
mailbox-owner migration/backfill before real tenant data is mixed.

The current frontend shell now exposes the north-star workspace map in the
primary and mobile menus: Today dashboard, Mail, Calendar, Tasks, Projects,
Context Search, AI Hub, Data, Security, and Settings. The `/mail`, `/search`,
`/tasks`, `/calendar`, `/projects`, `/ai-hub`, `/data`, `/security`, and
`/settings` destinations must render real work-detail surfaces rather than
static placeholder copy: calendar month/week/detail/coordination and CalDAV
writeback queues, ticket task boards and source-linked details, integrated
search result/detail graph timelines, source-backed project folders and
decision-evidence logs, document
repository/ingestion/embedding/quality queues, security dashboards and policy
screens, and operational settings. Provider write execution and enterprise
identity remain future connector/auth slices until source-backed integrations
exist. Browser writes to signed backend routes use the HttpOnly
`naruon_session` cookie; the same-origin Next.js `/api/*` proxy converts that
server-readable cookie into the backend `Authorization: Bearer` session and
strips public identity headers such as `X-User-Id` and `X-Organization-Id`,
including group and dev-token variants, rather than forwarding development
identity fallbacks.
Settings connected-account workflow reads and saves `/api/accounts/config`
through the same signed-session path and scopes provider settings by the signed
`user_id + organization_id` owner. It displays SMTP, IMAP, POP3, OAuth,
CalDAV/CardDAV, and WebDAV readiness from masked account fields and source
registry APIs, preserves stored credential secrets when the user leaves
replacement fields blank, and keeps Naruon framed as a web client/relay proxy
rather than an email host. Settings also exposes organization-admin
self-hosted connector token rotation through `/api/runner-config/rotate`; the
one-time token is shown only after rotation and is not included in the connector
manifest.
Mail worker logs and raised errors use generic account-configuration wording for
missing POP3 credentials so operational logs do not reveal credential-type
details.

Email-derived work is tracked through `/api/tasks/from-email`. Created ticket
tasks retain an internal source-email foreign key, expose source message/thread
provenance, sanitize NUL bytes from LLM/email-derived titles, and return opaque
public task ids instead of exposing database integer surrogates. The new
`ticket_tasks` table keeps database names two-word `snake_case` such as
`task_id`, `task_title`, `status_code`, and `priority_code`.

Calendar actions in `EmailDetail` now request `/api/calendar/writeback-intent`
for each extracted execution item and display the selected trusted source
provenance. Calendar source selection now reads opaque
`calendar_writeback_sources.source_uid` rows instead of exposing sequential
CalDAV account ids, and the Calendar workspace loads those rows through signed
`/api/calendar/writeback-sources` before posting an opaque `target_source_id`.
The workspace now presents those sources as explicit selectable writeback
targets and shows the selected source ETag/capability state before intent
creation. Provider execution is opt-in through `execute_provider=true`; the API
dispatches a signed `write_caldav` command to an active outbound runner only
after server-authoritative source selection and If-Match evidence are available.
The browser no longer claims `/api/calendar/sync` success from the mail-detail
action path; direct browser provider writes stay deferred. Connector-side DAV
adapters can execute ETag/If-Match-guarded PUTs, and the WebDAV
materialization endpoint can dispatch signed commands to an active outbound
runner. Durable queueing, retry, and broader UI dispatch controls remain
connector workflow follow-ups.
WebDAV writeback and self-sent knowledge materialization use
`webdav_accounts.source_uid` as the browser-visible source id, scope lookup by
the signed session organization, honor persisted `writeback_enabled`
eligibility, surface `webdav_accounts.etag_value` as source-safe If-Match
evidence, reject legacy `target_account_id` payloads, and keep sequential
`account_id` values internal-only. The Data workspace exposes the WebDAV source
as an explicit selected target and treats `409` If-Match/ETag responses as
conflicts instead of generic failures, so UI copy never implies a provider write
overwrote customer-owned files. Provider URLs, usernames, and credentials stay
server-side. Project folder listings are scoped by the signed session
organization and expose opaque `project_folders.folder_uid` values instead of
sequential `folder_id` values, and the `/dav` PUT skeleton fails closed until
provider-backed source, capability, and ETag/If-Match checks exist.
Data repository, ingestion, embedding, and quality status is loaded from signed
`/api/data/quality-surface`. Workspace document uploads use signed
`POST /api/data/documents`, while reparse, embedding-regeneration, and HWP
conversion controls call the scoped document action endpoints and keep
`provider_write_executed=false`. Workspace document WebDAV materialization uses
signed `POST /api/data/documents/{document_id}/webdav-materialization-intent`
with an opaque selected WebDAV `source_uid`; the backend derives the target path
and content server-side and dispatches connector execution only on
`execute_provider=true`. The UI must not reintroduce static ingestion logs, fake
vector counts, unsupported embedding model names, fake quality totals, or inert
permanent ready-soon controls; use source-backed rows or explicit pending
states.

## Operations and release docs

- `docs/operations/release-deployment-architecture.md`: release, CI, GHCR, and
  live E2E evidence path.
- `docs/operations/open-source-apm.md`: OpenTelemetry, Prometheus, Grafana, Loki,
  Tempo/Jaeger adoption plan. Settings calls signed
  `/api/observability/operational-signals` to show server-observed connector
  registration, active runner connection state, recent durable heartbeat
  history, Prometheus, and OpenTelemetry configuration while provider execution
  remains future connector work.
- `docs/operations/email-relay-proxy-boundary.md`: Naruon is a web client
  relay/proxy, not an email server.
- `docs/operations/source-of-truth-and-writeback-sovereignty.md`: customer-owned
  source-of-truth, connector, writeback, and audit rules.
- `docs/operations/postgresql-physical-replication.md`: physical replication,
  WAL, restore, and read-routing plan.
- `docs/operations/auth-key-management.md`: auth boundary, Fernet key management,
  and Keycloak/Casdoor evaluation.
- `docs/operations/traefik-evaluation.md`: Traefik versus current NGINX ingress
  evaluation.
- `docs/development/merge-gate-policy.md`: metadata-only PR governance,
  current-head CodeRabbit evidence, and required-check behavior.

## Verification used for this hardening pass

```bash
./scripts/verify_threading.sh

# Equivalent manual checks:
cd backend && python3 -m pytest -q
cd frontend && npm test && npm run lint && npm run build
```

Additional focused checks for the current workspace/task/governance slice:

```bash
cd backend && \
  PYTHONDONTWRITEBYTECODE=1 DISABLE_BACKGROUND_WORKERS=1 \
  pytest tests/test_tasks_api.py -q
cd frontend && npm test -- \
  src/lib/api-client.test.ts \
  src/lib/workspace-preferences.test.ts \
  src/components/DashboardLayout.test.tsx \
  src/app/calendar/page.test.tsx \
  src/app/tasks/page.test.tsx \
  src/app/search/page.test.tsx \
  src/app/projects/page.test.tsx \
  src/app/data/page.test.tsx \
  src/app/security/page.test.tsx \
  src/app/page.test.tsx \
  src/components/EmailDetail.test.tsx
cd frontend && LIVE_BASE_URL=http://127.0.0.1:18081 npm run test:e2e -- tests/e2e/dashboard-branding.spec.ts
bash scripts/ci/test_pr_governance_gate.sh
```

Known local warnings: backend tests emit dependency/toolchain deprecation warnings
from Starlette multipart and compiled SWIG metadata. They are not caused by
threading code.

## Phase 10 development rules

- **Stepwise execution**: Each phase requires an atomic PR, GitHub PR Tracking, Push, and Robot Review. A phase only ends when merged. Do not proceed without merge.
- **TDD + DDD**: Practice TDD, micro TDD, nano TDD, Domain Driven Development, and Context Driven Development.
- **API Wiring**: Always work with API wiring completed.
- **Collaboration**: Respect other agents' concurrent work; do not overwrite or dismiss unfamiliar changes.
- **Subagent Delegation**: Actively delegate tasks to Subagents.
- **UI/Browser Testing**: Use a real browser for testing (do not rely on assumptions).
- **Strict Errors**: Treat `Timeout`, `Fatal`, `Warn`, and `Denied` outputs as hard failures.
- **Goal**: Actively manage tasks to ensure open PR counts converge to 0.
