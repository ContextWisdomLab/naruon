"""Tests for batch-tolerant embedding routing via contextual-orchestrator.

Fast, fully-mocked unit tests: no live orchestrator, Postgres, pg_tiktoken, or
the pg-llm-batch package is required. They verify the properties the
integration promises:

* bulk import embeddings route through the **orchestrator batch API** (submit +
  retrieve) when a tenant has enabled + configured batching, and the job is
  recorded with the orchestrator's batch id and reported cost;
* the path degrades gracefully (returns ``None`` so callers fall back to the
  per-item path) when batching is disabled, the orchestrator base URL is
  rejected by the SSRF/allowlist guard, or the orchestrator is unreachable;
* the ``pg-llm-batch`` package is only used as an offline-dev fallback, gated
  behind orchestrator-unavailable;
* batch config (enablement, base URL, token, DSN) is read from the per-tenant
  Fernet-encrypted ``tenant_configs`` row, never from ``os.getenv``.
"""

import os
import types
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from core.config import settings
from db.models import LlmBatchItem, LlmBatchJob, TenantConfig
from services.email_import_service import (
    EmailImportBatchContext,
    EmailImportEmbeddingProvider,
    _generate_import_embeddings,
)
import services.batch_embedding_service as batch_module


PROVIDER = EmailImportEmbeddingProvider(
    api_key="secret-provider-token",
    base_url="http://gateway.internal/v1",
    embedding_model="text-embedding-test",
)

ORCH_URL = "https://orchestrator.internal"


@pytest.fixture(autouse=True)
def encryption_key():
    old_key = settings.ENCRYPTION_KEY
    settings.ENCRYPTION_KEY = SecretStr(Fernet.generate_key().decode("ascii"))
    yield
    settings.ENCRYPTION_KEY = old_key


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch):
    monkeypatch.setattr(batch_module, "_ORCHESTRATOR_POLL_INTERVAL_SECONDS", 0)


class FakeResult:
    def __init__(self, tenant_config):
        self._tenant_config = tenant_config

    def scalar_one_or_none(self):
        return self._tenant_config


class FakeAsyncSession:
    """Minimal async session: returns a tenant config and records .add()."""

    def __init__(self, tenant_config=None):
        self.tenant_config = tenant_config
        self.added: list = []

    async def execute(self, _stmt):
        return FakeResult(self.tenant_config)

    def add(self, obj):
        self.added.append(obj)


