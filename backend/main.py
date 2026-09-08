import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.auth import get_auth_context, preload_oidc_jwks
from api.search import router as search_router
from api.llm import router as llm_router
from api.calendar import router as calendar_router
from api.calendar_conflicts import router as calendar_conflicts_router
from api.network import router as network_router
from api.emails import router as emails_router
from api.runner_config import router as runner_config_router
from api.tenant_config import router as tenant_config_router
from api.runtime_config import router as runtime_config_router
from api.llm_providers import router as llm_providers_router
from api.prompts import router as prompts_router
from api.tasks import router as tasks_router
from api.tools import router as tools_router
from api.ontology import router as ontology_router
from api.observability import router as observability_router
from api.runner_ws import manager as runner_manager
from api.runner_ws import router as runner_ws_router
from api.dav import router as dav_router
from api.accounts import router as accounts_router
from api.webdav import router as webdav_router
from api.security import router as security_router
from api.data import router as data_router
from api.ai_hub import router as ai_hub_router
from api.projects import router as projects_router
from api.session import router as auth_session_router
from core.config import canonical_origin, settings
from core.telemetry import setup_telemetry
from core.version import get_release_version
from services.imap_worker import ImapSyncWorker
from services.newsdom_worker import NewsdomRecognitionWorker
from services.pop3_worker import Pop3SyncWorker
from services.provider_writeback_retry_service import ProviderWritebackRetryWorker
from services.reply_sla_scheduler import ReplySlaScheduler
from prometheus_fastapi_instrumentator import Instrumentator

imap_worker = ImapSyncWorker()
pop3_worker = Pop3SyncWorker()
reply_sla_scheduler = ReplySlaScheduler()
newsdom_recognition_worker = NewsdomRecognitionWorker()
provider_writeback_retry_worker = ProviderWritebackRetryWorker(
    runner_manager.dispatch_command,
)

DISABLE_WORKERS = os.environ.get("DISABLE_BACKGROUND_WORKERS") == "1"
PRIVATE_API_DEPENDENCIES = [Depends(get_auth_context)]
STATE_CHANGING_API_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE", "MKCOL"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    preload_oidc_jwks()
    if not DISABLE_WORKERS:
        await imap_worker.start()
        await pop3_worker.start()
        await reply_sla_scheduler.start()
        await newsdom_recognition_worker.start()
        await provider_writeback_retry_worker.start()
    yield
    if not DISABLE_WORKERS:
        await provider_writeback_retry_worker.stop()
        await newsdom_recognition_worker.stop()
        await reply_sla_scheduler.stop()
        await pop3_worker.stop()
        await imap_worker.stop()


app = FastAPI(
    title="Naruon Backend",
    version=get_release_version(),
    lifespan=lifespan,
)

setup_telemetry(app)

# Prometheus metrics are operational telemetry. Keep them opt-in so public
# deployments do not expose route labels and process details by default.
if settings.ENABLE_PROMETHEUS_METRICS:
    Instrumentator().instrument(app).expose(
        app, include_in_schema=False, should_gzip=True
    )


def _normalized_origin(header_value: str | None) -> str | None:
    if header_value is None:
        return None
    parsed = urlsplit(header_value.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.netloc or not parsed.hostname:
        return None
    if (
        parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return canonical_origin(parsed.scheme, parsed.hostname, port)


def _origin_from_referer(header_value: str | None) -> str | None:
    if header_value is None:
        return None
    parsed = urlsplit(header_value.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.netloc or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return canonical_origin(parsed.scheme, parsed.hostname, port)


def _is_trusted_browser_origin(origin: str | None) -> bool:
    if origin is None:
        return True
    return origin in set(settings.ALLOWED_CORS_ORIGINS_LIST)


def _requires_browser_origin_check(request: Request) -> bool:
    return (
        request.method.upper() in STATE_CHANGING_API_METHODS
        and request.url.path.startswith("/api/")
    )


@app.middleware("http")
async def reject_cross_site_state_changing_api_requests(request: Request, call_next):
    if _requires_browser_origin_check(request):
        fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
        if fetch_site == "cross-site":
            return JSONResponse(
                status_code=403,
                content={"error_code": "csrf_fetch_site_rejected"},
            )

        raw_origin = request.headers.get("origin")
        origin = _normalized_origin(raw_origin)
        if raw_origin is not None and origin is None:
            return JSONResponse(
                status_code=403,
                content={"error_code": "csrf_origin_rejected"},
            )
        if not _is_trusted_browser_origin(origin):
            return JSONResponse(
                status_code=403,
                content={"error_code": "csrf_origin_rejected"},
            )

        if origin is None:
            raw_referer = request.headers.get("referer")
            referer_origin = _origin_from_referer(raw_referer)
            if raw_referer is not None and referer_origin is None:
                return JSONResponse(
                    status_code=403,
                    content={"error_code": "csrf_referer_rejected"},
                )
            if not _is_trusted_browser_origin(referer_origin):
                return JSONResponse(
                    status_code=403,
                    content={"error_code": "csrf_referer_rejected"},
                )

    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    if settings.SECURITY_CONTENT_SECURITY_POLICY:
        response.headers["Content-Security-Policy"] = (
            settings.SECURITY_CONTENT_SECURITY_POLICY
        )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "PROPFIND",
        "REPORT",
        "MKCOL",
    ],
    allow_headers=["Accept", "Content-Type", "Authorization"],
)

app.include_router(search_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(llm_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(calendar_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(calendar_conflicts_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(network_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(emails_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(runner_config_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(tenant_config_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(runtime_config_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(llm_providers_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(prompts_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(tasks_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(tools_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(ontology_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(observability_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(runner_ws_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(dav_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(accounts_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(webdav_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(security_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(data_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(ai_hub_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(projects_router, dependencies=PRIVATE_API_DEPENDENCIES)
app.include_router(auth_session_router, dependencies=PRIVATE_API_DEPENDENCIES)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "message": "AI Email Client API"}
