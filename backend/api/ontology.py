import email.utils as email_utils

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import List

from db.session import get_db
from db.models import Email, SenderRelationship
from api.auth import get_auth_context, AuthContext
from services.ontology_service import RelationshipData, ontology_service
from services.text_safety import strip_html_markup
from services.threading_service import normalize_message_id

router = APIRouter(prefix="/api/ontology", tags=["ontology"])
SOURCE_IDENTIFIER_PATTERN = r"^[\w\.\-\+@_<>]+$"


class RelationshipResponse(BaseModel):
    sender_email: str
    parent_sender_email: str | None = None
    source_message_id: str | None = None
    source_thread_id: str | None = None
    relationship_type: str
    confidence_score: float
    next_action: str
    action_reason: str


class RelationshipCreate(BaseModel):
    sender_email: str
    parent_sender_email: str | None = None
    source_message_id: str | None = Field(
        default=None, max_length=512, pattern=SOURCE_IDENTIFIER_PATTERN
    )
    source_thread_id: str | None = Field(
        default=None, max_length=512, pattern=SOURCE_IDENTIFIER_PATTERN
    )
    relationship_type: str
    confidence_score: float = 1.0


class RelationshipCaptureRequest(BaseModel):
    source_message_id: str = Field(
        min_length=1, max_length=512, pattern=SOURCE_IDENTIFIER_PATTERN
    )


def _canonical_thread_id(email_row: Email) -> str:
    return (
        normalize_message_id(email_row.thread_id)
        or normalize_message_id(email_row.message_id)
        or email_row.message_id
    )


def _relationship_sender_label(raw_sender: str | None) -> str:
    display_name, parsed_address = email_utils.parseaddr(raw_sender or "")
    candidate = parsed_address or display_name or raw_sender or "unknown sender"
    cleaned = strip_html_markup(candidate.replace("\x00", ""))
    return " ".join(cleaned.split())[:320] or "unknown sender"


def _relationship_user_email(auth_ctx: AuthContext) -> str:
    return (
        auth_ctx.user_id
        if "@" in auth_ctx.user_id
        else f"{auth_ctx.user_id}@local.naruon"
    )


@router.get("/relationships", response_model=List[RelationshipResponse])
async def get_relationships(
    source_message_id: str | None = Query(
        default=None, max_length=512, pattern=SOURCE_IDENTIFIER_PATTERN
    ),
    source_thread_id: str | None = Query(
        default=None, max_length=512, pattern=SOURCE_IDENTIFIER_PATTERN
    ),
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    organization_filter = (
        SenderRelationship.organization_id == auth_ctx.organization_id
        if auth_ctx.organization_id is not None
        else SenderRelationship.organization_id.is_(None)
    )
    filters = [SenderRelationship.user_id == auth_ctx.user_id, organization_filter]
    if source_message_id is not None:
        filters.append(SenderRelationship.source_message_id == source_message_id)
    if source_thread_id is not None:
        filters.append(SenderRelationship.source_thread_id == source_thread_id)

    stmt = (
        select(SenderRelationship)
        .where(*filters)
        .order_by(
            SenderRelationship.confidence_score.desc(),
            SenderRelationship.updated_at.desc(),
        )
    )
    result = await db.execute(stmt)
    rels = result.scalars().all()
    return [
        RelationshipResponse(
            sender_email=r.sender_email,
            parent_sender_email=r.parent_sender_email,
            source_message_id=r.source_message_id,
            source_thread_id=r.source_thread_id,
            relationship_type=r.relationship_type,
            confidence_score=r.confidence_score,
            **ontology_service.next_action_for_relationship(r.relationship_type),
        )
        for r in rels
    ]


@router.post("/relationships", response_model=RelationshipResponse)
async def create_relationship(
    req: RelationshipCreate,
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    organization_filter = (
        SenderRelationship.organization_id == auth_ctx.organization_id
        if auth_ctx.organization_id is not None
        else SenderRelationship.organization_id.is_(None)
    )
    stmt = select(SenderRelationship).where(
        SenderRelationship.user_id == auth_ctx.user_id,
        organization_filter,
        SenderRelationship.sender_email == req.sender_email,
        SenderRelationship.source_message_id == req.source_message_id,
        SenderRelationship.source_thread_id == req.source_thread_id,
    )
    result = await db.execute(stmt)
    rel = result.scalars().first()

    if rel:
        rel.relationship_type = req.relationship_type
        rel.confidence_score = req.confidence_score
        if "parent_sender_email" in req.model_fields_set:
            rel.parent_sender_email = req.parent_sender_email
        rel.source_message_id = req.source_message_id
        rel.source_thread_id = req.source_thread_id
    else:
        rel = SenderRelationship(
            user_id=auth_ctx.user_id,
            organization_id=auth_ctx.organization_id,
            sender_email=req.sender_email,
            parent_sender_email=req.parent_sender_email,
            source_message_id=req.source_message_id,
            source_thread_id=req.source_thread_id,
            relationship_type=req.relationship_type,
            confidence_score=req.confidence_score,
        )
        db.add(rel)

    await db.commit()
    await db.refresh(rel)

    return RelationshipResponse(
        sender_email=rel.sender_email,
        parent_sender_email=rel.parent_sender_email,
        source_message_id=rel.source_message_id,
        source_thread_id=rel.source_thread_id,
        relationship_type=rel.relationship_type,
        confidence_score=rel.confidence_score,
        **ontology_service.next_action_for_relationship(rel.relationship_type),
    )


@router.post("/relationships/capture-source", response_model=RelationshipResponse)
async def capture_relationship_from_source(
    req: RelationshipCaptureRequest,
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Email).where(
            *Email.owner_filters(
                auth_ctx.user_id, auth_ctx.organization_id, auth_ctx.workspace_id
            ),
            Email.message_id == req.source_message_id,
        )
    )
    email_row = result.scalar_one_or_none()
    if email_row is None:
        raise HTTPException(status_code=404, detail="Source email not found")

    source_thread_id = _canonical_thread_id(email_row)
    sender_email = _relationship_sender_label(email_row.sender)
    analysis = await ontology_service.save_relationship(
        db,
        data=RelationshipData(
            user_email=_relationship_user_email(auth_ctx),
            sender_email=sender_email,
            email_content=email_row.body or "",
            user_id=auth_ctx.user_id,
            organization_id=auth_ctx.organization_id,
            source_message_id=email_row.message_id,
            source_thread_id=source_thread_id,
        ),
    )
    await db.commit()

    return RelationshipResponse(
        sender_email=sender_email,
        parent_sender_email=None,
        source_message_id=email_row.message_id,
        source_thread_id=source_thread_id,
        relationship_type=analysis["type"],
        confidence_score=analysis["confidence"],
        next_action=analysis["next_action"],
        action_reason=analysis["action_reason"],
    )
