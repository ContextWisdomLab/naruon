"""contextual-orchestrator inference gateway for naruon's in-process Noema agent.

naruon is a consumer of ``ContextualWisdomLab/contextual-orchestrator``, not a
second LLM-provider-routing authority. The general-purpose Noema workspace
agent (:mod:`services.noema_agent`) sends every chat-completion call through
this gateway using a per-tenant Fernet-encrypted credential
(``tenant_configs.noema_orchestrator_base_url`` /
``noema_orchestrator_token``), never a direct tenant LLM-provider key. The
orchestrator owns model selection, upstream failover, and cost -- naruon does
not pick or fail over across models here; the model alias sent on every call
is always :data:`ORCHESTRATOR_MODEL_ALIAS`.

This keeps two separately-authorized scopes distinct: naruon's tenant-scoped
Noema gateway credential resolved here, versus ``ContextualWisdomLab/.github``'s
central review-pipeline credential used by the org's CI Noema reviewer
(``scripts/ci/noema_review_gate.py``). This module never reads or writes
anything under that CI credential, and nothing here ever sends workspace data
through it.

Per ``docs/CWL-MASTER-CONTEXT.md`` (``ContextualWisdomLab/.github``), Noema is
actually one shared agent runtime (Pydantic-AI/Codex-Python) consumed by
naruon, the ``.github`` CI review agent, and wardnet's AI SOC quarantine
sandbox -- the credential scoping above is a security choice for this module,
not a claim that the deployments are permanently separate or share nothing
beyond a name; see ``ContextualWisdomLab/naruon#1527`` for the corrected
reasoning (its ``docs/adr/0006-noema-bounded-context-separation.md`` lives
on that PR's own branch, not this one, until it merges).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from services.llm_provider_urls import validate_llm_provider_base_url_async
from services.tenant_config_scope import get_scoped_tenant_config

ORCHESTRATOR_MODEL_ALIAS = "contextual-orchestrator"


@dataclass(frozen=True)
class OrchestratorGateway:
    """A tenant's resolved contextual-orchestrator gateway credential.

    ``base_url`` and ``inference_token`` come from the per-tenant
    Fernet-encrypted ``tenant_configs`` row (never ``os.getenv``).
    ``model_alias`` is always :data:`ORCHESTRATOR_MODEL_ALIAS`: naruon asks
    the orchestrator to select the underlying model, it never chooses one.
    """

    base_url: str
    inference_token: str
    model_alias: str = ORCHESTRATOR_MODEL_ALIAS


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


async def resolve_orchestrator_gateway(
    session: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
) -> OrchestratorGateway | None:
    """Resolve the tenant's contextual-orchestrator gateway config.

    Returns ``None`` when the tenant has not configured the gateway (missing
    base URL or token) or when the stored base URL fails SSRF/allowlist
    validation, so the caller can degrade to a single, structured
    "unavailable" result for every one of those reasons -- this never falls
    back to constructing a direct provider client. Validating here (rather
    than deferring to :func:`services.llm_provider_urls.build_llm_provider_http_client`
    at agent-build time) keeps that later call's own ``None`` result reserved
    for one thing only: the pydantic-ai runtime being absent.
    """
    tenant_config = await get_scoped_tenant_config(session, user_id, organization_id)
    if tenant_config is None:
        return None
    base_url = _clean(getattr(tenant_config, "noema_orchestrator_base_url", None))
    token = _clean(getattr(tenant_config, "noema_orchestrator_token", None))
    if not base_url or not token:
        return None
    validated_base_url = await validate_llm_provider_base_url_async(base_url)
    if not validated_base_url:
        return None
    return OrchestratorGateway(base_url=validated_base_url, inference_token=token)
