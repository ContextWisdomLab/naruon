# Architecture

## System shape

```mermaid
flowchart LR
  UI[Next.js frontend] --> API[FastAPI backend / Naruon control plane]
  API --> DB[(Postgres + pgvector)]
  API --> CO[contextual-orchestrator released gateway]
  API --> CONN[Outbound-only self-hosted connector]
  CONN --> MAIL[Customer IMAP/POP3/SMTP]
  CONN --> DAV[Customer CalDAV/CardDAV/WebDAV]
  API --> SMTP[Direct SMTP only when operator-allowed]
```

The backend owns persistence, threading, search, AI summaries, and outbound
send orchestration. The frontend consumes the backend contracts and renders
inbox, detail, thread history, reply composer, and network graph surfaces.
Runtime database connectivity is secret-injected: `backend/core/config.py` has
no fallback `DATABASE_URL`, so missing database configuration fails at startup
rather than silently using shared development credentials.

## Topic-intelligence boundary

Naruon has no live Structural Topic Modeling endpoint, fitted topic artifact,
or topic-result persistence. The retained `keyword_extractor` is deterministic
lexical metadata and must not feed topic, agenda, search, or norm-group
inference. A future adapter may consume a separately accepted, versioned TEPP
artifact/API only when frozen preprocessing and vocabulary, covariate design,
mixed-membership posterior uncertainty, diagnostics, provenance, and explicit
abstention are all available. Missing or incompatible scientific authority
fails closed. Naruon owns authentication, authorization, request validation,
the adapter envelope, and disclosure policy; TEPP would own the scientific
payload. See the canonical documentation graph in
[`docs/topic-intelligence/README.md`](docs/topic-intelligence/README.md) and
[`ADR-0001`](docs/adr/0001-topic-measurement-authority.md).

## Workspace navigation boundary

The Next.js shell opens the Today execution dashboard for first-run sessions and
lets users explicitly choose Dashboard, Email, or Calendar as their startup
surface. The primary and mobile menus expose Mail, Calendar, Tasks, Projects,
Context Search, AI Hub, Data, Security, and Settings as navigable workspace
destinations, with the tablet/mobile drawer carrying the same global navigation
matrix as the desktop shell. The `/mail`, `/search`, `/calendar`, `/tasks`,
`/projects`, `/ai-hub`, `/data`, `/security`, and `/settings` pages are honest
scope and control-plane surfaces with actionable detail states: CalDAV
month/week/detail/coordination and writeback queues, source-linked task boards,
integrated search results with graph/timeline context, project decision logs,
document repository/ingestion/embedding/quality queues, security policy/audit
surfaces, and operational settings. They expose source-of-truth, duplicate
import/thread provenance, and RBAC/ABAC boundaries without pretending provider
writeback or enterprise identity integrations are fully implemented.

## Threading boundary

`backend/services/threading_service.py` is the canonical domain service for
assigning persisted `thread_id` values. Parsers extract raw email headers, and
import/API paths persist the service-assigned value. The detailed behavior is
documented in `docs/threading-contract.md`.

## Data and tenancy boundary

The `emails` table has non-null `user_id` and `organization_id` owner keys, and
the current email list, detail, thread, search, and network graph endpoints scope
their queries to the authenticated user plus organization. Fresh local databases
get these columns from SQLAlchemy metadata; existing local databases get them
through `scripts/bootstrap_db.py`, which fails closed when legacy rows lack owner
scope unless explicit non-default `NARUON_IMPORT_USER_ID` and
`NARUON_IMPORT_ORGANIZATION_ID` values are provided for the backfill. Production
multi-user safety still requires an audited migration and backfill that maps
historical rows to verified mailbox owners and organizations before real tenant
data is mixed in one database.

`message_id` is unique only within the `(user_id, organization_id)` owner scope,
not globally. Fixture import upserts and reply-thread lookup use the same owner
scope so a reused RFC Message-ID from another organization cannot overwrite an
email row or attach a reply to another tenant's thread.

`llm_providers` is also owner-scoped. Provider rows carry non-null `user_id` and
`organization_id`, provider names are unique only within an organization, and the
registry/list/update/delete plus prompt-preview provider selection paths filter by
the authenticated organization. Existing local databases get the same fail-closed
owner backfill through `scripts/bootstrap_db.py`; legacy provider rows require
explicit non-default `NARUON_IMPORT_USER_ID` and `NARUON_IMPORT_ORGANIZATION_ID`
before bootstrap will set the new columns non-null.