# --- Fake orchestrator HTTP client ------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Stands in for the pinned httpx.AsyncClient the orchestrator submit uses.

    ``post_responses``/``get_responses`` are consumed in order; a value that is
    an Exception (or Exception instance) is raised to simulate a network error.
    """

    def __init__(self, post_responses=None, get_responses=None):
        self._post = list(post_responses or [])
        self._get = list(get_responses or [])
        self.post_calls: list = []
        self.get_calls: list = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False

    async def aclose(self):
        self.closed = True

    def _next(self, queue, calls, url, kwargs):
        calls.append({"url": url, **kwargs})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def post(self, url, **kwargs):
        return self._next(self._post, self.post_calls, url, kwargs)

    async def get(self, url, **kwargs):
        return self._next(self._get, self.get_calls, url, kwargs)


def _patch_client(monkeypatch, client, normalized_url=ORCH_URL):
    async def _build(_base_url):
        return normalized_url, client

    monkeypatch.setattr(batch_module, "build_llm_provider_http_client", _build)


def _orchestrator_tenant_config(**overrides):
    config = TenantConfig(user_id="user-1", organization_id="org-acme")
    config.batch_embedding_enabled = True
    config.batch_orchestrator_base_url = ORCH_URL
    config.batch_orchestrator_token = "orch-secret-token"
    config.batch_orchestrator_endpoint = "primary_gateway"
    config.batch_embedding_model = "text-embedding-test"
    config.batch_local_dsn = None
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _embeddings_payload(count, dim=8):
    return [{"index": i, "embedding": [0.5] * dim} for i in range(count)]


# --- Fake pg-llm-batch engine (offline-dev fallback) ------------------------


class _FakeConfigStore:
    def __init__(self, dsn):
        self.dsn = dsn
        self.closed = False

    def close(self):
        self.closed = True


class _FakeTokenCounter:
    def __init__(self, dsn, config=None):
        self.dsn = dsn
        self.config = config


class _FakeAccumulator:
    """Partitions into groups of two to exercise multi-part planning."""

    def __init__(self, counter, model):
        self.model = model
        self.reset()

    def reset(self):
        self.record_count = 0

    def compute_tokens(self, _system, user):
        tokens = len(user)
        return tokens, 0, tokens

    @staticmethod
    def compute_byte_size(line):
        return len(line.encode("utf-8")) + 1

    def would_exceed(self, _tokens, _byte_size):
        return self.record_count >= 2

    def add_entry(self, _rid, _line, _tokens, _byte_size):
        self.record_count += 1


def _fake_engine():
    return types.SimpleNamespace(
        PostgresConfigStore=_FakeConfigStore,
        TokenCounter=_FakeTokenCounter,
        BatchAccumulator=_FakeAccumulator,
    )


# --- Primary path: orchestrator submit (synchronous completion) -------------


@pytest.mark.asyncio
async def test_import_embeddings_route_through_orchestrator(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    completed = FakeResponse(
        {
            "batch_id": "orc_batch_123",
            "status": "completed",
            "embeddings": _embeddings_payload(3),
            "cost_micro_usd": 4200,
            "part_count": 2,
            "total_tokens": 30,
            "token_counts": [10, 10, 10],
        }
    )
    client = FakeAsyncClient(post_responses=[completed])
    _patch_client(monkeypatch, client)

    texts = ["body", "att-1", "att-2"]
    result = await batch_module.try_batch_import_embeddings(
        session,
        texts,
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert result is not None
    assert len(result) == 3
    assert all(len(vector) == 8 for vector in result)
    # Submitted once, no polling needed (completed synchronously).
    assert len(client.post_calls) == 1
    assert client.post_calls[0]["url"] == ORCH_URL + "/v1/batch/embeddings"
    # Bearer token came from the Fernet DB, sent as Authorization header.
    assert (
        client.post_calls[0]["headers"]["Authorization"] == "Bearer orch-secret-token"
    )
    body = client.post_calls[0]["json"]
    assert body["inputs"] == texts
    assert body["endpoint"] == "primary_gateway"

    jobs = [obj for obj in session.added if isinstance(obj, LlmBatchJob)]
    items = [obj for obj in session.added if isinstance(obj, LlmBatchItem)]
    assert len(jobs) == 1
    job = jobs[0]
    assert job.routing_mode == "orchestrator"
    assert job.job_status == "completed"
    assert job.orchestrator_batch_uid == "orc_batch_123"
    assert job.cost_micro_usd == 4200
    assert job.part_count == 2
    assert job.total_items == 3
    assert len(items) == 3
    assert all(item.item_status == "completed" for item in items)
    assert [item.token_count for item in items] == [10, 10, 10]


@pytest.mark.asyncio
async def test_orchestrator_bounds_requests_and_preserves_input_order(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    batch_size = batch_module._ORCHESTRATOR_MAX_INPUTS_PER_REQUEST
    texts = [f"text-{index}" for index in range(batch_size + 2)]
    responses = []
    for start in range(0, len(texts), batch_size):
        count = min(batch_size, len(texts) - start)
        responses.append(
            FakeResponse(
                {
                    "batch_id": f"orc_batch_{start}",
                    "status": "completed",
                    "embeddings": [
                        {"index": index, "embedding": [float(start + index)] * 8}
                        for index in range(count)
                    ],
                }
            )
        )
    client = FakeAsyncClient(post_responses=responses)
    _patch_client(monkeypatch, client)

    result = await batch_module.try_batch_import_embeddings(
        session,
        texts,
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert result is not None
    assert [len(call["json"]["inputs"]) for call in client.post_calls] == [
        batch_size,
        2,
    ]
    assert [vector[0] for vector in result] == [
        float(index) for index in range(len(texts))
    ]
    jobs = [obj for obj in session.added if isinstance(obj, LlmBatchJob)]
    assert [job.total_items for job in jobs] == [batch_size, 2]


def test_orchestrator_partitions_by_utf8_bytes_without_splitting_inputs():
    input_bytes = batch_module._ORCHESTRATOR_MAX_INPUT_BYTES
    first = "가" * (input_bytes // 12)
    second = "나" * (input_bytes // 12)

    assert batch_module._partition_orchestrator_inputs([]) == []
    partitions = batch_module._partition_orchestrator_inputs([first, second])

    assert partitions == [[first], [second]]
    assert batch_module._partition_orchestrator_inputs(["x" * input_bytes]) is None


def test_orchestrator_partitions_by_serialized_json_bytes():
    escaped = '"' * 18_000
    plain = "x" * 18_000

    partitions = batch_module._partition_orchestrator_inputs(
        [escaped, plain],
        model="text-embedding-test",
        endpoint_alias="primary_gateway",
        metadata={"source": "naruon-email-import"},
    )

    assert partitions == [[escaped], [plain]]
    assert (
        batch_module._serialized_orchestrator_payload_bytes(
            [escaped],
            model="text-embedding-test",
            endpoint_alias="primary_gateway",
            metadata={"source": "naruon-email-import"},
        )
        <= batch_module._ORCHESTRATOR_MAX_INPUT_BYTES
    )


@pytest.mark.asyncio
async def test_orchestrator_preserves_completed_partitions_when_later_partition_fails(
    monkeypatch,
):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    batch_size = batch_module._ORCHESTRATOR_MAX_INPUTS_PER_REQUEST
    texts = [f"text-{index}" for index in range(batch_size + 2)]
    client = FakeAsyncClient(
        post_responses=[
            FakeResponse(
                {
                    "batch_id": "orc_batch_first",
                    "status": "completed",
                    "embeddings": _embeddings_payload(batch_size),
                }
            ),
            RuntimeError("second partition unavailable"),
        ]
    )
    _patch_client(monkeypatch, client)

    result = await batch_module.try_batch_import_embeddings(
        session,
        texts,
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert isinstance(result, batch_module.BatchEmbeddingPartial)
    assert len(result.completed_vectors) == batch_size
    assert result.pending_texts == texts[batch_size:]
    assert len(client.post_calls) == 2


@pytest.mark.asyncio
async def test_orchestrator_falls_back_for_single_input_over_byte_budget():
    session = FakeAsyncSession(_orchestrator_tenant_config())

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["x" * (batch_module._ORCHESTRATOR_MAX_INPUT_BYTES + 1)],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert result is None
    assert session.added == []


@pytest.mark.asyncio
async def test_orchestrator_submit_then_retrieve_poll(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    submit = FakeResponse({"batch_id": "orc_batch_999", "status": "running"})
    running = FakeResponse({"batch_id": "orc_batch_999", "status": "running"})
    done = FakeResponse(
        {
            "batch_id": "orc_batch_999",
            "status": "completed",
            "embeddings": _embeddings_payload(2),
            "cost_micro_usd": 100,
        }
    )
    client = FakeAsyncClient(post_responses=[submit], get_responses=[running, done])
    _patch_client(monkeypatch, client)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body", "att-1"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert result is not None
    assert len(result) == 2
    # One submit + two retrieve polls (running, then completed).
    assert len(client.post_calls) == 1
    assert len(client.get_calls) == 2
    assert client.get_calls[0]["url"] == ORCH_URL + "/v1/batch/embeddings/orc_batch_999"
    jobs = [obj for obj in session.added if isinstance(obj, LlmBatchJob)]
    assert jobs[0].orchestrator_batch_uid == "orc_batch_999"


# --- Graceful degradation ---------------------------------------------------


@pytest.mark.asyncio
async def test_fall_back_when_batch_disabled(monkeypatch):
    session = FakeAsyncSession(
        _orchestrator_tenant_config(batch_embedding_enabled=False)
    )
    build = AsyncMock()
    monkeypatch.setattr(batch_module, "build_llm_provider_http_client", build)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
    )

    assert result is None
    build.assert_not_awaited()
    assert session.added == []


@pytest.mark.asyncio
async def test_fall_back_when_orchestrator_base_url_rejected(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    # normalized_url None simulates the SSRF/allowlist guard rejecting the host.
    rejecting_client = FakeAsyncClient()
    _patch_client(monkeypatch, rejecting_client, normalized_url=None)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
    )

    assert result is None
    assert rejecting_client.closed is True
    assert session.added == []


@pytest.mark.asyncio
async def test_fall_back_when_orchestrator_unreachable_no_local(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    client = FakeAsyncClient(post_responses=[httpx.ConnectError("orchestrator down")])
    _patch_client(monkeypatch, client)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
    )

    assert result is None
    # No local DSN configured -> no job persisted, caller falls back to per-item.
    assert session.added == []


@pytest.mark.asyncio
async def test_fall_back_when_orchestrator_http_error(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    client = FakeAsyncClient(post_responses=[FakeResponse({}, status_code=503)])
    _patch_client(monkeypatch, client)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body", "att"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
    )

    assert result is None
    assert session.added == []


@pytest.mark.asyncio
async def test_fall_back_when_orchestrator_returns_incomplete_vectors(monkeypatch):
    session = FakeAsyncSession(_orchestrator_tenant_config())
    # Only one embedding returned for two inputs -> incomplete -> fall back.
    client = FakeAsyncClient(
        post_responses=[
            FakeResponse(
                {
                    "batch_id": "b",
                    "status": "completed",
                    "embeddings": _embeddings_payload(1),
                }
            )
        ]
    )
    _patch_client(monkeypatch, client)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body", "att"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert result is None
    assert session.added == []


# --- Offline-dev fallback: local pg-llm-batch package -----------------------


@pytest.mark.asyncio
async def test_falls_back_to_local_engine_when_orchestrator_unavailable(monkeypatch):
    session = FakeAsyncSession(
        _orchestrator_tenant_config(batch_local_dsn="postgresql://batch-host/batch_db")
    )
    # Orchestrator submit fails (network) so the local package path is tried.
    client = FakeAsyncClient(post_responses=[httpx.ConnectError("down")])
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(batch_module, "load_batch_engine", _fake_engine)
    generate = AsyncMock(side_effect=lambda t, *a, **k: [[0.5] * 8 for _ in t])
    monkeypatch.setattr(batch_module, "generate_embeddings", generate)

    texts = ["body", "att-1", "att-2", "att-3", "att-4"]
    result = await batch_module.try_batch_import_embeddings(
        session,
        texts,
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
        dimension=8,
    )

    assert result is not None
    assert len(result) == 5
    # 5 texts partitioned two-at-a-time -> 3 parts -> 3 embedding calls.
    assert generate.await_count == 3
    # Credentials came from the runtime provider, not os.getenv.
    assert generate.await_args_list[0].args[1] == "secret-provider-token"
    jobs = [obj for obj in session.added if isinstance(obj, LlmBatchJob)]
    assert jobs[0].routing_mode == "local_engine"
    assert jobs[0].job_status == "completed"
    assert jobs[0].part_count == 3


@pytest.mark.asyncio
async def test_local_fallback_skipped_when_package_missing(monkeypatch):
    session = FakeAsyncSession(
        _orchestrator_tenant_config(batch_local_dsn="postgresql://batch-host/batch_db")
    )
    client = FakeAsyncClient(post_responses=[httpx.ConnectError("down")])
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(batch_module, "load_batch_engine", lambda: None)
    generate = AsyncMock()
    monkeypatch.setattr(batch_module, "generate_embeddings", generate)

    result = await batch_module.try_batch_import_embeddings(
        session,
        ["body"],
        embedding_provider=PROVIDER,
        user_id="user-1",
        organization_id="org-acme",
    )

    assert result is None
    generate.assert_not_awaited()
    assert session.added == []


@pytest.mark.asyncio
async def test_load_batch_engine_is_import_guarded():
    # The package is not installed on the backend path in this environment,
    # so the loader must degrade to None rather than raising ImportError.
    batch_module._ENGINE_CACHE.clear()
    try:
        assert batch_module.load_batch_engine() is None
    finally:
        batch_module._ENGINE_CACHE.clear()


# --- email_import_service wiring --------------------------------------------


@pytest.mark.asyncio
async def test_generate_import_embeddings_prefers_batch_context(monkeypatch):
    context = EmailImportBatchContext(
        session=FakeAsyncSession(), user_id="user-1", organization_id="org-acme"
    )
    batched = [[0.1] * 1536, [0.2] * 1536]
    routed = AsyncMock(return_value=batched)
    monkeypatch.setattr(
        "services.email_import_service.try_batch_import_embeddings", routed
    )
    per_item = AsyncMock()
    monkeypatch.setattr("services.email_import_service.generate_embeddings", per_item)

    result = await _generate_import_embeddings(
        ["body", "attachment"],
        embedding_provider=PROVIDER,
        batch_context=context,
    )

    assert result == batched
    routed.assert_awaited_once()
    # Batch path handled it; the per-item embedding path was never touched.
    per_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_import_embeddings_falls_back_when_batch_returns_none(
    monkeypatch,
):
    context = EmailImportBatchContext(
        session=FakeAsyncSession(), user_id="user-1", organization_id="org-acme"
    )
    routed = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "services.email_import_service.try_batch_import_embeddings", routed
    )
    per_item = AsyncMock(return_value=[[0.9] * 1536, [0.9] * 1536])
    monkeypatch.setattr("services.email_import_service.generate_embeddings", per_item)

    result = await _generate_import_embeddings(
        ["body", "attachment"],
        embedding_provider=PROVIDER,
        batch_context=context,
    )

    routed.assert_awaited_once()
    # Fell through to the existing per-item path.
    per_item.assert_awaited()
    assert len(result) == 2


# --- Config from the Fernet DB (never env) ----------------------------------


@pytest.mark.asyncio
async def test_batch_config_resolves_from_fernet_db_not_env(monkeypatch):
    monkeypatch.delenv("BATCH_ORCHESTRATOR_TOKEN", raising=False)
    monkeypatch.delenv("PG_LLM_BATCH_DSN", raising=False)
    secret_token = "orch-super-secret-token"
    secret_dsn = "postgresql://batch-user:batch-pass@batch-host/batch_db"

    engine = create_engine("sqlite:///:memory:")
    TenantConfig.__table__.create(engine)
    try:
        with Session(engine) as session:
            session.add(
                TenantConfig(
                    user_id="user-1",
                    organization_id="org-acme",
                    batch_embedding_enabled=True,
                    batch_orchestrator_base_url=ORCH_URL,
                    batch_orchestrator_token=secret_token,
                    batch_orchestrator_endpoint="primary_gateway",
                    batch_embedding_model="text-embedding-test",
                    batch_local_dsn=secret_dsn,
                )
            )
            session.commit()

            # Stored at rest as Fernet ciphertext, not the plaintext secrets.
            raw_token, raw_dsn = session.execute(
                text(
                    "SELECT batch_orchestrator_token, batch_local_dsn "
                    "FROM tenant_configs"
                )
            ).one()
            assert raw_token != secret_token
            assert raw_dsn != secret_dsn
            assert "batch-pass" not in raw_dsn

            reloaded = session.query(TenantConfig).one()
            assert reloaded.batch_orchestrator_token == secret_token
            assert reloaded.batch_local_dsn == secret_dsn
    finally:
        engine.dispose()

    # The resolver returns the secrets decrypted from the DB row; no env var
    # supplied them.
    resolved = await batch_module.resolve_batch_embedding_settings(
        FakeAsyncSession(reloaded),
        user_id="user-1",
        organization_id="org-acme",
    )
    assert resolved is not None
    assert resolved.orchestrator_base_url == ORCH_URL
    assert resolved.orchestrator_token == secret_token
    assert resolved.endpoint_alias == "primary_gateway"
    assert resolved.local_dsn == secret_dsn
    assert resolved.has_orchestrator is True
    assert "BATCH_ORCHESTRATOR_TOKEN" not in os.environ


@pytest.mark.asyncio
async def test_resolve_returns_none_when_enabled_but_unconfigured():
    config = TenantConfig(user_id="user-1", organization_id="org-acme")
    config.batch_embedding_enabled = True
    config.batch_orchestrator_base_url = None
    config.batch_orchestrator_token = None
    config.batch_local_dsn = None

    resolved = await batch_module.resolve_batch_embedding_settings(
        FakeAsyncSession(config),
        user_id="user-1",
        organization_id="org-acme",
    )
    assert resolved is None
