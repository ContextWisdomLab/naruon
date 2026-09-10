from collections import defaultdict
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select
from db.session import get_db
from db.models import Email
from pydantic import BaseModel, EmailStr, Field, field_validator
import datetime
from typing import Literal
from services.email_client import (
    EmailMessageParams,
    SmtpConfig,
    send_email,
    validate_smtp_destination,
)
from services.reply_tracking_service import (
    check_missing_replies,
    configured_email_addresses,
    message_is_from_user,
    message_is_self_sent,
    thread_requires_reply,
)
from services.threading_service import normalize_message_id
from services.email_dedupe_service import (
    EmailDedupeCandidate,
    candidate_message_lookup_values,
    candidate_strong_fingerprint,
    email_strong_fingerprint,
)
from services.email_import_service import (
    EmailImportEmbeddingProvider,
    EmailImportQuotaExceeded,
    MAX_IMPORT_UPLOAD_BYTES,
    MAX_IMPORT_UPLOADS,
    EmailImportItemStatus,
    EmailImportUpload,
    canonical_email_import_upload_filename,
    import_email_uploads,
)
from services.email_send_rate_limiter import (
    EmailSendRateLimitUnavailable,
    enforce_send_email_rate_limit,
)
from services.llm_provider_selection import resolve_runtime_llm_provider
from services.text_safety import strip_html_markup
import logging
from api.auth import AuthContext, get_auth_context
from api.search import thread_group_key as sql_thread_group_key
from services.tenant_config_scope import get_scoped_tenant_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/emails")

def canonical_thread_key(email: Email) -> str:
    return (
        normalize_message_id(email.thread_id)
        or normalize_message_id(email.message_id)
        or email.message_id
    )


def thread_lookup_values(thread_id: str) -> list[str]:
    normalized = normalize_message_id(thread_id) or thread_id
    return list({thread_id, normalized, f"<{normalized}>"})


MailFolder = Literal["inbox", "sent"]


def thread_matches_folder(
    thread_messages: list[Email], user_addresses: set[str], folder: MailFolder
) -> bool:
    if folder == "sent":
        return any(
            message_is_from_user(email_message, user_addresses)
            for email_message in thread_messages
        )
    return True


def _to_dedupe_candidate(
    candidate: "UniqueThreadCandidateRequest",
) -> EmailDedupeCandidate:
    return EmailDedupeCandidate(
        candidate_key=candidate.candidate_key,
        message_id=candidate.message_id,
        sender=candidate.sender,
        recipients=candidate.recipients,
        subject=candidate.subject,
        date=candidate.date,
        body=candidate.body,
    )


def _email_message_lookup_values(email_row: Email) -> set[str]:
    normalized = normalize_message_id(email_row.message_id)
    if not normalized:
        return set()
    return {normalized, f"<{normalized}>"}


def _safe_email_display_text(value: str | None) -> str | None:
    if value is None:
        return None
    return strip_html_markup(str(value).replace("\x00", ""))


def _safe_email_body(value: str | None) -> str:
    return _safe_email_display_text(value) or ""


def _safe_email_snippet(value: str | None) -> str:
    body = _safe_email_body(value)
    return body[:100] + "..." if len(body) > 100 else body


def _email_list_item(
    *,
    email: Email,
    thread_id: str,
    reply_count: int | None,
    is_self_sent: bool,
    requires_reply: bool,
) -> "EmailListItem":
    return EmailListItem(
        id=email.id,
        subject=_safe_email_display_text(email.subject),
        sender=_safe_email_body(email.sender),
        reply_to=_safe_email_display_text(email.reply_to),
        date=email.date,
        snippet=_safe_email_snippet(email.body),
        thread_id=thread_id,
        reply_count=reply_count,
        is_self_sent=is_self_sent,
        # default column value is applied at flush; coalesce unflushed None -> read
        is_read=email.is_read if email.is_read is not None else True,
        requires_reply=requires_reply,
    )


def _email_detail_response(email: Email) -> "EmailDetailResponse":
    return EmailDetailResponse(
        id=email.id,
        message_id=email.message_id,
        sender=_safe_email_body(email.sender),
        reply_to=_safe_email_display_text(email.reply_to),
        recipients=_safe_email_display_text(email.recipients),
        subject=_safe_email_display_text(email.subject),
        date=email.date,
        body=_safe_email_body(email.body),
        thread_id=canonical_thread_key(email),
        in_reply_to=email.in_reply_to,
        references=email.references,
    )


