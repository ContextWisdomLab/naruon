"""Noema general agent.

A general-purpose `Pydantic-AI <https://ai.pydantic.dev>`_ (MIT) agent that
reasons over the naruon workspace. Every chat-completion call is routed
through ``ContextualWisdomLab/contextual-orchestrator`` — resolved through
:func:`services.orchestrator_gateway.resolve_orchestrator_gateway` from the
tenant's own Fernet-encrypted gateway credential, never ``os.getenv`` and
never a direct tenant LLM-provider key. Production LLM routing belongs to
contextual-orchestrator; naruon owns the Noema tools/authorization/context,
not a second provider-routing authority. This is a distinct, tenant-scoped
credential from the one ``ContextualWisdomLab/.github``'s central
review-pipeline Noema uses (``scripts/ci/noema_review_gate.py``); naruon's
workspace data is never sent through that CI credential path. Per
``docs/CWL-MASTER-CONTEXT.md`` (``ContextualWisdomLab/.github``), Noema is
actually one shared agent runtime (Pydantic-AI/Codex-Python) consumed by
naruon, the ``.github`` CI review agent, and wardnet's AI SOC quarantine
sandbox — the per-deployment credential scoping here is a security choice
for this module, not a claim that the deployments are permanently separate
or share nothing beyond a name; see ``ContextualWisdomLab/naruon#1527`` for
the corrected reasoning (its ``docs/adr/0006-noema-bounded-context-separation.md``
lives on that PR's own branch, not this one — this docstring cannot resolve
it as a local path until that PR merges). It is given a small set of tools
that plug into the existing service and runner seams:

* **read/search mail** and **content-graph queries** are workspace-scoped SQL reads.
* **task actions** update ``TicketTask`` rows and are audit-logged.
* **calendar conflict check** validates the proposal but fails closed until a
  scoped authoritative provider-calendar read seam exists.
* **writeback** is dispatched to the self-hosted runner (the ``write_caldav`` /
  ``write_webdav`` actions handled by :class:`SelfHostedConnector`), preserving
  naruon's opt-in-writeback and audit-logged contract.

Pydantic-AI is an *optional* runtime dependency (installed via
``backend/requirements-agent.txt``). When it — or a usable LLM provider — is not
available the agent degrades gracefully: it returns a structured no-op notice
instead of raising, so the surrounding request path stays healthy.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AuditLog,
    ContentNodeRecord,
    Email,
    KnowledgeGraphEdgeRecord,
    TicketTask,
)
from services.calendar_conflict_policy import (
    CalendarCommitment,
    CalendarPolicyValidationError,
)
from services.llm_provider_urls import build_llm_provider_http_client
from services.orchestrator_gateway import (
    OrchestratorGateway,
    resolve_orchestrator_gateway,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pydantic_ai import Agent

# ``RunContext`` must live in this module's globals so that pydantic-ai can
# resolve the ``RunContext[NoemaAgentDeps]`` string annotations on the tool
# functions (with ``from __future__ import annotations`` active, pydantic-ai
# evaluates them via ``get_type_hints`` against each function's module globals —
# a closure-local alias would raise ``NameError``). pydantic-ai stays optional:
# when it is not installed this falls back to ``Any`` and the annotation is
# never evaluated because ``build_noema_agent`` returns early.
try:  # pragma: no cover - trivial import guard
    from pydantic_ai import RunContext
except ImportError:  # pydantic-ai is an optional runtime dependency
    RunContext = Any  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

AGENT_ID = "noema-general-agent"

# Task statuses the agent is allowed to set. Anything else is refused so the LLM
# cannot write arbitrary status codes into the tenant's tickets.
ALLOWED_TASK_STATUSES = frozenset(
    {"open", "in_progress", "blocked", "done", "cancelled"}
)

# Runner actions the agent may dispatch. These are exactly the writeback actions
# handled by SelfHostedConnector.
WRITEBACK_ACTIONS = frozenset({"write_caldav", "write_webdav"})

_MAX_MAIL_RESULTS = 20
_MAX_CONTENT_NODES = 40
_SNIPPET_LENGTH = 280

RunnerDispatcher = Callable[..., Awaitable[dict[str, Any]]]


@dataclass
class NoemaAgentDeps:
    """Per-run dependencies injected into every tool call.

    ``writeback_enabled`` is the opt-in switch: unless the caller explicitly
    turns it on, the writeback tool is a no-op that never touches the runner.
    """

    session: AsyncSession
    user_id: str
    organization_id: str | None
    workspace_id: str
    writeback_enabled: bool = False
    dispatcher: RunnerDispatcher | None = None
    tool_calls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NoemaAgentResult:
    """Outcome of a :func:`run_noema_agent` call."""

    status: Literal["ok", "unavailable", "error"]
    output: str = ""
    notice: str | None = None
    provider_name: str | None = None
    tool_calls: tuple[str, ...] = ()
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _snippet(value: str | None) -> str:
    if not value:
        return ""
    collapsed = " ".join(value.split())
    if len(collapsed) <= _SNIPPET_LENGTH:
        return collapsed
    return collapsed[:_SNIPPET_LENGTH].rstrip() + "…"


async def _record_audit(
    deps: NoemaAgentDeps,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: str,
) -> None:
    """Append an audit-log row for a tool side effect and persist it."""
    deps.session.add(
        AuditLog(
            user_id=deps.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
    )
    await deps.session.commit()


# --------------------------------------------------------------------------- #
# Tool implementations (framework-agnostic so they can be unit-tested directly)
# --------------------------------------------------------------------------- #


async def tool_search_mail(
    deps: NoemaAgentDeps, query: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Search the owner's mail by subject/sender/body substring."""
    deps.tool_calls.append("search_mail")
    query = (query or "").strip()
    bounded = max(1, min(int(limit or 1), _MAX_MAIL_RESULTS))
    statement = select(Email).where(
        *Email.owner_filters(deps.user_id, deps.organization_id, deps.workspace_id),
    )
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                Email.subject.ilike(pattern),
                Email.sender.ilike(pattern),
                Email.body.ilike(pattern),
            )
        )
    statement = statement.order_by(Email.date.desc()).limit(bounded)
    result = await deps.session.execute(statement)
    emails = result.scalars().all()
    return [
        {
            "id": email.id,
            "message_id": email.message_id,
            "thread_id": email.thread_id,
            "subject": email.subject,
            "sender": email.sender,
            "date": email.date.isoformat() if email.date else None,
            "snippet": _snippet(email.body),
        }
        for email in emails
    ]


