"""Batch-tolerant embedding routing via contextual-orchestrator.

This adapter lets naruon route *bulk, latency-tolerant* embedding work (email
import, summarization backfills) as a single batch instead of issuing one
embedding call per item. The **primary** path submits the batch to the
``contextual-orchestrator`` batch API — the routing / cost hub — which selects a
provider, load-balances, forwards the work to ``pg-llm-batch`` and records cost.
naruon keeps a durable job/item audit trail (``llm_batch_jobs`` /
``llm_batch_items``) so batch work is observable, but it no longer owns the
``pg-llm-batch`` engine on the primary path.

Design constraints:

* **Orchestrator is primary.** naruon submits to the orchestrator batch endpoint
  and lets it own provider routing, load balancing and cost accounting. A local
  ``pg_llm_batch`` package remains only as an *offline-dev fallback*, gated behind
  "orchestrator unavailable" (see :func:`_run_local_engine_batch`).
* **Graceful degradation.** If batching is disabled/unconfigured for the tenant,
  the orchestrator is unreachable/misconfigured, and the local fallback is also
  unavailable, every entry point returns ``None`` so the caller transparently
  uses its existing per-item embedding path. naruon keeps working regardless.
* **SSRF-guarded, allowlisted egress.** The orchestrator base URL is validated
  and the HTTP client is built with :func:`build_llm_provider_http_client`,
  reusing the pinned-address transport (DNS-rebinding safe, redirects disabled,
  ``trust_env`` off) that fronts every other outbound LLM call.
* **No ``os.getenv`` for secrets/config.** The orchestrator base URL, bearer
  token, endpoint alias, model and the optional local fallback DSN are resolved
  from the per-tenant Fernet-encrypted ``tenant_configs`` row (the token and DSN
  columns are ``EncryptedString``). The environment is never read here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LlmBatchItem, LlmBatchJob
from services.embedding import (
    STORAGE_EMBEDDING_DIMENSION,
    fit_embedding_vector,
    generate_embeddings,
)
from services.exceptions import EmbeddingGenerationError
from services.llm_provider_urls import build_llm_provider_http_client
from services.tenant_config_scope import get_scoped_tenant_config

if TYPE_CHECKING:  # pragma: no cover - typing only
    from services.email_import_service import EmailImportEmbeddingProvider

logger = logging.getLogger(__name__)

# Orchestrator batch API surface (naruon -> contextual-orchestrator).
_BATCH_SUBMIT_PATH = "/v1/batch/embeddings"
_ORCHESTRATOR_TIMEOUT_SECONDS = 30.0
# Poll budget while the orchestrator drains the batch through pg-llm-batch.
_ORCHESTRATOR_POLL_INTERVAL_SECONDS = 1.0
_ORCHESTRATOR_MAX_POLLS = 30
# Keep each JSON request below the orchestrator's body budget with envelope
# headroom. Import chunks are normally <= 1,000 characters, but the byte check
# also protects direct callers that provide longer or multibyte inputs.
_ORCHESTRATOR_MAX_INPUTS_PER_REQUEST = 32
_ORCHESTRATOR_MAX_INPUT_BYTES = 48 * 1024
_SUCCESS_STATUSES = frozenset({"completed", "succeeded"})

# Cache the (im)port result so repeated imports don't re-probe sys.path.
_ENGINE_CACHE: list[ModuleType | None] = []


def load_batch_engine() -> ModuleType | None:
    """Return the ``pg_llm_batch`` module, or ``None`` when unavailable.

    The package is an *optional* offline-dev dependency (the orchestrator is
    the primary path): naruon must run with it uninitialized. When the package
    cannot be imported we log once at debug level and signal fallback by
    returning ``None``.
    """
    if _ENGINE_CACHE:
        return _ENGINE_CACHE[0]
    try:
        import pg_llm_batch  # type: ignore
    except ImportError:
        logger.debug(
            "pg_llm_batch package not importable; local batch fallback disabled"
        )
        _ENGINE_CACHE.append(None)
        return None
    _ENGINE_CACHE.append(pg_llm_batch)
    return pg_llm_batch


@dataclass(frozen=True)
class BatchEmbeddingSettings:
    """Per-tenant batch configuration resolved from the Fernet DB (never env)."""

    orchestrator_base_url: str | None
    orchestrator_token: str | None
    endpoint_alias: str | None
    model: str | None
    local_dsn: str | None
    # Cost-attribution dimensions resolved from the tenant config (never env),
    # forwarded to the orchestrator ledger so batch cost attribution is complete.
    attribution_service: str | None = None
    attribution_team: str | None = None
    attribution_group: str | None = None
    attribution_company: str | None = None

    @property
    def has_orchestrator(self) -> bool:
        return bool(self.orchestrator_base_url and self.orchestrator_token)

    @property
    def has_local_fallback(self) -> bool:
        return bool(self.local_dsn)


@dataclass(frozen=True)
class BatchEmbeddingPartial:
    """Completed prefix plus inputs that still need the normal fallback path."""

    completed_vectors: list[list[float]]
    pending_texts: list[str]


async def resolve_batch_embedding_settings(
    session: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
) -> BatchEmbeddingSettings | None:
    """Resolve batch settings from the per-tenant Fernet-encrypted config.

    Returns ``None`` (i.e. "route the normal per-item path") unless the tenant
    has enabled batching. The orchestrator token and local DSN are read back
    through ``EncryptedString`` columns, so they are decrypted from the Fernet DB
    rather than read from the process environment.
    """
    tenant_config = await get_scoped_tenant_config(session, user_id, organization_id)
    if tenant_config is None:
        return None
    if not getattr(tenant_config, "batch_embedding_enabled", False):
        return None
    base_url = _clean(getattr(tenant_config, "batch_orchestrator_base_url", None))
    token = _clean(getattr(tenant_config, "batch_orchestrator_token", None))
    settings = BatchEmbeddingSettings(
        orchestrator_base_url=base_url,
        orchestrator_token=token,
        endpoint_alias=_clean(
            getattr(tenant_config, "batch_orchestrator_endpoint", None)
        ),
        model=_clean(getattr(tenant_config, "batch_embedding_model", None)),
        local_dsn=_clean(getattr(tenant_config, "batch_local_dsn", None)),
        attribution_service=_clean(
            getattr(tenant_config, "batch_attribution_service", None)
        ),
        attribution_team=_clean(getattr(tenant_config, "batch_attribution_team", None)),
        attribution_group=_clean(
            getattr(tenant_config, "batch_attribution_group", None)
        ),
        attribution_company=_clean(
            getattr(tenant_config, "batch_attribution_company", None)
        ),
    )
    if not settings.has_orchestrator and not settings.has_local_fallback:
        # Enabled but nothing configured to route to — behave as disabled.
        return None
    return settings


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


async def try_batch_import_embeddings(
    session: AsyncSession,
    texts: list[str],
    *,
    embedding_provider: EmailImportEmbeddingProvider,
    user_id: str,
    organization_id: str | None,
    dimension: int = STORAGE_EMBEDDING_DIMENSION,
) -> list[list[float]] | BatchEmbeddingPartial | None:
    """Route bulk embeddings through the batch path, or ``None`` to fall back.

    On success returns one fitted vector per input text (original order). The
    primary path submits to contextual-orchestrator; only if the orchestrator is
    unconfigured or unavailable does it consider the local ``pg-llm-batch``
    package fallback. A later partition failure returns a completed prefix plus
    only the unfinished inputs so the caller does not resend successful work.
    The run is recorded in ``llm_batch_jobs`` / ``llm_batch_items`` for
    observability.
    """
    if not texts:
        return None

    settings = await resolve_batch_embedding_settings(
        session, user_id=user_id, organization_id=organization_id
    )
    if settings is None:
        return None

    model = settings.model or embedding_provider.embedding_model

    if settings.has_orchestrator:
        result = await _run_orchestrator_batches(
            session,
            texts,
            settings=settings,
            model=model,
            user_id=user_id,
            organization_id=organization_id,
            dimension=dimension,
        )
        if result is not None:
            return result
        # Orchestrator unavailable/misconfigured — consider the local fallback.

    if settings.has_local_fallback:
        return await _run_local_engine_batch(
            session,
            texts,
            embedding_provider=embedding_provider,
            settings=settings,
            model=model,
            user_id=user_id,
            organization_id=organization_id,
            dimension=dimension,
        )

    return None


# --- Primary path: contextual-orchestrator batch API ------------------------


def _serialized_orchestrator_payload_bytes(
    inputs: list[str],
    *,
    model: str,
    endpoint_alias: str | None,
    metadata: dict[str, str],
) -> int:
    """Return the UTF-8 size of the request envelope sent to the orchestrator."""
    payload = {
        "model": model,
        "endpoint": endpoint_alias,
        "inputs": inputs,
        "metadata": metadata,
    }
    return len(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )


def _partition_orchestrator_inputs(
    texts: list[str],
    *,
    model: str = "",
    endpoint_alias: str | None = None,
    metadata: dict[str, str] | None = None,
) -> list[list[str]] | None:
    """Partition inputs by count and serialized JSON request bytes."""
    request_metadata = metadata or {}
    partitions: list[list[str]] = []
    current: list[str] = []
    for text in texts:
        candidate = [*current, text]
        if current and (
            len(candidate) > _ORCHESTRATOR_MAX_INPUTS_PER_REQUEST
            or _serialized_orchestrator_payload_bytes(
                candidate,
                model=model,
                endpoint_alias=endpoint_alias,
                metadata=request_metadata,
            )
            > _ORCHESTRATOR_MAX_INPUT_BYTES
        ):
            partitions.append(current)
            candidate = [text]
        if (
            _serialized_orchestrator_payload_bytes(
                candidate,
                model=model,
                endpoint_alias=endpoint_alias,
                metadata=request_metadata,
            )
            > _ORCHESTRATOR_MAX_INPUT_BYTES
        ):
            return None
        current = candidate
    if current:
        partitions.append(current)
    return partitions


async def _run_orchestrator_batches(
    session: AsyncSession,
    texts: list[str],
    *,
    settings: BatchEmbeddingSettings,
    model: str,
    user_id: str,
    organization_id: str | None,
    dimension: int,
) -> list[list[float]] | BatchEmbeddingPartial | None:
    """Submit bounded requests and concatenate vectors in original order."""
    metadata = _attribution_metadata(
        settings=settings,
        user_id=user_id,
        organization_id=organization_id,
    )
    partitions = _partition_orchestrator_inputs(
        texts,
        model=model,
        endpoint_alias=settings.endpoint_alias,
        metadata=metadata,
    )
    if partitions is None:
        logger.warning(
            "Orchestrator batch input exceeded one-request byte budget; falling back: "
            "text_count=%s",
            len(texts),
        )
        return None

    vectors: list[list[float]] = []
    for partition_index, partition in enumerate(partitions):
        partition_vectors = await _run_orchestrator_batch(
            session,
            partition,
            settings=settings,
            model=model,
            user_id=user_id,
            organization_id=organization_id,
            dimension=dimension,
        )
        if partition_vectors is None:
            if not vectors:
                return None
            pending_texts = [
                text for remaining in partitions[partition_index:] for text in remaining
            ]
            return BatchEmbeddingPartial(
                completed_vectors=vectors,
                pending_texts=pending_texts,
            )
        vectors.extend(partition_vectors)
    return vectors


async def _run_orchestrator_batch(
    session: AsyncSession,
    texts: list[str],
    *,
    settings: BatchEmbeddingSettings,
    model: str,
    user_id: str,
    organization_id: str | None,
    dimension: int,
) -> list[list[float]] | None:
    """Submit the batch to contextual-orchestrator and collect the vectors.

    Returns fitted vectors on success, or ``None`` to signal fallback. The
    orchestrator owns routing + cost; naruon records the reported batch id and
    cost on the job row for observability.
    """
    # SSRF-guard + allowlist + pinned-address transport, shared with every other
    # outbound LLM call. A None normalized_url means the base URL was rejected.
    try:
        normalized_url, client = await build_llm_provider_http_client(
            settings.orchestrator_base_url
        )
    except ValueError as exc:
        logger.warning(
            "Orchestrator base URL rejected by SSRF/allowlist guard; falling back: "
            "error_type=%s",
            type(exc).__name__,
        )
        return None
    if normalized_url is None:
        await client.aclose()
        logger.warning(
            "Orchestrator base URL missing/invalid; falling back to non-batch path"
        )
        return None

    submit_url = normalized_url.rstrip("/") + _BATCH_SUBMIT_PATH
    headers = {
        "Authorization": f"Bearer {settings.orchestrator_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "endpoint": settings.endpoint_alias,
        "inputs": list(texts),
        "metadata": _attribution_metadata(
            settings=settings,
            user_id=user_id,
            organization_id=organization_id,
        ),
    }

    try:
        async with client:
            document = await _submit_and_await(client, submit_url, headers, payload)
    except (EmbeddingGenerationError, ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "Orchestrator batch submit/retrieve failed; falling back: "
            "error_type=%s text_count=%s",
            type(exc).__name__,
            len(texts),
        )
        return None
    except Exception as exc:  # network/httpx errors -> graceful fallback
        logger.warning(
            "Orchestrator batch unreachable; falling back: error_type=%s text_count=%s",
            type(exc).__name__,
            len(texts),
        )
        return None

    vectors = _extract_ordered_vectors(document, count=len(texts), dimension=dimension)
    if vectors is None:
        logger.warning(
            "Orchestrator batch returned incomplete vectors; falling back: "
            "text_count=%s",
            len(texts),
        )
        return None

    _record_orchestrator_job(
        session,
        document,
        texts=texts,
        model=model,
        user_id=user_id,
        organization_id=organization_id,
        endpoint_alias=settings.endpoint_alias,
    )
    return vectors


def _attribution_metadata(
    *,
    settings: BatchEmbeddingSettings,
    user_id: str,
    organization_id: str | None,
) -> dict[str, str]:
    """Build the FULL attribution metadata the orchestrator ledger expects.

    Carries the cost-attribution dimensions (service, team, group, company)
    resolved from the tenant config alongside the observability keys (source,
    organization_id, user_id). ``company`` falls back to ``organization_id`` and
    ``service`` to the import service name so cost is always attributed to a real
    company/service even when the tenant leaves the optional dims unset. Empty
    dimensions are omitted so the orchestrator does not record blank values.
    """
    org = organization_id or ""
    metadata: dict[str, str] = {
        "source": "naruon-email-import",
        "organization_id": org,
        "user_id": user_id,
        "service": settings.attribution_service or "naruon-email-import",
        "company": settings.attribution_company or org,
    }
    if settings.attribution_team:
        metadata["team"] = settings.attribution_team
    if settings.attribution_group:
        metadata["group"] = settings.attribution_group
    # Drop any dimension that resolved to an empty string (e.g. no organization).
    return {key: value for key, value in metadata.items() if value}


async def _submit_and_await(
    client: Any,
    submit_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """POST the batch, then poll the returned batch until it reaches a terminal
    state. Returns the final orchestrator document (dict)."""
    response = await client.post(
        submit_url,
        json=payload,
        headers=headers,
        timeout=_ORCHESTRATOR_TIMEOUT_SECONDS,
    )
    document = _json_or_raise(response)

    status = str(document.get("status") or "").lower()
    if status in _SUCCESS_STATUSES and document.get("embeddings") is not None:
        return document
    if status in ("failed", "error", "canceled"):
        raise EmbeddingGenerationError(f"orchestrator batch rejected: status={status}")

    batch_id = document.get("batch_id") or document.get("id")
    if not batch_id:
        raise KeyError("orchestrator batch response missing batch_id")

    retrieve_url = submit_url.rstrip("/") + f"/{batch_id}"
    for _ in range(_ORCHESTRATOR_MAX_POLLS):
        await asyncio.sleep(_ORCHESTRATOR_POLL_INTERVAL_SECONDS)
        poll_response = await client.get(
            retrieve_url,
            headers=headers,
            timeout=_ORCHESTRATOR_TIMEOUT_SECONDS,
        )
        polled = _json_or_raise(poll_response)
        poll_status = str(polled.get("status") or "").lower()
        if poll_status in _SUCCESS_STATUSES:
            return polled
        if poll_status in ("failed", "error", "canceled"):
            raise EmbeddingGenerationError(
                f"orchestrator batch failed: status={poll_status}"
            )
    raise EmbeddingGenerationError("orchestrator batch timed out before completion")


def _json_or_raise(response: Any) -> dict[str, Any]:
    status_code = getattr(response, "status_code", 200)
    if int(status_code) >= 400:
        raise EmbeddingGenerationError(
            f"orchestrator batch HTTP error: status_code={status_code}"
        )
    document = response.json()
    if not isinstance(document, dict):
        raise TypeError("orchestrator batch response was not a JSON object")
    return document


def _extract_ordered_vectors(
    document: dict[str, Any], *, count: int, dimension: int
) -> list[list[float]] | None:
    """Map the orchestrator's embedding payload back to input order.

    Accepts either a plain list of vectors (positional) or a list of
    ``{"index": i, "embedding": [...]}`` objects. Returns ``None`` if any input
    is missing a vector (treated as incomplete -> fall back).
    """
    raw = document.get("embeddings")
    if not isinstance(raw, list) or not raw:
        return None

    ordered: list[list[float] | None] = [None] * count
    for position, entry in enumerate(raw):
        if isinstance(entry, dict):
            index = entry.get("index", position)
            vector = entry.get("embedding")
        else:
            index = position
            vector = entry
        if not isinstance(index, int) or not (0 <= index < count):
            continue
        if not isinstance(vector, (list, tuple)):
            continue
        ordered[index] = fit_embedding_vector(list(vector), dimension)

    if any(vector is None for vector in ordered):
        return None
    return [vector for vector in ordered if vector is not None]


def _record_orchestrator_job(
    session: AsyncSession,
    document: dict[str, Any],
    *,
    texts: list[str],
    model: str,
    user_id: str,
    organization_id: str | None,
    endpoint_alias: str | None,
) -> None:
    part_count = _safe_int(document.get("part_count"), default=1)
    total_tokens = _safe_int(document.get("total_tokens"), default=0)
    cost_micro_usd = _optional_int(document.get("cost_micro_usd"))
    batch_id = document.get("batch_id") or document.get("id")

    job = LlmBatchJob(
        batch_job_uid=f"llm_batch_{uuid.uuid4().hex}",
        organization_id=organization_id or "",
        user_id=user_id,
        job_status="completed",
        routing_mode="orchestrator",
        model_name=model,
        endpoint_alias=endpoint_alias,
        orchestrator_batch_uid=str(batch_id) if batch_id else None,
        total_items=len(texts),
        completed_items=len(texts),
        failed_items=0,
        total_tokens=total_tokens,
        part_count=part_count,
        cost_micro_usd=cost_micro_usd,
    )
    session.add(job)

    token_counts = document.get("token_counts")
    for sequence_no in range(len(texts)):
        token_count = 0
        if isinstance(token_counts, list) and sequence_no < len(token_counts):
            token_count = _safe_int(token_counts[sequence_no], default=0)
        session.add(
            LlmBatchItem(
                batch_item_uid=f"llm_batch_item_{uuid.uuid4().hex}",
                batch_job_uid=job.batch_job_uid,
                sequence_no=sequence_no,
                part_index=0,
                token_count=token_count,
                item_status="completed",
            )
        )


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --- Offline-dev fallback: local pg-llm-batch package -----------------------


def _plan_partitions(
    engine: ModuleType, dsn: str, model: str, texts: list[str]
) -> tuple[list[list[int]], list[int]]:
    """Group text indices into token/byte/record-bounded partitions.

    Runs the component's ``TokenCounter`` + ``BatchAccumulator`` (which count
    tokens inside Postgres via ``pg_tiktoken``) to split the batch the same way
    the standalone engine would. Pure planning: returns index partitions plus
    the per-text token counts. Synchronous (psycopg) — call via a thread.
    """
    config = engine.PostgresConfigStore(dsn)
    try:
        counter = engine.TokenCounter(dsn, config=config)
        accumulator = engine.BatchAccumulator(counter, model)
        partitions: list[list[int]] = []
        current: list[int] = []
        token_counts: list[int] = []
        for index, text in enumerate(texts):
            total_tokens, _system, _user = accumulator.compute_tokens("", text)
            token_counts.append(int(total_tokens))
            byte_size = engine.BatchAccumulator.compute_byte_size(text)
            if current and accumulator.would_exceed(total_tokens, byte_size):
                partitions.append(current)
                current = []
                accumulator.reset()
            accumulator.add_entry(str(index), text, total_tokens, byte_size)
            current.append(index)
        if current:
            partitions.append(current)
        return partitions, token_counts
    finally:
        close = getattr(config, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - defensive
                logger.debug(
                    "Failed to close pg_llm_batch config store",
                    exc_info=True,
                )


async def _run_local_engine_batch(
    session: AsyncSession,
    texts: list[str],
    *,
    embedding_provider: EmailImportEmbeddingProvider,
    settings: BatchEmbeddingSettings,
    model: str,
    user_id: str,
    organization_id: str | None,
    dimension: int,
) -> list[list[float]] | None:
    """Offline-dev fallback: partition locally via a pg-llm-batch package.

    Only reached when the orchestrator is unconfigured/unavailable *and* a local
    DSN is present. Returns fitted vectors on success, else ``None`` to fall back
    to the per-item path.
    """
    engine = load_batch_engine()
    if engine is None:
        return None

    dsn = settings.local_dsn
    if not dsn:
        return None

    try:
        partitions, token_counts = await asyncio.to_thread(
            _plan_partitions, engine, dsn, model, texts
        )
    except Exception as exc:
        logger.warning(
            "Local batch planning unavailable; falling back to per-item path: "
            "error_type=%s text_count=%s",
            type(exc).__name__,
            len(texts),
        )
        return None

    job = LlmBatchJob(
        batch_job_uid=f"llm_batch_{uuid.uuid4().hex}",
        organization_id=organization_id or "",
        user_id=user_id,
        job_status="preparing",
        routing_mode="local_engine",
        model_name=model,
        endpoint_alias=settings.endpoint_alias,
        total_items=len(texts),
        completed_items=0,
        failed_items=0,
        total_tokens=sum(token_counts),
        part_count=len(partitions),
    )
    items = _new_batch_items(job.batch_job_uid, partitions, token_counts)
    session.add(job)
    for item in items:
        session.add(item)

    results: list[list[float] | None] = [None] * len(texts)
    try:
        for index_group in partitions:
            part_texts = [texts[i] for i in index_group]
            vectors = await generate_embeddings(
                part_texts,
                embedding_provider.api_key,
                base_url=embedding_provider.base_url,
                model=model,
            )
            for offset, text_index in enumerate(index_group):
                if offset < len(vectors):
                    results[text_index] = fit_embedding_vector(
                        vectors[offset], dimension
                    )
    except (EmbeddingGenerationError, ValueError, TypeError) as exc:
        logger.warning(
            "Local batch embedding generation failed; falling back to per-item path: "
            "error_type=%s text_count=%s part_count=%s",
            type(exc).__name__,
            len(texts),
            len(partitions),
        )
        _mark_job_failed(job, items, error_code=type(exc).__name__)
        return None

    if any(vector is None for vector in results):
        logger.warning(
            "Local batch embedding returned incomplete vectors; falling back: "
            "text_count=%s",
            len(texts),
        )
        _mark_job_failed(job, items, error_code="incomplete_vectors")
        return None

    _mark_job_completed(job, items)
    return [vector for vector in results if vector is not None]


def _new_batch_items(
    batch_job_uid: str,
    partitions: list[list[int]],
    token_counts: list[int],
) -> list[LlmBatchItem]:
    items: list[LlmBatchItem] = []
    for part_index, index_group in enumerate(partitions):
        for text_index in index_group:
            items.append(
                LlmBatchItem(
                    batch_item_uid=f"llm_batch_item_{uuid.uuid4().hex}",
                    batch_job_uid=batch_job_uid,
                    sequence_no=text_index,
                    part_index=part_index,
                    token_count=(
                        token_counts[text_index]
                        if text_index < len(token_counts)
                        else 0
                    ),
                    item_status="queued",
                )
            )
    return items


def _mark_job_completed(job: LlmBatchJob, items: list[LlmBatchItem]) -> None:
    job.job_status = "completed"
    job.completed_items = job.total_items
    for item in items:
        item.item_status = "completed"


def _mark_job_failed(
    job: LlmBatchJob, items: list[LlmBatchItem], *, error_code: str
) -> None:
    job.job_status = "failed"
    job.failed_items = job.total_items
    job.error_code = error_code
    for item in items:
        item.item_status = "failed"