class EmailListItem(BaseModel):
    id: int
    thread_id: str | None = None
    subject: str | None
    sender: str
    reply_to: str | None = None
    date: datetime.datetime
    snippet: str
    reply_count: int | None = None
    has_draft: bool = False
    is_self_sent: bool = False
    is_read: bool = True
    requires_reply: bool = False
    schedule_conflict: bool = False


class EmailDetailResponse(BaseModel):
    id: int
    message_id: str
    thread_id: str | None = None
    sender: str
    reply_to: str | None = None
    recipients: str | None
    subject: str | None
    date: datetime.datetime
    body: str
    in_reply_to: str | None = None
    references: str | None = None
    requires_reply: bool = False
    schedule_conflict: bool = False


class UniqueThreadCandidateRequest(BaseModel):
    candidate_key: str = Field(min_length=1, max_length=128)
    message_id: str | None = Field(default=None, max_length=512)
    sender: str | None = Field(default=None, max_length=512)
    recipients: str | None = Field(default=None, max_length=2048)
    subject: str | None = Field(default=None, max_length=1024)
    date: datetime.datetime | None = None
    body: str | None = Field(default=None, max_length=20000)


class UniqueThreadIntentRequest(BaseModel):
    candidates: list[UniqueThreadCandidateRequest] = Field(min_length=1, max_length=20)


class UniqueThreadUpdate(BaseModel):
    candidate_key: str
    canonical_thread_id: str
    dedupe_key: str
    match_reason: Literal["message_id", "fingerprint"]
    existing_message_id: str


class UniqueThreadIntentResponse(BaseModel):
    status: Literal["intent_ready"]
    candidates_checked: int
    duplicates_found: int
    thread_updates: list[UniqueThreadUpdate]
    provenance: Literal["server-authoritative"]
    provider_write_executed: bool
    audit_event: Literal["email.unique_thread_intent.created"]


class EmailFileImportItem(BaseModel):
    filename: str
    status: EmailImportItemStatus
    reason_code: str | None = None
    attachment_count: int = 0


class EmailFileImportResponse(BaseModel):
    status: Literal["completed"]
    imported_count: int
    skipped_count: int
    failed_count: int
    attachment_count: int
    items: list[EmailFileImportItem]
    provenance: Literal["server-authoritative"]
    provider_write_executed: bool
    audit_event: Literal["email.file_import.completed"]


