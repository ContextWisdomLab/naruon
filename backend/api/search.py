"""Context Search API — language-agnostic hybrid retrieval (G6).

Two channels per query, fused per candidate email:

- lexical: pg_trgm character-trigram word similarity over the four KG
  search surfaces (email subject+body, attachment content, content
  segments, project-graph objects) — no per-language tokenizer, no
  ``to_tsvector`` configuration;
- dense: pgvector cosine over the stored multilingual embeddings
  (emails + attachments today).

Fusion defaults to a convex combination of theoretically min-max
normalized scores (TM2C2; Bruch, Gai & Ingber 2023) with RRF
(Cormack, Clarke & Büttcher 2009) available as the non-parametric
alternative. See docs/engineering/language-agnostic-hybrid-retrieval.md.
"""

from fastapi import APIRouter, Depends, HTTPException
import dataclasses
import datetime
import logging
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Select, func, select
from core.config import settings
from db.session import get_db, get_readonly_db
from db.models import Email
from services.embedding import (
    STORAGE_EMBEDDING_DIMENSION,
    fit_embedding_vector,
    generate_embeddings,
)
from api.auth import AuthContext, get_auth_context
from services.exceptions import EmbeddingGenerationError
from services.hybrid_retrieval import (
    FusionSettings,
    fuse_channel_scores,
    normalize_search_text,
)
from services.hybrid_retrieval.retrieval_channels import (
    DENSE_ATTACHMENT_CHANNEL,
    DENSE_EMAIL_CHANNEL,
    LEXICAL_ATTACHMENT_CHANNEL,
    LEXICAL_CONTENT_SEGMENT_CHANNEL,
    LEXICAL_EMAIL_CHANNEL,
    LEXICAL_PROJECT_OBJECT_CHANNEL,
    build_dense_attachment_statement,
    build_dense_email_statement,
    build_lexical_attachment_statement,
    build_lexical_content_segment_statement,
    build_lexical_email_statement,
    build_lexical_project_object_statement,
)
from services.llm_provider_selection import resolve_runtime_llm_provider
from services.rag_service import GroundedAnswer, answer_from_emails

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
SEARCH_VECTOR_DIMENSIONS = STORAGE_EMBEDDING_DIMENSION
_SNIPPET_CHARACTER_LIMIT = 200


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)


class SearchResultItem(BaseModel):
    id: int
    source_message_id: str | None = None
    subject: str | None
    sender: str
    date: datetime.datetime
    snippet: str
    thread_id: str | None = None
    reply_count: int = 1
    score: float
    result_kind: str | None = None
    evidence_kinds: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


class AnswerRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=10)


class AnswerCitation(BaseModel):
    email_id: int
    subject: str | None = None
    sender: str | None = None
    snippet: str = ""


class AnswerResponse(BaseModel):
    answer: str | None
    citations: list[AnswerCitation]
    provenance: str | None = None


def thread_group_key():
    normalized_thread_id = func.nullif(
        func.btrim(func.btrim(Email.thread_id), "<>"), ""
    )
    normalized_message_id = func.nullif(
        func.btrim(func.btrim(Email.message_id), "<>"), ""
    )
    return func.coalesce(normalized_thread_id, normalized_message_id)


def build_reply_counts_stmt(
    thread_keys: list[str],
    user_id: str,
    organization_id: str | None,
    workspace_id: str,
) -> Select:
    group_key = thread_group_key()
    return (
        select(
            group_key.label("thread_key"),
            func.count(Email.id).label("reply_count"),
        )
        .select_from(Email)
        .where(*Email.owner_filters(user_id, organization_id, workspace_id))
        .where(group_key.in_(thread_keys))
        .group_by(group_key)
    )


def resolve_fusion_settings() -> FusionSettings:
    return FusionSettings(
        strategy_name=settings.SEARCH_FUSION_STRATEGY,
        semantic_weight_alpha=settings.SEARCH_FUSION_SEMANTIC_WEIGHT,
        rank_constant_eta=settings.SEARCH_RRF_RANK_CONSTANT,
    )