async def tool_read_mail(deps: NoemaAgentDeps, message_id: str) -> dict[str, Any]:
    """Read a single owned email by its message id."""
    deps.tool_calls.append("read_mail")
    message_id = (message_id or "").strip()
    if not message_id:
        return {"status": "error", "reason": "message_id is required"}
    statement = (
        select(Email)
        .where(
            *Email.owner_filters(deps.user_id, deps.organization_id, deps.workspace_id)
        )
        .where(Email.message_id == message_id)
        .limit(1)
    )
    result = await deps.session.execute(statement)
    email = result.scalars().first()
    if email is None:
        return {"status": "not_found", "message_id": message_id}
    return {
        "status": "ok",
        "id": email.id,
        "message_id": email.message_id,
        "thread_id": email.thread_id,
        "subject": email.subject,
        "sender": email.sender,
        "recipients": email.recipients,
        "date": email.date.isoformat() if email.date else None,
        "body": email.body,
    }


async def tool_content_graph_query(
    deps: NoemaAgentDeps, message_id: str
) -> dict[str, Any]:
    """Return the parsed content-graph nodes and edges for an owned email."""
    deps.tool_calls.append("content_graph_query")
    message_id = (message_id or "").strip()
    if not message_id:
        return {"status": "error", "reason": "message_id is required"}

    email_result = await deps.session.execute(
        select(Email.id)
        .where(
            *Email.owner_filters(deps.user_id, deps.organization_id, deps.workspace_id)
        )
        .where(Email.message_id == message_id)
        .limit(1)
    )
    email_id = email_result.scalar_one_or_none()
    if email_id is None:
        return {"status": "not_found", "message_id": message_id}

    node_result = await deps.session.execute(
        select(ContentNodeRecord)
        .where(ContentNodeRecord.email_id == email_id)
        .order_by(ContentNodeRecord.ordinal_index)
        .limit(_MAX_CONTENT_NODES)
    )
    nodes = node_result.scalars().all()

    edge_result = await deps.session.execute(
        select(KnowledgeGraphEdgeRecord)
        .where(KnowledgeGraphEdgeRecord.email_id == email_id)
        .order_by(KnowledgeGraphEdgeRecord.ordinal_index)
        .limit(_MAX_CONTENT_NODES)
    )
    edges = edge_result.scalars().all()

    return {
        "status": "ok",
        "message_id": message_id,
        "nodes": [
            {
                "uid": node.content_node_uid,
                "kind": node.node_kind,
                "path": node.node_path,
                "label": node.display_label,
                "text": _snippet(node.safe_text_content),
            }
            for node in nodes
        ],
        "edges": [
            {
                "uid": edge.edge_uid,
                "kind": edge.edge_kind,
                "source_uid": edge.source_record_uid,
            }
            for edge in edges
        ],
    }


