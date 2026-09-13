"""Per-source candidate statements for language-agnostic hybrid search.

Each channel returns a uniform candidate row shape:

    email_id, source_message_id, subject, sender, date, thread_key,
    matched_text, result_kind, word_similarity_score, cosine_distance

Lexical channels rank by pg_trgm word-similarity distance (``<->>``)
over the SQL expression ``search_normalized_text(<document text>)``,
which migration 0010_language_agnostic_search indexes with GiST
trigram indexes. The expressions built here MUST stay textually
identical to the indexed expressions, or PostgreSQL will not use the
indexes. Character trigrams are language-agnostic: no per-language
tokenizer or ``to_tsvector`` configuration is involved (G6).

Dense channels rank by pgvector cosine distance over the stored
multilingual embeddings (email bodies and attachments today; content
segments and project-graph objects gain embeddings with the batch
embedding work routed through contextual-orchestrator).
"""

from sqlalchemy import Select, String, cast, func, literal, select

from db.models import (
    Attachment,
    ContentSegmentRecord,
    Email,
    ProjectGraphObjectRecord,
)

EMAIL_BODY_RESULT_KIND = "email_body"
ATTACHMENT_RESULT_KIND = "attachment_content"
CONTENT_SEGMENT_RESULT_KIND = "content_segment"
PROJECT_GRAPH_OBJECT_RESULT_KIND = "project_graph_object"

LEXICAL_EMAIL_CHANNEL = "lexical_email"
LEXICAL_ATTACHMENT_CHANNEL = "lexical_attachment"
LEXICAL_CONTENT_SEGMENT_CHANNEL = "lexical_content_segment"
LEXICAL_PROJECT_OBJECT_CHANNEL = "lexical_project_object"
DENSE_EMAIL_CHANNEL = "dense_email"
DENSE_ATTACHMENT_CHANNEL = "dense_attachment"

# Correct-by-exception (CP-2): objects the user dismissed must not
# resurface as search evidence. Current status vocabulary is
# {candidate, confirmed}; the exclusion list is defensive.
_EXCLUDED_PROJECT_OBJECT_STATUS_CODES = ("dismissed", "rejected")

# Only a "parsed" attachment's `content` is genuine parsed text. Every other
# status (quarantined content-type mismatch, pdf_dom_recognition_pending
# awaiting the NewsDOM sidecar, reparse_pending/reparse_payload_invalid,
# unsupported_content_type, parse_size_limit_exceeded, ...) stores either a
# base64-encoded raw payload or an empty string -- neither is a legitimate
# search match, and the base64 payload in particular must never surface as
# if it were the attachment's real content.
_SEARCHABLE_ATTACHMENT_PARSE_STATUS = "parsed"


def _thread_key_expression():
    normalized_thread_id = func.nullif(
        func.btrim(func.btrim(Email.thread_id), "<>"), ""
    )
    normalized_message_id = func.nullif(
        func.btrim(func.btrim(Email.message_id), "<>"), ""
    )
    return func.coalesce(normalized_thread_id, normalized_message_id)


def email_search_document_expression():
    """Subject + body as one searchable document (index expression)."""
    return func.search_normalized_text(
        func.coalesce(Email.subject, "") + " " + Email.body
    )


def attachment_search_document_expression():
    return func.search_normalized_text(Attachment.content)


def content_segment_search_document_expression():
    return func.search_normalized_text(ContentSegmentRecord.safe_text_content)


def project_object_search_document_expression():
    return func.search_normalized_text(
        ProjectGraphObjectRecord.title + " " + ProjectGraphObjectRecord.summary
    )


def _candidate_columns(matched_text_column, result_kind: str):
    return (
        Email.id.label("email_id"),
        Email.message_id.label("source_message_id"),
        Email.subject.label("subject"),
        Email.sender.label("sender"),
        Email.date.label("date"),
        _thread_key_expression().label("thread_key"),
        matched_text_column.label("matched_text"),
        cast(literal(result_kind), String).label("result_kind"),
    )