@dataclasses.dataclass
class EmailCandidateEvidence:
    """Accumulated cross-channel evidence for one candidate email."""

    email_id: int
    source_message_id: str | None
    subject: str | None
    sender: str
    date: datetime.datetime
    thread_key: str | None
    best_word_similarity: float | None = None
    best_cosine_distance: float | None = None
    channel_ranks: dict[str, int] = dataclasses.field(default_factory=dict)
    evidence_kinds: set[str] = dataclasses.field(default_factory=set)
    primary_result_kind: str | None = None
    primary_matched_text: str = ""
    _primary_row_score: float = -1.0

    def observe_row(
        self,
        *,
        channel_name: str,
        one_based_rank: int,
        result_kind: str,
        matched_text: str | None,
        word_similarity_score: float | None,
        cosine_distance: float | None,
        fusion_settings: FusionSettings,
    ) -> None:
        existing_rank = self.channel_ranks.get(channel_name)
        if existing_rank is None or one_based_rank < existing_rank:
            self.channel_ranks[channel_name] = one_based_rank
        if word_similarity_score is not None and (
            self.best_word_similarity is None
            or word_similarity_score > self.best_word_similarity
        ):
            self.best_word_similarity = word_similarity_score
        if cosine_distance is not None and (
            self.best_cosine_distance is None
            or cosine_distance < self.best_cosine_distance
        ):
            self.best_cosine_distance = cosine_distance
        self.evidence_kinds.add(result_kind)

        row_score = fuse_channel_scores(
            word_similarity_score=word_similarity_score,
            cosine_distance=cosine_distance,
            channel_ranks={channel_name: one_based_rank},
            settings=fusion_settings,
        )
        if row_score > self._primary_row_score:
            self._primary_row_score = row_score
            self.primary_result_kind = result_kind
            self.primary_matched_text = matched_text or ""

    def fused_score(self, fusion_settings: FusionSettings) -> float:
        return fuse_channel_scores(
            word_similarity_score=self.best_word_similarity,
            cosine_distance=self.best_cosine_distance,
            channel_ranks=self.channel_ranks,
            settings=fusion_settings,
        )


def merge_candidate_rows(
    channel_rows: list[tuple[str, list]],
    fusion_settings: FusionSettings,
) -> dict[int, EmailCandidateEvidence]:
    """Merge per-channel candidate rows into per-email evidence.

    ``channel_rows`` pairs a channel name with that channel's rows in
    channel rank order. Rows must expose the uniform candidate columns
    built by ``services.hybrid_retrieval.retrieval_channels``.
    """
    candidates: dict[int, EmailCandidateEvidence] = {}
    for channel_name, rows in channel_rows:
        for zero_based_position, row in enumerate(rows):
            email_id = row.email_id
            evidence = candidates.get(email_id)
            if evidence is None:
                evidence = EmailCandidateEvidence(
                    email_id=email_id,
                    source_message_id=row.source_message_id,
                    subject=row.subject,
                    sender=row.sender,
                    date=row.date,
                    thread_key=row.thread_key,
                )
                candidates[email_id] = evidence
            evidence.observe_row(
                channel_name=channel_name,
                one_based_rank=zero_based_position + 1,
                result_kind=row.result_kind,
                matched_text=row.matched_text,
                word_similarity_score=getattr(row, "word_similarity_score", None),
                cosine_distance=getattr(row, "cosine_distance", None),
                fusion_settings=fusion_settings,
            )
    return candidates


def build_search_result_items(
    candidates: dict[int, EmailCandidateEvidence],
    fusion_settings: FusionSettings,
    limit: int,
    reply_counts_by_thread_key: dict[str, int],
) -> list[SearchResultItem]:
    scored_candidates = sorted(
        (
            (candidate.fused_score(fusion_settings), candidate)
            for candidate in candidates.values()
        ),
        key=lambda scored: (-scored[0], scored[1].email_id),
    )
    search_results: list[SearchResultItem] = []
    for fused_score, candidate in scored_candidates:
        if fused_score < settings.SEARCH_MINIMUM_FUSED_SCORE:
            continue
        snippet_source = candidate.primary_matched_text or ""
        snippet = (
            snippet_source[:_SNIPPET_CHARACTER_LIMIT] + "..."
            if len(snippet_source) > _SNIPPET_CHARACTER_LIMIT
            else snippet_source
        )
        search_results.append(
            SearchResultItem(
                id=candidate.email_id,
                source_message_id=candidate.source_message_id,
                subject=candidate.subject,
                sender=candidate.sender,
                date=candidate.date,
                snippet=snippet,
                thread_id=candidate.thread_key,
                reply_count=reply_counts_by_thread_key.get(
                    candidate.thread_key or "", 1
                ),
                score=fused_score,
                result_kind=candidate.primary_result_kind,
                evidence_kinds=sorted(candidate.evidence_kinds),
            )
        )
        if len(search_results) >= limit:
            break
    return search_results