async def tool_list_tasks(
    deps: NoemaAgentDeps, status: str | None = None
) -> list[dict[str, Any]]:
    """List the owner's tasks, optionally filtered by status."""
    deps.tool_calls.append("list_tasks")
    statement = select(TicketTask).where(
        TicketTask.user_id == deps.user_id,
        TicketTask.organization_id == deps.organization_id,
    )
    status = (status or "").strip()
    if status:
        statement = statement.where(TicketTask.status == status)
    statement = statement.order_by(TicketTask.updated_at.desc()).limit(
        _MAX_MAIL_RESULTS
    )
    result = await deps.session.execute(statement)
    tasks = result.scalars().all()
    return [
        {
            "task_uid": task.task_uid,
            "title": task.title,
            "status": task.status,
            "priority": task.priority,
            "source_type": task.source_type,
        }
        for task in tasks
    ]


async def tool_update_task_status(
    deps: NoemaAgentDeps, task_uid: str, status: str
) -> dict[str, Any]:
    """Update the status of an owned task. Audit-logged."""
    deps.tool_calls.append("update_task_status")
    task_uid = (task_uid or "").strip()
    status = (status or "").strip()
    if not task_uid:
        return {"status": "error", "reason": "task_uid is required"}
    if status not in ALLOWED_TASK_STATUSES:
        return {
            "status": "error",
            "reason": "unsupported status",
            "allowed": sorted(ALLOWED_TASK_STATUSES),
        }

    result = await deps.session.execute(
        select(TicketTask)
        .where(
            TicketTask.user_id == deps.user_id,
            TicketTask.organization_id == deps.organization_id,
            TicketTask.task_uid == task_uid,
        )
        .limit(1)
    )
    task = result.scalars().first()
    if task is None:
        return {"status": "not_found", "task_uid": task_uid}

    previous_status = task.status
    task.status = status
    task.updated_at = _utc_now()
    await _record_audit(
        deps,
        action="update",
        resource_type="ticket_task",
        resource_id=task_uid,
        details=f"noema-agent status {previous_status} -> {status}",
    )
    return {"status": "ok", "task_uid": task_uid, "new_status": status}