`ticket_tasks` stores email-derived execution items as ticket-like work records.
The table and its new columns use at least two-word `snake_case` database names
such as `task_id`, `task_title`, `status_code`, `priority_code`, `email_id`, and
`thread_id`. The integer `task_id` stays an internal database surrogate; API
responses use the opaque `task_uid` as their public id and expose source message
provenance instead of private foreign keys. Task creation from email always
checks the source email owner scope, copies the canonical thread provenance, and
strips NUL bytes from titles before persistence so malformed LLM/email-derived
strings cannot break PostgreSQL text writes. Because task titles are plain text,
the backend rejects encoded, malformed, or direct HTML-like execution item markup
before storage instead of returning stored tags to a future rendering surface.
Parsed email body/subject, address, and attachment display text strips active
HTML/script markup at the parser boundary while preserving message/thread
identifiers and angle-address headers separately.

Customer-owned mail, CalDAV/CardDAV, and WebDAV systems remain the durable
source-of-truth. Naruon can cache/index metadata and generate writeback intents,
but provider writes must use server-authoritative source records, ownership
checks, and conflict-aware provider revisions such as ETag/If-Match. The detailed
contract is documented in
`docs/operations/source-of-truth-and-writeback-sovereignty.md`.
Frontend calendar actions follow the same boundary: `EmailDetail` requests
`/api/calendar/writeback-intent` per extracted execution item and reports source
provenance, while legacy `/api/calendar/sync` remains fail-closed unless a
trusted backend credential dependency supplies an authorized provider token.
Calendar provider execution is explicit opt-in: `execute_provider=true` dispatches
a signed `write_caldav` command to an active outbound runner only after
server-authoritative source selection and If-Match evidence are available.
The Data workspace follows the same control-plane boundary for uploaded
workspace documents: `/api/data/documents` stores scoped document metadata and
content in the signed `workspace_id`, while reparse, embedding regeneration, and
HWP conversion endpoints update document status or intent metadata only and
return `provider_write_executed=false`. WebDAV document materialization is a
separate explicit execution path: the browser selects an opaque WebDAV
`source_uid`, while `/api/data/documents/{document_id}/webdav-materialization-intent`
re-reads the scoped document server-side, derives the provider target path and
Markdown content, and dispatches `write_webdav` only when
`execute_provider=true`.
PixelRAG visual retrieval is being evaluated as an optional sidecar for
visually rich documents, not as a core backend dependency or hosted third-party
tenant-data path; see `docs/architecture/pixelrag-integration-evaluation.md`.

Authorization is RBAC plus ABAC with deny precedence. Data-region, consent,
workspace, group, source capability, and customer-policy denies still override
broad roles. The narrow exception is an explicitly RBAC-permitted
`platform_admin`: that role may cross organization and resource ownership
boundaries in the pure access-policy evaluator for platform operations, but it
does not bypass data-region or consent denies; see
`docs/operations/auth-key-management.md`.

## Local deployment boundary

`docker-compose.yml` provides the blessed local stack: Postgres with pgvector,
FastAPI backend, and Next.js frontend. Schema changes now have an Alembic
history under `backend/alembic`, with `backend/scripts/migrate_db.py` applying
`upgrade head` for managed environments. The legacy backend bootstrap script
remains a local/dev compatibility path that creates the `vector` extension,
metadata-defined tables for fresh local databases, and idempotent backfills for
existing local databases.

## Send boundary

Outbound replies preserve `In-Reply-To` and `References` headers in the built
message payload. Local/dev behavior is explicit: missing SMTP config returns a
400, and simulated send results are marked with `simulated: true` rather than
described as real delivery.

Tenant-provided SMTP destinations are not a general outbound socket primitive.
`backend/api/tenant_config.py`, `backend/api/emails.py`, and the final
`backend/services/email_client.py` network sink enforce the operator-controlled
`ALLOWED_SMTP_HOSTS` and `ALLOWED_SMTP_PORTS` allowlists. The service also
rejects loopback, link-local, private, reserved, and otherwise non-global DNS
answers before opening a pinned socket to the selected global address, so stale
database rows or direct service calls fail closed instead of reaching internal
network targets or re-resolving DNS after validation.

Private-network IMAP/SMTP/CalDAV/CardDAV/WebDAV access belongs behind the
outbound-only self-hosted connector boundary. GitHub self-hosted runners can
smoke-test internal mail connectivity, but production relay/proxy access should
use a connector artifact and never imply inbound MX hosting. The Python
connector now includes explicit IMAP fetch/import, SMTP send, and
ETag/If-Match-guarded CalDAV/WebDAV PUT local adapter handlers for
`SelfHostedConnector`; packaging, registration-token lifecycle, backend
dispatch, and non-DAV protocol adapters remain separate connector delivery work.