async def _resolve_query_embedding(
    config_db: AsyncSession,
    normalized_query: str,
    user_id: str,
    organization_id: str | None,
) -> list[float] | None:
    """Best-effort query embedding; lexical search works without it."""
    runtime_provider = await resolve_runtime_llm_provider(
        config_db,
        user_id=user_id,
        organization_id=organization_id,
    )
    if runtime_provider is None:
        logger.info("No LLM provider configured; hybrid search running lexical-only")
        return None
    try:
        embeddings = await generate_embeddings(
            [normalized_query],
            runtime_provider.api_key,
            base_url=runtime_provider.base_url,
            model=runtime_provider.embedding_model,
        )
    except EmbeddingGenerationError:
        logger.info("Search embedding unavailable; using lexical search only")
        return None
    if not embeddings:
        return None
    return fit_embedding_vector(embeddings[0], SEARCH_VECTOR_DIMENSIONS)


def _build_channel_statements(
    normalized_query: str,
    query_embedding: list[float] | None,
    owner_filters,
) -> list[tuple[str, Select]]:
    candidate_limit = settings.SEARCH_CHANNEL_CANDIDATE_LIMIT
    channel_statements: list[tuple[str, Select]] = [
        (
            LEXICAL_EMAIL_CHANNEL,
            build_lexical_email_statement(
                normalized_query, owner_filters, candidate_limit
            ),
        ),
        (
            LEXICAL_ATTACHMENT_CHANNEL,
            build_lexical_attachment_statement(
                normalized_query, owner_filters, candidate_limit
            ),
        ),
        (
            LEXICAL_CONTENT_SEGMENT_CHANNEL,
            build_lexical_content_segment_statement(
                normalized_query, owner_filters, candidate_limit
            ),
        ),
        (
            LEXICAL_PROJECT_OBJECT_CHANNEL,
            build_lexical_project_object_statement(
                normalized_query, owner_filters, candidate_limit
            ),
        ),
    ]
    if query_embedding is not None:
        channel_statements.extend(
            [
                (
                    DENSE_EMAIL_CHANNEL,
                    build_dense_email_statement(
                        query_embedding, owner_filters, candidate_limit
                    ),
                ),
                (
                    DENSE_ATTACHMENT_CHANNEL,
                    build_dense_attachment_statement(
                        query_embedding, owner_filters, candidate_limit
                    ),
                ),
            ]
        )
    return channel_statements


async def _merge_search_candidates(
    search_db: AsyncSession,
    channel_statements: list[tuple[str, Select]],
    fusion_settings: FusionSettings,
) -> dict[int, EmailCandidateEvidence]:
    channel_rows: list[tuple[str, list]] = []
    for channel_name, channel_statement in channel_statements:
        channel_result = await search_db.execute(channel_statement)
        channel_rows.append((channel_name, list(channel_result.all())))
    return merge_candidate_rows(channel_rows, fusion_settings)


def _answer_context_emails(
    candidates: dict[int, EmailCandidateEvidence],
    fusion_settings: FusionSettings,
    limit: int,
) -> list[dict]:
    scored_candidates = sorted(
        (
            (candidate.fused_score(fusion_settings), candidate)
            for candidate in candidates.values()
        ),
        key=lambda scored: (-scored[0], scored[1].email_id),
    )
    return [
        {
            "id": candidate.email_id,
            "subject": candidate.subject,
            "sender": candidate.sender,
            "date": candidate.date,
            "content": candidate.primary_matched_text,
        }
        for fused_score, candidate in scored_candidates
        if fused_score >= settings.SEARCH_MINIMUM_FUSED_SCORE
    ][:limit]