async def tool_dispatch_writeback(
    deps: NoemaAgentDeps,
    action: str,
    account: str,
    target_path: str,
    content: str,
) -> dict[str, Any]:
    """Dispatch an opt-in, audit-logged writeback to the self-hosted runner.

    The command is one of the ``write_caldav`` / ``write_webdav`` actions handled
    by :class:`SelfHostedConnector`. When writeback is not opted in this is a
    no-op that never contacts the runner.
    """
    deps.tool_calls.append("dispatch_writeback")
    action = (action or "").strip()
    account = (account or "").strip()
    target_path = (target_path or "").strip()

    if action not in WRITEBACK_ACTIONS:
        return {"status": "error", "reason": "unsupported writeback action"}
    if not account or not target_path:
        return {"status": "error", "reason": "account and target_path are required"}
    if not deps.writeback_enabled:
        # Opt-in contract: refuse to touch the runner unless explicitly enabled.
        return {
            "status": "skipped",
            "notice": "writeback is not enabled for this run (opt-in required)",
            "provider_write_executed": False,
        }
    if not deps.organization_id:
        return {"status": "error", "reason": "organization scope is required"}

    dispatcher = deps.dispatcher or _default_dispatcher
    command = {
        "action": action,
        "account": account,
        "target_path": target_path,
        "content": content or "",
    }
    dispatch_result = await dispatcher(deps.organization_id, deps.workspace_id, command)
    provider_write_executed = bool(
        isinstance(dispatch_result, dict)
        and dispatch_result.get("provider_write_executed", False)
    )
    await _record_audit(
        deps,
        action="writeback_executed"
        if provider_write_executed
        else "writeback_dispatched",
        resource_type="runner_writeback",
        resource_id=target_path,
        details=f"noema-agent {action} provider_write_executed={provider_write_executed}",
    )
    return {
        "status": "ok" if provider_write_executed else "dispatched",
        "action": action,
        "target_path": target_path,
        "provider_write_executed": provider_write_executed,
    }


async def _default_dispatcher(
    organization_id: str, workspace_id: str, command: dict[str, Any]
) -> dict[str, Any]:
    """Resolve the live runner connection manager lazily to avoid import cycles."""
    from api.runner_ws import manager as runner_manager

    return await runner_manager.dispatch_command(organization_id, workspace_id, command)


def _parse_commitment(
    commitment_id: str, start_at: str, end_at: str, status: str
) -> CalendarCommitment:
    """Parse ISO 8601 timestamps into a validated :class:`CalendarCommitment`.

    Raises :class:`CalendarPolicyValidationError` — the same typed failure
    :mod:`services.calendar_conflict_policy` itself raises — on a malformed
    timestamp, so callers only need to catch one exception type.
    """
    try:
        parsed_start = datetime.datetime.fromisoformat((start_at or "").strip())
        parsed_end = datetime.datetime.fromisoformat((end_at or "").strip())
    except (TypeError, ValueError) as exc:
        raise CalendarPolicyValidationError(
            "calendar_timestamp_timezone_required",
            "start_at/end_at must be ISO 8601 timestamps with a UTC offset",
        ) from exc
    return CalendarCommitment(
        commitment_id=commitment_id,
        start_at=parsed_start,
        end_at=parsed_end,
        status=status,  # type: ignore[arg-type]  # validated by __post_init__
    )


async def tool_check_calendar_conflict(
    deps: NoemaAgentDeps,
    proposed_commitment_id: str,
    proposed_start_at: str,
    proposed_end_at: str,
    proposed_status: str,
    existing: list[dict[str, str]],
) -> dict[str, Any]:
    """Refuse to assert availability without authoritative calendar evidence.

    Proposed timestamps still use the deterministic policy's validation
    contract. Naruon currently exposes only an outbound CalDAV write seam; it has no
    scoped inbound provider-calendar reader. ``existing`` is therefore
    untrusted conversational evidence and cannot establish availability.
    """
    deps.tool_calls.append("check_calendar_conflict")
    try:
        _parse_commitment(
            proposed_commitment_id, proposed_start_at, proposed_end_at, proposed_status
        )
    except CalendarPolicyValidationError as exc:
        return {"status": "error", "error_code": exc.error_code, "reason": str(exc)}

    return {
        "status": "error",
        "error_code": "calendar_authoritative_evidence_unavailable",
        "decision_code": "review_required",
        "reason": "Authoritative scoped provider calendar evidence is unavailable",
    }