LLM provider `base_url` is also a server-side egress boundary, not an arbitrary
URL field. Provider registry create/update paths are organization-admin scoped,
and LLM call sinks validate custom OpenAI-compatible base URLs with HTTPS-only
syntax, no userinfo/query or fragment, exact host membership in
`ALLOWED_LLM_BASE_URL_HOSTS`, and DNS answers that are all globally routable.
Missing allowlist configuration fails closed; the default provider path should
leave `base_url` unset.

## Batch embedding routing boundary

Bulk, latency-tolerant embedding work (email import, backfills) does not call a
batch engine directly. It routes through **contextual-orchestrator**, the
routing / cost hub, which owns provider selection, load balancing, and cost
accounting and forwards the work to `pg-llm-batch`.
[`backend/services/batch_embedding_service.py`](backend/services/batch_embedding_service.py)
resolves the orchestrator base URL, bearer token, endpoint alias, and model from
the per-tenant Fernet-encrypted `tenant_configs` row (never `os.getenv`; the
token column is `EncryptedString`), then submits the batch over the same
SSRF-guarded, allowlisted, pinned-address HTTP client
(`build_llm_provider_http_client`) that fronts every other outbound LLM call.
naruon records a durable `llm_batch_jobs` / `llm_batch_items` audit trail
(routing mode, the orchestrator's batch id, reported cost) for observability.
The path degrades gracefully: if batching is disabled, the orchestrator base URL
is rejected by the egress guard, or the orchestrator is unreachable, the caller
transparently falls back to the per-item embedding path. A local `pg-llm-batch`
package/checkout remains only as an optional offline-dev fallback, gated behind
orchestrator-unavailable and an explicit local DSN; naruon does not vendor a
gitlink for that fallback in this PR.

## Semantic project-graph extractor seam

Semantic extraction — turning grounded content segments into cited
`project_graph_objects`/`_edges` — goes through a stable, named + versioned
extractor seam rather than a hardcoded branch in the import pipeline.
[`backend/services/project_graph/extractor_registry.py`](backend/services/project_graph/extractor_registry.py)
defines the `KgExtractor` contract (name + version + `extract`), a
`KgExtractorRegistry` keyed by the `PROJECT_GRAPH_EXTRACTOR` selector, and
`run_extraction`, which resolves an ordered fallback chain. The chain's terminal
element is **always** the deterministic keyword extractor, so "rule-based
extraction is fallback/reference only" is guaranteed structurally — an LLM
extractor that lacks credentials, targets an unconfigured orchestrator endpoint,
or fails at request time raises `ExtractorUnavailableError` (or any exception)
and the runner degrades down the chain instead of losing the projection. New
extractors (including future plugins on the platform plan's `kg.extractor`
extension point) register a selector without editing ingest.

Routing LLM extraction through **contextual-orchestrator** is modelled as a
transport concern: the orchestrator is an OpenAI-compatible gateway, so the
`orchestrator` selector reuses the identical grounded LLM extractor
(`extract_project_semantics_llm`, which enforces segment citations) but points
its SSRF-allowlisted client (`build_llm_provider_http_client`) at
`PROJECT_GRAPH_ORCHESTRATOR_BASE_URL` instead of the raw provider. The provider
API key stays the tenant's Fernet-encrypted credential, and the orchestrator base
URL must be HTTPS and exact-host allowlisted by `ALLOWED_LLM_BASE_URL_HOSTS`;
an unset or rejected endpoint fails closed to the deterministic extractor. Design
and grounding: [`docs/architecture/kg-extractor-seam.md`](docs/architecture/kg-extractor-seam.md).

Provider discovery, capability routing, and fallback belong to
`contextual-orchestrator`. Production adoption requires an immutable released
owner API/client/schema; an unavailable or incompatible release fails closed.

## CI security boundary

OpenCode Review, Strix Security Scan, and PR Review Merge Scheduler are supplied
by the ContextualWisdomLab central required workflows in
`ContextualWisdomLab/.github`; this repository does not carry repo-local copies
of those workflows or their dedicated support scripts. The central Strix
workflow treats pull request code as untrusted whenever repository secrets are
available: privileged PR scans run from trusted workflow code, fetch the pull
request head as Git objects, and copy PR-head blobs into temporary scan scopes
before invoking Strix. Changed PR-head files must be scanned as PR-head data,
not replaced with trusted-base content.

The central gate fails closed when PR-head evidence cannot be validated, keeps
Medium-or-higher Strix findings required, and owns model routing, fallback,
reasoning-effort, failed-check explanation, branch update, auto-merge, and
OpenCode review behavior. Naruon documents the required behavior but does not
duplicate the central workflow implementation. Merge-gate governance for Strix,
CodeRabbit, OpenCode, and required review evidence is documented in
`docs/development/merge-gate-policy.md`.

## Release and operations boundary

Release/deployment architecture is documented in
`docs/operations/release-deployment-architecture.md`. Naruon is not an email
server; the email boundary is a web client relay/proxy for member-configured
SMTP/IMAP providers as documented in
`docs/operations/email-relay-proxy-boundary.md`. PostgreSQL remains
single-primary in the default local stack, while
`docker-compose.postgres-ha.yml` and `scripts/postgres_ha_drill.sh` provide the
physical-replication evaluation path. The 2026-06-15 drill verified
`pg_basebackup`, replica recovery, marker replay, `vector` extension replay, and
manual promotion; production automated HA still requires operator WAL
archive/restore drills and failover-coordinator policy per
`docs/operations/postgresql-physical-replication.md`.

Authentication does not treat public `X-User-*`, `X-Organization-*`,
`X-Group-*`, or `X-Dev-Auth-Token` headers as identity material. The runtime
FastAPI dependency in `backend/api/auth.py` accepts only `Authorization: Bearer`
compact session tokens whose protected header pins `alg=HS256` and whose
`header.payload` signing input is signed by the configured
`AUTH_SESSION_HMAC_SECRET`; missing, weak, malformed, legacy two-segment,
wrong-algorithm, tampered, expired, or public fixture-secret tokens fail closed
with 401. The signed session envelope must carry explicit identity, role,
organization/group, and workspace claims, so user ids such as `admin` do not
imply elevated privileges.
Endpoint tests use FastAPI dependency overrides for fixture identity only through
explicit opt-in pytest fixtures, while a full Keycloak/Casdoor/OIDC provider and
audited mailbox-owner migration remain required before production multi-user
access is claimed; see `docs/operations/auth-key-management.md`. The current
Kubernetes ingress assumes NGINX, while Traefik is only an evaluated option in
`docs/operations/traefik-evaluation.md`.

Private `/api/*` routers are also registered in `backend/main.py` with the
default `get_auth_context` dependency so newly added private endpoints inherit a
signed-session requirement before endpoint-specific user, organization, role, or
resource checks run. `/api/runtime-config`, `/`, and `/metrics` remain public
because they expose only non-secret runtime/health metadata. LLM provider
registry reads and writes are organization/platform admin operations; members use
tenant-scoped configuration or approved AI workflows rather than provider
inventory APIs. Provider rows remain scoped to the authenticated organization for
ordinary provider registry operations and prompt-preview model selection. Custom
provider endpoints additionally require an operator-owned egress allowlist so an
organization admin cannot point LLM traffic at localhost, private networks, or
cloud metadata services.

The browser API client reads `naruon_session_token` from local storage and sends
it as the bearer session on signed routes. It does not synthesize or forward
public identity headers such as `X-User-Id`, `X-Organization-Id`, `X-Group-Id`,
`X-Group-Ids`, `X-User-Role`, or `X-Dev-Auth-Token`; any local development
identity-header flow is limited to explicit unsigned/test harness paths and is
not accepted by authenticated runtime dependencies. UI flows that create
source-linked tasks or other server-side writes must keep that signed-session
path covered in fast tests and E2E mocks so authenticated backend behavior is
not masked by stale fixtures.
Caller-supplied `Authorization` headers are dropped before the stored signed
session is applied, so browser code cannot shadow the bearer token with a
case-variant header.

Secret-field encryption has no code fallback key. `backend/db/models.py` requires
an explicit, valid Fernet `ENCRYPTION_KEY` before encrypting or decrypting OAuth,
OpenAI, SMTP, IMAP, Google, and runner registration token fields, even in debug
mode. Invalid passphrase-style keys fail closed instead of being transformed into
derived keys. Decryption failures return `None` rather than ciphertext, so routes
that touch encrypted values must surface operator-facing missing-key or
unavailable-secret behavior without exposing encrypted blobs.

Calendar writeback intent selection is server-authoritative. The
`/api/calendar/writeback-intent` request may specify an action and optional
target source id, but it must not provide source ownership or capability records;
`backend/api/calendar.py` obtains writeback sources through a FastAPI dependency
that reads DB-backed `calendar_writeback_sources` records scoped to the
authenticated user. Provider execution remains opt-in and fail-closed without an
active outbound runner or If-Match/ETag evidence.