def _lexical_scored_statement(
    *,
    matched_text_column,
    result_kind: str,
    document_expression,
    normalized_query: str,
    owner_filters,
    candidate_limit: int,
) -> Select:
    # The query goes through the same SQL normalization function as the
    # indexed document expressions so both sides fold identically.
    normalized_query_expression = func.search_normalized_text(normalized_query)
    word_similarity_score = func.word_similarity(
        normalized_query_expression, document_expression
    )
    # ``document <->> query`` = 1 - word_similarity(query, document);
    # kNN-ordering form served by the GiST trigram indexes.
    lexical_distance = document_expression.op("<->>")(
        normalized_query_expression
    )
    return (
        select(
            *_candidate_columns(matched_text_column, result_kind),
            word_similarity_score.label("word_similarity_score"),
        )
        .where(*owner_filters)
        .order_by(lexical_distance)
        .limit(candidate_limit)
    )


def build_lexical_email_statement(
    normalized_query: str, owner_filters, candidate_limit: int
) -> Select:
    return _lexical_scored_statement(
        matched_text_column=Email.body,
        result_kind=EMAIL_BODY_RESULT_KIND,
        document_expression=email_search_document_expression(),
        normalized_query=normalized_query,
        owner_filters=owner_filters,
        candidate_limit=candidate_limit,
    )


def build_lexical_attachment_statement(
    normalized_query: str, owner_filters, candidate_limit: int
) -> Select:
    statement = _lexical_scored_statement(
        matched_text_column=Attachment.content,
        result_kind=ATTACHMENT_RESULT_KIND,
        document_expression=attachment_search_document_expression(),
        normalized_query=normalized_query,
        owner_filters=owner_filters,
        candidate_limit=candidate_limit,
    )
    return statement.join(Email, Attachment.email_id == Email.id).where(
        Attachment.parse_status == _SEARCHABLE_ATTACHMENT_PARSE_STATUS
    )


def build_lexical_content_segment_statement(
    normalized_query: str, owner_filters, candidate_limit: int
) -> Select:
    statement = _lexical_scored_statement(
        matched_text_column=ContentSegmentRecord.safe_text_content,
        result_kind=CONTENT_SEGMENT_RESULT_KIND,
        document_expression=content_segment_search_document_expression(),
        normalized_query=normalized_query,
        owner_filters=owner_filters,
        candidate_limit=candidate_limit,
    )
    return statement.join(Email, ContentSegmentRecord.email_id == Email.id)


def build_lexical_project_object_statement(
    normalized_query: str, owner_filters, candidate_limit: int
) -> Select:
    statement = _lexical_scored_statement(
        matched_text_column=ProjectGraphObjectRecord.summary,
        result_kind=PROJECT_GRAPH_OBJECT_RESULT_KIND,
        document_expression=project_object_search_document_expression(),
        normalized_query=normalized_query,
        owner_filters=owner_filters,
        candidate_limit=candidate_limit,
    )
    return statement.join(
        Email, ProjectGraphObjectRecord.email_id == Email.id
    ).where(
        ProjectGraphObjectRecord.status_code.not_in(
            _EXCLUDED_PROJECT_OBJECT_STATUS_CODES
        )
    )


def _dense_scored_statement(
    *,
    matched_text_column,
    result_kind: str,
    embedding_column,
    query_embedding: list[float],
    owner_filters,
    candidate_limit: int,
) -> Select:
    cosine_distance = embedding_column.cosine_distance(query_embedding)
    return (
        select(
            *_candidate_columns(matched_text_column, result_kind),
            cosine_distance.label("cosine_distance"),
        )
        .where(*owner_filters)
        .where(embedding_column.is_not(None))
        .order_by(cosine_distance)
        .limit(candidate_limit)
    )


def build_dense_email_statement(
    query_embedding: list[float], owner_filters, candidate_limit: int
) -> Select:
    return _dense_scored_statement(
        matched_text_column=Email.body,
        result_kind=EMAIL_BODY_RESULT_KIND,
        embedding_column=Email.embedding,
        query_embedding=query_embedding,
        owner_filters=owner_filters,
        candidate_limit=candidate_limit,
    )


def build_dense_attachment_statement(
    query_embedding: list[float], owner_filters, candidate_limit: int
) -> Select:
    statement = _dense_scored_statement(
        matched_text_column=Attachment.content,
        result_kind=ATTACHMENT_RESULT_KIND,
        embedding_column=Attachment.embedding,
        query_embedding=query_embedding,
        owner_filters=owner_filters,
        candidate_limit=candidate_limit,
    )
    return statement.join(Email, Attachment.email_id == Email.id).where(
        Attachment.parse_status == _SEARCHABLE_ATTACHMENT_PARSE_STATUS
    )