# Introspectable catalog of the tools the agent exposes. Used for wiring tests
# and for documenting the agent's surface without importing pydantic-ai.
NOEMA_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {"name": "search_mail", "impl": tool_search_mail, "capability": "mail.search"},
    {"name": "read_mail", "impl": tool_read_mail, "capability": "mail.read"},
    {
        "name": "content_graph_query",
        "impl": tool_content_graph_query,
        "capability": "content_graph.query",
    },
    {"name": "list_tasks", "impl": tool_list_tasks, "capability": "tasks.read"},
    {
        "name": "update_task_status",
        "impl": tool_update_task_status,
        "capability": "tasks.update",
    },
    {
        "name": "check_calendar_conflict",
        "impl": tool_check_calendar_conflict,
        "capability": "calendar.conflict_check",
    },
    {
        "name": "dispatch_writeback",
        "impl": tool_dispatch_writeback,
        "capability": "calendar.writeback",
    },
)

SYSTEM_PROMPT = (
    "You are Noema, the general assistant for a naruon email workspace. "
    "Use the provided tools to read and search the owner's mail, inspect the "
    "content graph of an email, and manage tasks. When a message proposes or "
    "moves a meeting, use check_calendar_conflict, but never claim a time is "
    "available unless that tool has authoritative provider evidence. Only "
    "change task status or dispatch a writeback when the user clearly asks "
    "for it. Writebacks target the customer's own systems and require opt-in; "
    "if a writeback is skipped, explain that it must be enabled. Be concise "
    "and cite message ids you used."
)


def _load_pydantic_ai() -> Any | None:
    """Import pydantic-ai lazily; return ``None`` when it is not installed."""
    try:
        import pydantic_ai  # noqa: F401
        from pydantic_ai import Agent, RunContext

        # pydantic-ai 2.x renamed ``OpenAIModel`` to ``OpenAIChatModel``. Import
        # the current name; the old alias no longer exists on 2.x.
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError:
        logger.info("pydantic-ai is not installed; noema agent is disabled.")
        return None
    return {
        "Agent": Agent,
        "RunContext": RunContext,
        "OpenAIChatModel": OpenAIChatModel,
        "OpenAIProvider": OpenAIProvider,
    }