@router.get("", response_model=dict[str, list[EmailListItem]])
async def get_emails(
    limit: int = Query(default=50, ge=1, le=200),
    folder: MailFolder = Query(default="inbox"),
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    tenant_config = await get_scoped_tenant_config(
        db,
        auth_context.user_id,
        auth_context.organization_id,
    )
    user_addresses = configured_email_addresses(tenant_config)
    is_sent_folder = folder == "sent"
    owner_filters = Email.owner_filters(
        auth_context.user_id, auth_context.organization_id
    )

    # Thread winnowing happens in SQL: one newest head row per thread via a
    # window function, so accuracy no longer degrades with mailbox size the
    # way the previous fixed 2000-row in-memory window did. The sent folder
    # filters app-side on parsed sender addresses, so it over-fetches a
    # bounded multiple of the page instead.
    head_candidate_limit = limit * 5 if is_sent_folder else limit
    thread_rank = (
        func.row_number()
        .over(
            partition_by=sql_thread_group_key(),
            order_by=(Email.date.desc(), Email.id.desc()),
        )
        .label("thread_rank")
    )
    ranked_heads = (
        select(Email.id.label("head_id"), thread_rank)
        .where(*owner_filters)
        .subquery("ranked_thread_heads")
    )
    result = await db.execute(
        select(Email)
        .join(ranked_heads, ranked_heads.c.head_id == Email.id)
        .where(ranked_heads.c.thread_rank == 1)
        .order_by(Email.date.desc())
        .limit(head_candidate_limit)
    )
    head_emails = list(result.scalars().all())

    # Defensive app-side dedupe: a no-op on PostgreSQL (SQL already returns
    # one head per thread) but keeps behavior exact if a backend ever returns
    # duplicates for the window query.
    grouped = {}
    for email in head_emails:
        group_key = canonical_thread_key(email)
        if group_key not in grouped:
            grouped[group_key] = email

    reply_counts = defaultdict(int)
    thread_messages = defaultdict(list)
    has_sent_message = set()

    if grouped:
        thread_lookup: set[str] = set()
        for group_key in grouped:
            thread_lookup.update(thread_lookup_values(group_key))
        messages_result = await db.execute(
            select(Email)
            .where(
                *owner_filters,
                or_(
                    Email.thread_id.in_(thread_lookup),
                    Email.message_id.in_(thread_lookup),
                ),
            )
            .order_by(Email.date.desc())
        )
        for email in messages_result.scalars().all():
            group_key = canonical_thread_key(email)
            if group_key not in grouped:
                continue
            thread_messages[group_key].append(email)
            reply_counts[group_key] += 1
            if is_sent_folder and group_key not in has_sent_message:
                if message_is_from_user(email, user_addresses):
                    has_sent_message.add(group_key)

    if is_sent_folder:
        visible_groups = [
            email
            for group_key, email in grouped.items()
            if group_key in has_sent_message
        ]
    else:
        visible_groups = list(grouped.values())
    sorted_groups = visible_groups[:limit]

    items = []
    for email in sorted_groups:
        group_key = canonical_thread_key(email)
        items.append(
            _email_list_item(
                email=email,
                thread_id=group_key,
                reply_count=reply_counts[group_key],
                is_self_sent=message_is_self_sent(email, user_addresses),
                requires_reply=thread_requires_reply(
                    list(reversed(thread_messages[group_key])), user_addresses
                ),
            )
        )
    return {"emails": items}


@router.get("/pending-replies", response_model=dict[str, list[EmailListItem]])
async def get_pending_replies(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    pending_emails = await check_missing_replies(
        db, auth_context.user_id, auth_context.organization_id
    )
    items = []
    for email in pending_emails[:limit]:
        items.append(
            _email_list_item(
                email=email,
                thread_id=canonical_thread_key(email),
                reply_count=None,
                is_self_sent=False,
                requires_reply=True,
            )
        )
    return {"emails": items}


def _extract_candidate_lookups(
    candidates: list[EmailDedupeCandidate],
) -> tuple[set[str], set[str], dict[str, set[str]], dict[str, str | None]]:
    message_lookup_values: set[str] = set()
    fingerprint_values: set[str] = set()

    # ⚡ Bolt: Cache expensive lookup generation and SHA-256 fingerprinting
    # Mapping by candidate_key to prevent redundant processing in downstream dedupe logic
    candidate_lookups: dict[str, set[str]] = {}
    candidate_fingerprints: dict[str, str | None] = {}

    for candidate in candidates:
        lookups = candidate_message_lookup_values(candidate)
        candidate_lookups[candidate.candidate_key] = lookups
        message_lookup_values.update(lookups)

        candidate_fingerprint = candidate_strong_fingerprint(candidate)
        candidate_fingerprints[candidate.candidate_key] = candidate_fingerprint
        if candidate_fingerprint:
            fingerprint_values.add(candidate_fingerprint)

    return (
        message_lookup_values,
        fingerprint_values,
        candidate_lookups,
        candidate_fingerprints,
    )


async def _fetch_existing_emails_for_candidates(
    db: AsyncSession,
    auth_context: AuthContext,
    message_lookup_values: set[str],
    fingerprint_values: set[str],
) -> list[Email]:
    predicates = []
    if message_lookup_values:
        predicates.append(Email.message_id.in_(message_lookup_values))
    if fingerprint_values:
        predicates.append(Email.fingerprint.in_(fingerprint_values))

    if not predicates:
        return []

    result = await db.execute(
        select(Email).where(
            *Email.owner_filters(auth_context.user_id, auth_context.organization_id),
            or_(*predicates),
        )
    )
    return list(result.scalars().all())


def _build_email_lookup_dicts(
    existing_emails: list[Email],
) -> tuple[dict[str, Email], dict[str, Email]]:
    by_message_id: dict[str, Email] = {}
    by_fingerprint: dict[str, Email] = {}
    for email_row in existing_emails:
        msg_id = email_row.message_id
        if msg_id:
            normalized = normalize_message_id(msg_id)
            if normalized:
                if normalized not in by_message_id:
                    by_message_id[normalized] = email_row
                bracketed = f"<{normalized}>"
                if bracketed not in by_message_id:
                    by_message_id[bracketed] = email_row
        row_fingerprint = email_strong_fingerprint(email_row)
        if row_fingerprint:
            if row_fingerprint not in by_fingerprint:
                by_fingerprint[row_fingerprint] = email_row
        if email_row.fingerprint:
            if email_row.fingerprint not in by_fingerprint:
                by_fingerprint[email_row.fingerprint] = email_row
    return by_message_id, by_fingerprint


def _find_matches_for_candidates(
    candidates: list[EmailDedupeCandidate],
    by_message_id: dict[str, Email],
    by_fingerprint: dict[str, Email],
    candidate_lookups: dict[str, set[str]],
    candidate_fingerprints: dict[str, str | None],
) -> list[UniqueThreadUpdate]:
    updates: list[UniqueThreadUpdate] = []
    for candidate in candidates:
        matched_email: Email | None = None
        match_reason: Literal["message_id", "fingerprint"] | None = None
        dedupe_key: str | None = None

        # ⚡ Bolt: Fetch explicitly and iterate only if found.
        # This avoids continuously instantiating an empty set() via .get(..., set())
        # inside a tight loop which adds severe memory and garbage collection overhead.
        lookups = candidate_lookups.get(candidate.candidate_key)
        if lookups:
            for lookup_value in lookups:
                if lookup_value in by_message_id:
                    matched_email = by_message_id[lookup_value]
                    match_reason = "message_id"
                    dedupe_key = normalize_message_id(lookup_value) or lookup_value
                    break

        if matched_email is None:
            candidate_fingerprint = candidate_fingerprints.get(candidate.candidate_key)
            if candidate_fingerprint and candidate_fingerprint in by_fingerprint:
                matched_email = by_fingerprint[candidate_fingerprint]
                match_reason = "fingerprint"
                dedupe_key = f"sha256:{candidate_fingerprint[:16]}"

        if matched_email is not None and match_reason and dedupe_key:
            updates.append(
                UniqueThreadUpdate(
                    candidate_key=candidate.candidate_key,
                    canonical_thread_id=canonical_thread_key(matched_email),
                    dedupe_key=dedupe_key,
                    match_reason=match_reason,
                    existing_message_id=(
                        normalize_message_id(matched_email.message_id)
                        or matched_email.message_id
                    ),
                )
            )
    return updates


@router.post("/unique-thread-intent", response_model=UniqueThreadIntentResponse)
async def create_unique_thread_intent(
    request: UniqueThreadIntentRequest,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    candidates = [_to_dedupe_candidate(candidate) for candidate in request.candidates]
    (
        message_lookup_values,
        fingerprint_values,
        candidate_lookups,
        candidate_fingerprints,
    ) = _extract_candidate_lookups(candidates)
    existing_emails = await _fetch_existing_emails_for_candidates(
        db, auth_context, message_lookup_values, fingerprint_values
    )
    by_message_id, by_fingerprint = _build_email_lookup_dicts(existing_emails)
    updates = _find_matches_for_candidates(
        candidates,
        by_message_id,
        by_fingerprint,
        candidate_lookups,
        candidate_fingerprints,
    )

    return UniqueThreadIntentResponse(
        status="intent_ready",
        candidates_checked=len(candidates),
        duplicates_found=len(updates),
        thread_updates=updates,
        provenance="server-authoritative",
        provider_write_executed=False,
        audit_event="email.unique_thread_intent.created",
    )


@router.post("/import-files", response_model=EmailFileImportResponse)
async def import_email_files(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    if auth_context.organization_id is None:
        raise HTTPException(status_code=403, detail="organization_required")
    if len(files) > MAX_IMPORT_UPLOADS:
        raise HTTPException(status_code=422, detail="too_many_files")

    uploads: list[EmailImportUpload] = []
    for upload in files:
        canonical_filename = canonical_email_import_upload_filename(upload.filename)
        if canonical_filename is None:
            raise HTTPException(status_code=400, detail="invalid_file_type")

        content = await upload.read(MAX_IMPORT_UPLOAD_BYTES + 1)
        if len(content) > MAX_IMPORT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file_too_large")
        uploads.append(
            EmailImportUpload(
                filename=canonical_filename,
                content=content,
            )
        )

    runtime_provider = await resolve_runtime_llm_provider(
        db,
        user_id=auth_context.user_id,
        organization_id=auth_context.organization_id,
    )
    embedding_provider = None
    if runtime_provider is not None:
        embedding_provider = EmailImportEmbeddingProvider(
            api_key=runtime_provider.api_key,
            base_url=runtime_provider.base_url,
            embedding_model=runtime_provider.embedding_model,
        )

    try:
        import_result = await import_email_uploads(
            db,
            uploads=uploads,
            user_id=auth_context.user_id,
            organization_id=auth_context.organization_id,
            embedding_provider=embedding_provider,
        )
    except EmailImportQuotaExceeded as exc:
        raise HTTPException(
            status_code=429, detail="email_import_quota_exceeded"
        ) from exc
    return EmailFileImportResponse(
        status="completed",
        imported_count=import_result.imported_count,
        skipped_count=import_result.skipped_count,
        failed_count=import_result.failed_count,
        attachment_count=import_result.attachment_count,
        items=[
            EmailFileImportItem(
                filename=item.filename,
                status=item.status,
                reason_code=item.reason_code,
                attachment_count=item.attachment_count,
            )
            for item in import_result.items
        ],
        provenance="server-authoritative",
        provider_write_executed=False,
        audit_event="email.file_import.completed",
    )


@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    result = await db.execute(
        select(Email).where(
            Email.id == email_id,
            *Email.owner_filters(auth_context.user_id, auth_context.organization_id),
        )
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return _email_detail_response(email)


@router.get(
    "/thread/{thread_id:path}", response_model=dict[str, list[EmailDetailResponse]]
)
async def get_email_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    lookup_values = thread_lookup_values(thread_id)
    result = await db.execute(
        select(Email)
        .where(
            *Email.owner_filters(auth_context.user_id, auth_context.organization_id),
            or_(
                Email.thread_id.in_(lookup_values), Email.message_id.in_(lookup_values)
            ),
        )
        .order_by(Email.date.asc())
    )
    emails = result.scalars().all()
    if not emails:
        raise HTTPException(status_code=404, detail="Thread not found")

    items = []
    for email in emails:
        items.append(_email_detail_response(email))
    return {"thread": items}


class SendEmailRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., max_length=256, pattern=r"^[^\r\n]*$")
    body: str
    in_reply_to: str | None = None  # O3: email threading support
    references: str | None = None

    @field_validator("to", "subject", "in_reply_to", "references", mode="before")
    @classmethod
    def reject_crlf(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            if chr(10) in v or chr(13) in v:
                raise ValueError("CR/LF injection detected")
        return v


@router.post("/send")
async def send_email_endpoint(
    request: SendEmailRequest,
    db: AsyncSession = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    # Ensure auth context validates the request payload and scopes access
    try:
        tenant_config = await get_scoped_tenant_config(
            db,
            auth_context.user_id,
            auth_context.organization_id,
        )

        if (
            not tenant_config
            or not tenant_config.smtp_server
            or not tenant_config.smtp_port
            or not tenant_config.smtp_username
        ):
            raise HTTPException(status_code=400, detail="SMTP is not configured")

        try:
            smtp_server = tenant_config.smtp_server
            smtp_port = tenant_config.smtp_port
            smtp_username = tenant_config.smtp_username
            smtp_password = tenant_config.smtp_password
            # The production dependency is an AsyncSession. Lightweight unit-test
            # doubles do not own a pooled connection and may omit rollback().
            rollback = getattr(db, "rollback", None)
            if rollback is not None:
                await rollback()
            validate_smtp_destination(smtp_server, smtp_port)
        except Exception as exc:
            if "ENCRYPTION_KEY is required" in str(exc):
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Server encryption key is not configured. "
                        "Contact your workspace administrator."
                    ),
                ) from exc
            if isinstance(exc, ValueError):
                logger.warning(
                    "Email send rejected invalid SMTP configuration",
                    extra={"error_type": type(exc).__name__},
                )
                raise HTTPException(
                    status_code=400, detail="Invalid email configuration"
                ) from exc
            raise

        message_params = EmailMessageParams(
            to_address=request.to,
            subject=request.subject,
            body=request.body,
            in_reply_to=request.in_reply_to,
            references=request.references,
        )
        try:
            rate_limit_decision = await enforce_send_email_rate_limit(auth_context)
        except EmailSendRateLimitUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Email send rate limiter unavailable",
            ) from exc
        if not rate_limit_decision.allowed:
            raise HTTPException(
                status_code=429,
                detail="Email send rate limit exceeded",
            )
        smtp_config = SmtpConfig(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
        )
        send_result = await send_email(
            message_params=message_params,
            smtp_config=smtp_config,
        )
        if send_result.get("status") not in {"sent", "simulated"}:
            raise HTTPException(status_code=500, detail="Failed to send email")
        return send_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An internal error occurred while sending the email"
        )