@router.post("/search", response_model=SearchResponse)
async def hybrid_search(
    request: SearchRequest,
    user_id: str | None = None,
    config_db: AsyncSession = Depends(get_db),
    search_db: AsyncSession = Depends(get_readonly_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    if user_id and user_id != auth_context.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    target_user_id = user_id or auth_context.user_id

    normalized_query = normalize_search_text(request.query)
    if not normalized_query:
        return SearchResponse(results=[])

    try:
        fusion_settings = resolve_fusion_settings()
        query_embedding = await _resolve_query_embedding(
            config_db,
            normalized_query,
            target_user_id,
            auth_context.organization_id,
        )

        owner_filters = Email.owner_filters(
            target_user_id, auth_context.organization_id, auth_context.workspace_id
        )
        channel_statements = _build_channel_statements(
            normalized_query, query_embedding, owner_filters
        )
        candidates = await _merge_search_candidates(
            search_db, channel_statements, fusion_settings
        )

        reply_counts_by_thread_key: dict[str, int] = {}
        candidate_thread_keys = sorted(
            {
                candidate.thread_key
                for candidate in candidates.values()
                if candidate.thread_key
            }
        )
        if candidate_thread_keys:
            reply_counts_result = await search_db.execute(
                build_reply_counts_stmt(
                    candidate_thread_keys,
                    target_user_id,
                    auth_context.organization_id,
                    auth_context.workspace_id,
                )
            )
            reply_counts_by_thread_key = {
                row.thread_key: row.reply_count for row in reply_counts_result.all()
            }

        search_results = build_search_result_items(
            candidates,
            fusion_settings,
            request.limit,
            reply_counts_by_thread_key,
        )
        return SearchResponse(results=search_results)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Search failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed") from e


@router.post("/search/answer", response_model=AnswerResponse)
async def grounded_answer(
    request: AnswerRequest,
    config_db: AsyncSession = Depends(get_db),
    search_db: AsyncSession = Depends(get_readonly_db),
    auth_context: AuthContext = Depends(get_auth_context),
):
    """Answer from owner-scoped retrieved emails with enforced citations."""
    normalized_query = normalize_search_text(request.query)
    if not normalized_query:
        return AnswerResponse(answer=None, citations=[])

    try:
        runtime_provider = await resolve_runtime_llm_provider(
            config_db,
            user_id=auth_context.user_id,
            organization_id=auth_context.organization_id,
        )
        if runtime_provider is None:
            raise HTTPException(status_code=400, detail="OpenAI API key not configured")

        query_embedding = None
        try:
            embeddings = await generate_embeddings(
                [normalized_query],
                runtime_provider.api_key,
                base_url=runtime_provider.base_url,
                model=runtime_provider.embedding_model,
            )
            query_embedding = (
                fit_embedding_vector(embeddings[0], SEARCH_VECTOR_DIMENSIONS)
                if embeddings
                else None
            )
        except EmbeddingGenerationError:
            logger.info("Answer embedding unavailable; using lexical search only")

        fusion_settings = resolve_fusion_settings()
        owner_filters = Email.owner_filters(
            auth_context.user_id,
            auth_context.organization_id,
            auth_context.workspace_id,
        )
        channel_statements = _build_channel_statements(
            normalized_query, query_embedding, owner_filters
        )
        candidates = await _merge_search_candidates(
            search_db, channel_statements, fusion_settings
        )
        context_emails = _answer_context_emails(
            candidates, fusion_settings, request.limit
        )

        grounded: GroundedAnswer | None = await answer_from_emails(
            normalized_query,
            context_emails,
            api_key=runtime_provider.api_key,
            base_url=runtime_provider.base_url,
            model=runtime_provider.chat_model,
            provider_name=runtime_provider.provider_name,
        )
        if grounded is None:
            return AnswerResponse(answer=None, citations=[])

        by_id = {email["id"]: email for email in context_emails}
        citations = [
            AnswerCitation(
                email_id=email_id,
                subject=by_id[email_id]["subject"],
                sender=by_id[email_id]["sender"],
                snippet=(by_id[email_id]["content"] or "")[:_SNIPPET_CHARACTER_LIMIT],
            )
            for email_id in grounded.cited_email_ids
            if email_id in by_id
        ]
        return AnswerResponse(
            answer=grounded.answer,
            citations=citations,
            provenance=grounded.provenance,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Grounded answer failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Answer failed") from e
