from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import get_db
from db.models import Email
from api.auth import AuthContext, get_auth_context
import re

router = APIRouter(prefix="/api/network")


class Node(BaseModel):
    id: str
    label: str


class Edge(BaseModel):
    source: str
    target: str
    weight: int


class GraphResponse(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def extract_emails(text: str | None) -> list[str]:
    if not text:
        return []
    return EMAIL_PATTERN.findall(text)


@router.get("/graph", response_model=GraphResponse)
async def get_network_graph(
    limit: int = Query(default=500, ge=1, le=2000),
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    current_user = auth_context.user_id
    if user_id and user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    target_user_id = user_id or current_user
    result = await db.execute(
        select(Email.sender, Email.recipients)
        .where(
            *Email.owner_filters(
                target_user_id,
                auth_context.organization_id,
                auth_context.workspace_id,
            )
        )
        .limit(limit)
    )
    rows = result.fetchall()

    nodes_set = set()
    edges_dict = {}  # (sender, recipient) -> weight

    nodes_add = nodes_set.add
    edges_get = edges_dict.get
    findall = EMAIL_PATTERN.findall

    for row in rows:
        sender_str = row[0]
        recipients_str = row[1]

        sender_email = None
        if sender_str:
            senders = findall(sender_str.lower())
            if senders:
                sender_email = senders[0]
                nodes_add(sender_email)

        if recipients_str:
            recipients = findall(recipients_str.lower())
            if recipients:
                nodes_set.update(recipients)
                if sender_email:
                    for rec_email in recipients:
                        if sender_email != rec_email:
                            edge_key = (sender_email, rec_email)
                            edges_dict[edge_key] = edges_get(edge_key, 0) + 1

    nodes = [Node(id=email, label=email) for email in nodes_set]
    edges = [
        Edge(source=src, target=tgt, weight=weight)
        for (src, tgt), weight in edges_dict.items()
    ]

    return GraphResponse(nodes=nodes, edges=edges)