async def build_noema_agent(
    gateway: OrchestratorGateway,
) -> tuple["Agent | None", Callable[[], Awaitable[None]]]:
    """Build the pydantic-ai agent for a resolved contextual-orchestrator gateway.

    Returns ``(agent, closer)``. ``agent`` is ``None`` when pydantic-ai is not
    installed, or when the gateway's ``base_url`` fails SSRF/allowlist
    validation (a stored credential can still be malformed); ``closer``
    always closes any opened HTTP client. Never falls back to a direct
    tenant LLM-provider client on either condition.
    """
    from openai import AsyncOpenAI

    async def _noop_closer() -> None:
        return None

    modules = _load_pydantic_ai()
    if modules is None:
        return None, _noop_closer

    validated_base_url, http_client = await build_llm_provider_http_client(
        gateway.base_url
    )
    if validated_base_url is None:
        await http_client.aclose()
        return None, _noop_closer

    openai_client = AsyncOpenAI(
        api_key=gateway.inference_token,
        base_url=validated_base_url,
        http_client=http_client,
    )

    async def _closer() -> None:
        await openai_client.close()

    model = modules["OpenAIChatModel"](
        gateway.model_alias,
        provider=modules["OpenAIProvider"](openai_client=openai_client),
    )
    agent = modules["Agent"](
        model,
        deps_type=NoemaAgentDeps,
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.tool
    async def search_mail(  # type: ignore[unused-ignore]
        ctx: RunContext[NoemaAgentDeps], query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search the owner's mail by subject, sender, or body text."""
        return await tool_search_mail(ctx.deps, query, limit)

    @agent.tool
    async def read_mail(
        ctx: RunContext[NoemaAgentDeps], message_id: str
    ) -> dict[str, Any]:
        """Read the full body of a single owned email by message id."""
        return await tool_read_mail(ctx.deps, message_id)

    @agent.tool
    async def content_graph_query(
        ctx: RunContext[NoemaAgentDeps], message_id: str
    ) -> dict[str, Any]:
        """Return the content-graph nodes and edges parsed from an owned email."""
        return await tool_content_graph_query(ctx.deps, message_id)

    @agent.tool
    async def list_tasks(
        ctx: RunContext[NoemaAgentDeps], status: str | None = None
    ) -> list[dict[str, Any]]:
        """List the owner's tasks, optionally filtered by status."""
        return await tool_list_tasks(ctx.deps, status)

    @agent.tool
    async def update_task_status(
        ctx: RunContext[NoemaAgentDeps], task_uid: str, status: str
    ) -> dict[str, Any]:
        """Update the status of an owned task (audit-logged)."""
        return await tool_update_task_status(ctx.deps, task_uid, status)

    @agent.tool
    async def check_calendar_conflict(
        ctx: RunContext[NoemaAgentDeps],
        proposed_commitment_id: str,
        proposed_start_at: str,
        proposed_end_at: str,
        proposed_status: str,
        existing: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Check a proposed meeting time against known commitments for a conflict.

        Timestamps are ISO 8601 with a UTC offset; ``proposed_status`` and each
        row's ``status`` in ``existing`` are one of confirmed/tentative/desired/
        cancelled. ``existing`` rows come from commitments already surfaced in
        this conversation (e.g. via search_mail/read_mail), not a live provider
        fetch.
        """
        return await tool_check_calendar_conflict(
            ctx.deps,
            proposed_commitment_id,
            proposed_start_at,
            proposed_end_at,
            proposed_status,
            existing,
        )

    @agent.tool
    async def dispatch_writeback(
        ctx: RunContext[NoemaAgentDeps],
        action: str,
        account: str,
        target_path: str,
        content: str,
    ) -> dict[str, Any]:
        """Dispatch an opt-in, audit-logged writeback to the self-hosted runner."""
        return await tool_dispatch_writeback(
            ctx.deps, action, account, target_path, content
        )

    return agent, _closer


async def run_noema_agent(
    session: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
    prompt: str,
    writeback_enabled: bool = False,
    dispatcher: RunnerDispatcher | None = None,
) -> NoemaAgentResult:
    """Run the Noema general agent, degrading gracefully when unavailable.

    This is the entrypoint referenced by ``registered_agents.json``.
    """
    gateway = await resolve_orchestrator_gateway(
        session, user_id=user_id, organization_id=organization_id
    )
    if gateway is None:
        return NoemaAgentResult(
            status="unavailable",
            notice=(
                "The contextual-orchestrator gateway is not configured for "
                "this workspace."
            ),
            error_code="orchestrator_gateway_unavailable",
        )

    agent, closer = await build_noema_agent(gateway)
    if agent is None:
        return NoemaAgentResult(
            status="unavailable",
            notice="The pydantic-ai runtime is not installed; agent is disabled.",
            provider_name=gateway.model_alias,
            error_code="pydantic_ai_unavailable",
        )

    deps = NoemaAgentDeps(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        writeback_enabled=writeback_enabled,
        dispatcher=dispatcher,
    )
    try:
        result = await agent.run(prompt, deps=deps)
        return NoemaAgentResult(
            status="ok",
            output=str(getattr(result, "output", "")),
            provider_name=gateway.model_alias,
            tool_calls=tuple(deps.tool_calls),
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, never propagate
        logger.info("Noema agent run did not complete: %s", exc)
        return NoemaAgentResult(
            status="error",
            notice="The agent run could not be completed.",
            provider_name=gateway.model_alias,
            tool_calls=tuple(deps.tool_calls),
            error_code="noema_agent_run_failed",
        )
    finally:
        await closer()
