import base64
import binascii
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal, NamedTuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from api.auth import AuthContext, get_auth_context, is_admin_role
from api.common.scopes import connector_scope_statement
from api.runner_ws import manager as runner_manager
from core.config import settings
from db.models import (
    Attachment,
    ConnectorSignalEvent,
    ContentSegmentRecord,
    Document,
    Email,
    KnowledgeGraphEdgeRecord,
    ProjectFolder,
    SenderRelationship,
    WebdavAccount,
)
from db.session import get_db
from services.attachment_parser import (
    CONTENT_TYPE_MISMATCH_QUARANTINED_STATUS,
    get_attachment_parser_manifest,
)
from services.newsdom_pdf_recognition import (
    PDF_DOM_RECOGNITION_PENDING_STATUS,
)
from services.ontology_service import ontology_service
from services.webdav_service import webdav_service

router = APIRouter(prefix="/api/data", tags=["data"])

DATA_VECTOR_DIMENSIONS = 1536
# Upper bound for the binary PDF DOM recognition upload variant. Kept in step
# with the NewsDOM sidecar's own MAX_PARSE_UPLOAD_BYTES (20 MiB): accepting more
# would let a caller stash a pending document the configured sidecar will always
# reject while the base64 copy inflates the database.
_MAX_PDF_DOM_UPLOAD_BYTES = 20 * 1024 * 1024
# The only status a reparse-intent may act on -- an attachment that parsed
# cleanly, is still pending, or already failed for an unrelated reason has
# nothing for a reparse pass to usefully re-evaluate.
ATTACHMENT_REPARSE_PENDING_STATUS = "reparse_pending"
ATTACHMENT_PARSE_BREAKDOWN_EVIDENCE_SOURCE = (
    "email_attachments.content_type, "
    "email_attachments.parse_content_type, "
    "email_attachments.parse_status, email_attachments.parser_key"
)
CONTENT_GRAPH_BREAKDOWN_EVIDENCE_SOURCE = (
    "content_segments.source_kind, content_segments.segment_kind"
)
KNOWLEDGE_GRAPH_BREAKDOWN_EVIDENCE_SOURCE = (
    "knowledge_graph_edges.source_kind, knowledge_graph_edges.edge_kind"
)
CONTENT_SEGMENT_TEXT_READINESS_EVIDENCE_SOURCE = (
    "content_segments.word_count, content_segments.safe_text_content"
)
KNOWLEDGE_GRAPH_EVIDENCE_ENDPOINT_READINESS_EVIDENCE_SOURCE = (
    "knowledge_graph_edges.source_segment_id, "
    "knowledge_graph_edges.target_segment_id"
)
SEMANTIC_KG_READINESS_EVIDENCE_SOURCE = (
    "knowledge_graph_edges.edge_kind, content_segments.segment_path"
)
SEMANTIC_RELATION_SOURCE_BACKING_EVIDENCE_SOURCE = (
    "sender_relationships.source_message_id, "
    "sender_relationships.source_thread_id"
)
WEB_DAV_ERROR_STATUS_CODES = {
    "no_webdav_account": 422,
    "webdav_account_not_found": 422,
}
SurfaceStatus = Literal[
    "ready",
    "running",
    "needs_attention",
    "pending",
    "no_source",
]
QualityStatus = Literal["pass", "needs_attention", "pending"]
AcquisitionReadinessState = Literal["ready", "needs_attention", "pending"]
EvidencePacketChecklistState = Literal["ready", "needs_attention", "pending"]
DataRoomManifestState = Literal["ready", "needs_attention", "pending"]
DataRoomArtifactType = Literal[
    "snapshot_json",
    "verifier_script",
    "policy_json",
    "manifest_json",
    "evidence_samples_json",
    "readiness_summary_json",
]
CloseGateStatus = Literal["blocked", "ready"]
DiligenceCloseDecision = Literal["ready_to_close", "close_blocked"]
DiligenceCloseSeverity = Literal["critical", "high", "medium", "none"]
DiligenceArtifactReviewStatus = Literal["blocked", "ready_for_review"]
DiligenceOwnerHandoffStatus = Literal["blocked", "ready_for_handoff"]
RemediationPriority = Literal["critical", "high", "medium"]
DiligenceRecommendation = Literal[
    "ready_for_diligence",
    "remediate_before_close",
    "insufficient_evidence",
]
DiligenceRiskLevel = Literal["low", "medium", "high"]
EndpointStatus = Literal["segment_backed", "node_only", "missing_endpoint"]
ConfidenceBucket = Literal["high", "medium", "low", "unknown"]
RelationSourceScope = Literal["message_thread", "message", "thread", "unknown"]
RepositoryAssetState = Literal["ready", "needs_attention"]
RepositoryType = Literal[
    "webdav_account",
    "project_folder",
    "email_repository",
    "attachment_repository",
    "document_repository",
]
EmailScopeFilter = tuple[ColumnElement[bool], ColumnElement[bool], ColumnElement[bool]]
AttachmentAssetRow = Row[tuple[Attachment, Email]]


class EmailQualityStats(NamedTuple):
    count: int
    missing_thread_count: int
    missing_fingerprint_count: int
    embedded_count: int


class AttachmentQualityStats(NamedTuple):
    count: int
    blank_content_count: int
    embedded_count: int


class AttachmentParseQualityStats(NamedTuple):
    parsed_count: int
    unparsed_count: int


class ContentGraphQualityStats(NamedTuple):
    segmented_email_count: int
    segment_count: int


class KnowledgeGraphQualityStats(NamedTuple):
    edged_email_count: int
    edge_count: int


class ContentSegmentTextReadinessStats(NamedTuple):
    total_count: int
    issue_count: int


class KnowledgeGraphEvidenceEndpointStats(NamedTuple):
    total_count: int
    issue_count: int


class SemanticRelationEvidenceStats(NamedTuple):
    total_count: int
    source_backed_count: int


class DataRepositorySummary(BaseModel):
    source_id: str
    repository_type: RepositoryType
    display_name: str
    object_count: int
    writeback_enabled: bool | None
    evidence_source: str
    provider_write_executed: bool


class DataRepositoryAsset(BaseModel):
    asset_key: str
    asset_type: Literal["email_attachment", "workspace_document"]
    display_name: str
    source_label: str
    state_code: RepositoryAssetState
    detail_text: str
    content_chars: int
    captured_at: str
    evidence_source: str
    thread_key: str
    provider_write_executed: bool


class DataPipelineStage(BaseModel):
    stage_key: str
    display_name: str
    status_code: SurfaceStatus
    progress_percent: int
    evidence_source: str
    detail_text: str
    provider_write_executed: bool


class DataEmbeddingCollection(BaseModel):
    collection_key: str
    display_name: str
    object_count: int
    embedded_count: int
    embedding_model: str
    vector_dimensions: int
    status_code: SurfaceStatus
    evidence_source: str
    provider_write_executed: bool


class DataQualityCheck(BaseModel):
    check_key: str
    display_name: str
    status_code: QualityStatus
    issue_count: int
    total_count: int
    evidence_source: str
    detail_text: str
    provider_write_executed: bool


class DataAcquisitionRemediationAction(BaseModel):
    action_key: str
    blocking_check_key: str
    display_name: str
    owner_area: str
    priority_rank: int
    priority_code: RemediationPriority
    impact_text: str
    recommended_next_step: str
    provider_write_executed: bool


class DataAcquisitionReadinessKpi(BaseModel):
    kpi_key: str
    source_check_key: str
    display_name: str
    owner_area: str
    priority_rank: int
    current_percent: int
    target_percent: int
    target_met: bool
    status_code: QualityStatus
    guardrail_text: str
    provider_write_executed: bool


class DataAcquisitionDecisionSummary(BaseModel):
    summary_key: str
    recommendation_code: DiligenceRecommendation
    risk_level: DiligenceRiskLevel
    target_gap_count: int
    critical_action_count: int
    high_action_count: int
    medium_action_count: int
    headline_text: str
    next_step_text: str
    provider_write_executed: bool


class DataAcquisitionReadinessGate(BaseModel):
    gate_key: str
    display_name: str
    state_code: AcquisitionReadinessState
    readiness_score: int
    passed_checks: int
    issue_checks: int
    pending_checks: int
    total_checks: int
    blocking_check_keys: list[str]
    evidence_packet_ready: bool
    snapshot_verification_ready: bool
    provider_write_executed: bool
    kpis: list[DataAcquisitionReadinessKpi]
    decision_summary: DataAcquisitionDecisionSummary
    remediation_actions: list[DataAcquisitionRemediationAction]
    detail_text: str


class DataAttachmentParseBreakdown(BaseModel):
    content_type: str
    parse_content_type: str
    parse_status: str
    parser_key: str
    display_name: str
    object_count: int
    evidence_source: str
    provider_write_executed: bool


class DataAttachmentActionResponse(BaseModel):
    attachment_uid: str
    filename: str
    content_type: str
    parse_content_type: str
    parse_status: str
    parse_error_code: str | None
    provider_write_executed: bool
    provenance: Literal["server-authoritative"]
    audit_event: str
    message: str


class DataContentGraphBreakdown(BaseModel):
    source_kind: str
    segment_kind: str
    object_count: int
    evidence_source: str
    provider_write_executed: bool


class DataKnowledgeGraphBreakdown(BaseModel):
    source_kind: str
    edge_kind: str
    object_count: int
    evidence_source: str
    provider_write_executed: bool


class DataContentGraphEvidenceSample(BaseModel):
    sample_key: str
    source_kind: str
    segment_kind: str
    segment_path: str
    word_count: int


class DataKnowledgeGraphEvidenceSample(BaseModel):
    sample_key: str
    source_kind: str
    edge_kind: str
    edge_path: str
    endpoint_status: EndpointStatus


class DataSemanticRelationEvidenceSample(BaseModel):
    sample_key: str
    relationship_type: str
    confidence_bucket: ConfidenceBucket
    source_scope: RelationSourceScope
    next_action: str


class DataSemanticExtractionManifest(BaseModel):
    manifest_key: str
    display_name: str
    state_code: Literal["provenance_gate_pending", "ready"]
    structural_edge_count: int
    semantic_relation_count: int
    source_backed_relation_count: int
    required_evidence: list[str]
    detail_text: str
    provider_write_executed: bool


class DataConnectorEvent(BaseModel):
    event_uid: str
    signal_key: str
    state_code: str
    detail_text: str | None
    observed_at: str


class DataDocumentUploadRequest(BaseModel):
    document_name: str = Field(min_length=1, max_length=240)
    document_type: str = Field(min_length=1, max_length=120)
    document_content: str = Field(default="", max_length=2_000_000)


class DataDocumentWebdavMaterializationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_source_id: str | None = None
    execute_provider: bool = False


class DataDocumentActionResponse(BaseModel):
    document_id: str
    workspace_id: str
    document_name: str
    document_type: str
    document_status: str
    content_chars: int
    provider_write_executed: bool
    provenance: Literal["server-authoritative"]
    audit_event: str
    message: str


class DataDocumentWebdavMaterializationResponse(BaseModel):
    intent: Literal["document_webdav_materialization"]
    status: str
    document_id: str
    workspace_id: str
    document_name: str
    document_type: str
    source_id: str | None
    target_label: str | None
    target_path: str
    requires_if_match: bool
    if_match: str | None = None
    provenance: Literal["server-authoritative"]
    provider_write_executed: bool
    audit_event: str
    runner_request_id: str | None = None
    provider_status: int | None = None
    error_code: str | None = None
    retry_item_uid: str | None = None
    message: str


class DataQualitySurfaceResponse(BaseModel):
    workspace_id: str
    organization_id: str | None
    audit_event: Literal["data.quality_surface.viewed"]
    provider_write_executed: bool
    acquisition_readiness_gate: DataAcquisitionReadinessGate
    repositories: list[DataRepositorySummary]
    repository_assets: list[DataRepositoryAsset]
    pipeline_stages: list[DataPipelineStage]
    embedding_collections: list[DataEmbeddingCollection]
    quality_checks: list[DataQualityCheck]
    attachment_parse_breakdown: list[DataAttachmentParseBreakdown]
    content_graph_breakdown: list[DataContentGraphBreakdown]
    knowledge_graph_breakdown: list[DataKnowledgeGraphBreakdown]
    content_graph_evidence_samples: list[DataContentGraphEvidenceSample]
    knowledge_graph_evidence_samples: list[DataKnowledgeGraphEvidenceSample]
    semantic_relation_evidence_samples: list[DataSemanticRelationEvidenceSample]
    semantic_extraction_manifest: list[DataSemanticExtractionManifest]
    connector_events: list[DataConnectorEvent]


class DataEvidenceSnapshotParserSummary(BaseModel):
    parser_key: str
    display_name: str
    parse_status: str
    content_types: list[str]
    extensions: list[str]


class DataEvidenceSnapshotPrivacyPolicy(BaseModel):
    raw_content_exposed: bool
    stable_identifiers_exposed: bool
    provider_credentials_exposed: bool
    redacted_fields: list[str]
    allowed_sample_fields: list[str]


class DataEvidenceSnapshotValidationStatus(BaseModel):
    status_code: QualityStatus
    checks_passed: int
    checks_with_issues: int
    total_checks: int


class DataEvidenceSnapshotVerificationHandoff(BaseModel):
    verifier_key: str
    verifier_command: str
    accepted_input: str
    digest_algorithm: Literal["sha256"]
    excluded_digest_fields: list[str]
    success_exit_code: int
    failure_exit_codes: dict[str, int]
    handoff_text: str
    provider_write_executed: bool


class DataEvidencePacketChecklistItem(BaseModel):
    checklist_key: str
    display_name: str
    state_code: EvidencePacketChecklistState
    source_field: str
    required_artifact: str
    detail_text: str
    provider_write_executed: bool


class DataRoomPackageManifestEntry(BaseModel):
    manifest_key: str
    file_name: str
    artifact_type: DataRoomArtifactType
    display_name: str
    state_code: DataRoomManifestState
    source_field: str
    required_for_close: bool
    contains_raw_content: bool
    contains_stable_identifiers: bool
    detail_text: str
    provider_write_executed: bool


class DataDiligenceExceptionRegisterEntry(BaseModel):
    exception_key: str
    blocking_check_key: str
    display_name: str
    severity_code: RemediationPriority
    owner_area: str
    source_field: str
    related_artifact: str
    blocks_close: bool
    detail_text: str
    next_action: str
    provider_write_executed: bool


class DataDiligenceRiskMatrixEntry(BaseModel):
    matrix_key: str
    severity_code: RemediationPriority
    owner_area: str
    related_artifact: str
    exception_count: int
    representative_exception_keys: list[str]
    risk_label: str
    buyer_implication: str
    recommended_next_action: str
    blocks_close: bool
    provider_write_executed: bool


class DataDiligenceCloseProofPlanEntry(BaseModel):
    proof_key: str
    severity_code: RemediationPriority
    owner_area: str
    related_artifact: str
    exception_count: int
    required_proof_artifact: str
    acceptance_criteria: str
    verification_method: str
    buyer_close_dependency: str
    close_gate_status: CloseGateStatus
    next_action: str
    provider_write_executed: bool


class DataDiligenceCloseDecisionSummary(BaseModel):
    summary_key: str
    decision_code: DiligenceCloseDecision
    total_proof_count: int
    blocked_proof_count: int
    ready_proof_count: int
    critical_blocker_count: int
    high_blocker_count: int
    medium_blocker_count: int
    required_artifact_count: int
    required_artifacts: list[str]
    highest_severity: DiligenceCloseSeverity
    snapshot_verification_required: bool
    buyer_summary_text: str
    next_action_text: str
    provider_write_executed: bool


class DataDiligenceCloseArtifactReviewQueueEntry(BaseModel):
    queue_key: str
    required_proof_artifact: str
    owner_areas: list[str]
    proof_count: int
    blocked_proof_count: int
    ready_proof_count: int
    highest_severity: DiligenceCloseSeverity
    buyer_review_role: str
    review_status: DiligenceArtifactReviewStatus
    acceptance_summary: str
    next_action: str
    snapshot_verification_required: bool
    provider_write_executed: bool


class DataDiligenceCloseOwnerHandoffQueueEntry(BaseModel):
    handoff_key: str
    owner_area: str
    related_artifacts: list[str]
    proof_count: int
    blocked_proof_count: int
    ready_proof_count: int
    highest_severity: DiligenceCloseSeverity
    buyer_review_roles: list[str]
    handoff_status: DiligenceOwnerHandoffStatus
    acceptance_summary: str
    next_action: str
    snapshot_verification_required: bool
    provider_write_executed: bool


class DataDiligenceCloseTraceabilityMapEntry(BaseModel):
    trace_key: str
    source_field: str
    data_room_artifact: str
    manifest_key: str
    exception_keys: list[str]
    risk_key: str
    proof_key: str
    artifact_review_key: str
    owner_handoff_key: str
    owner_area: str
    severity_code: DiligenceCloseSeverity
    exception_count: int
    close_gate_status: CloseGateStatus
    buyer_review_roles: list[str]
    trace_summary: str
    next_action: str
    snapshot_verification_required: bool
    provider_write_executed: bool


def _default_diligence_close_decision_summary() -> DataDiligenceCloseDecisionSummary:
    return DataDiligenceCloseDecisionSummary(
        summary_key="buyer_close_decision",
        decision_code="ready_to_close",
        total_proof_count=0,
        blocked_proof_count=0,
        ready_proof_count=0,
        critical_blocker_count=0,
        high_blocker_count=0,
        medium_blocker_count=0,
        required_artifact_count=0,
        required_artifacts=[],
        highest_severity="none",
        snapshot_verification_required=False,
        buyer_summary_text="No close proof requirements are present.",
        next_action_text="Generate the evidence snapshot before buyer close review.",
        provider_write_executed=False,
    )


class DataEvidenceSnapshotQualityCheck(BaseModel):
    check_key: str
    display_name: str
    status_code: QualityStatus
    issue_count: int
    total_count: int
    detail_text: str


class DataEvidenceSnapshotContentTopologyCount(BaseModel):
    source_kind: str
    segment_kind: str
    object_count: int


class DataEvidenceSnapshotKnowledgeTopologyCount(BaseModel):
    source_kind: str
    edge_kind: str
    object_count: int


class DataEvidenceSnapshotResponse(BaseModel):
    snapshot_version: str
    generated_at: str
    audit_event: Literal["data.quality_surface.evidence_snapshot.viewed"]
    scope_label: str
    snapshot_digest: str
    digest_algorithm: Literal["sha256"]
    canonical_payload_fields: list[str]
    privacy_redaction_policy: DataEvidenceSnapshotPrivacyPolicy
    acquisition_readiness_gate: DataAcquisitionReadinessGate
    validation_status: DataEvidenceSnapshotValidationStatus
    verification_handoff: DataEvidenceSnapshotVerificationHandoff
    evidence_packet_checklist: list[DataEvidencePacketChecklistItem] = Field(
        default_factory=list
    )
    data_room_package_manifest: list[DataRoomPackageManifestEntry] = Field(
        default_factory=list
    )
    diligence_exception_register: list[DataDiligenceExceptionRegisterEntry] = Field(
        default_factory=list
    )
    diligence_risk_matrix: list[DataDiligenceRiskMatrixEntry] = Field(
        default_factory=list
    )
    diligence_close_proof_plan: list[DataDiligenceCloseProofPlanEntry] = Field(
        default_factory=list
    )
    diligence_close_decision_summary: DataDiligenceCloseDecisionSummary = Field(
        default_factory=_default_diligence_close_decision_summary
    )
    diligence_close_artifact_review_queue: list[
        DataDiligenceCloseArtifactReviewQueueEntry
    ] = Field(default_factory=list)
    diligence_close_owner_handoff_queue: list[
        DataDiligenceCloseOwnerHandoffQueueEntry
    ] = Field(default_factory=list)
    diligence_close_traceability_map: list[
        DataDiligenceCloseTraceabilityMapEntry
    ] = Field(default_factory=list)
    parser_manifest_summary: list[DataEvidenceSnapshotParserSummary]
    quality_checks: list[DataEvidenceSnapshotQualityCheck]
    content_graph_topology_counts: list[DataEvidenceSnapshotContentTopologyCount]
    knowledge_graph_topology_counts: list[DataEvidenceSnapshotKnowledgeTopologyCount]
    content_graph_evidence_samples: list[DataContentGraphEvidenceSample]
    knowledge_graph_evidence_samples: list[DataKnowledgeGraphEvidenceSample]
    semantic_relation_evidence_samples: list[DataSemanticRelationEvidenceSample]
    semantic_extraction_manifest: list[DataSemanticExtractionManifest]


def _datetime_to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_display_text(value: str | None, fallback: str) -> str:
    cleaned = (value or fallback).replace("<", "").replace(">", "").strip()
    return " ".join(cleaned.split())[:120] or fallback


def _safe_document_type(value: str) -> str:
    return _safe_display_text(value, "application/octet-stream")[:120]


_ATTACHMENT_PARSER_BY_CONTENT_TYPE = {
    content_type: descriptor
    for descriptor in get_attachment_parser_manifest()
    for content_type in descriptor.content_types
}
_ATTACHMENT_PARSER_BY_KEY = {
    descriptor.parser_key: descriptor for descriptor in get_attachment_parser_manifest()
}
_UNSUPPORTED_ATTACHMENT_PARSER = _ATTACHMENT_PARSER_BY_CONTENT_TYPE[
    "application/octet-stream"
]
SNAPSHOT_VERSION = "data_quality_evidence_snapshot.v1"
SNAPSHOT_REDACTED_FIELDS = [
    "raw_email_body",
    "raw_html",
    "attachment_bytes",
    "message_id",
    "attachment_id",
    "source_record_id",
    "stable_database_id",
    "provider_credentials",
    "db_evidence_column_strings",
]
SNAPSHOT_ALLOWED_SAMPLE_FIELDS = [
    "sample_key",
    "source_kind",
    "segment_kind",
    "edge_kind",
    "segment_path",
    "edge_path",
    "word_count",
    "endpoint_status",
    "manifest_key",
    "state_code",
    "structural_edge_count",
    "semantic_relation_count",
    "source_backed_relation_count",
    "relationship_type",
    "confidence_bucket",
    "source_scope",
    "next_action",
    "required_evidence",
]
SNAPSHOT_DIGEST_EXCLUDED_FIELDS = {
    "snapshot_digest",
    "digest_algorithm",
    "canonical_payload_fields",
}
_REMEDIATION_ACTIONS_BY_CHECK_KEY = {
    "thread_id_integrity": {
        "action_key": "repair_thread_id_integrity",
        "display_name": "Canonical thread repair",
        "owner_area": "email_ingestion",
        "priority_rank": 1,
        "priority_code": "critical",
        "impact_text": "Thread provenance must be stable before buyer review.",
        "recommended_next_step": (
            "Run canonical threading repair for affected scoped emails."
        ),
    },
    "dedupe_fingerprint": {
        "action_key": "backfill_dedupe_fingerprints",
        "display_name": "Duplicate fingerprint backfill",
        "owner_area": "email_ingestion",
        "priority_rank": 2,
        "priority_code": "critical",
        "impact_text": "Duplicate detection must be reliable before corpus valuation.",
        "recommended_next_step": (
            "Backfill duplicate-detection fingerprints for scoped email records."
        ),
    },
    "attachment_content": {
        "action_key": "recover_attachment_content",
        "display_name": "Attachment content extraction",
        "owner_area": "attachment_parsing",
        "priority_rank": 3,
        "priority_code": "high",
        "impact_text": "Attachment text gaps reduce searchable diligence coverage.",
        "recommended_next_step": (
            "Re-run attachment extraction for scoped attachments with blank safe "
            "content."
        ),
    },
    "content_graph_coverage": {
        "action_key": "backfill_content_graph_coverage",
        "display_name": "DOM paragraph segmentation backfill",
        "owner_area": "content_graph",
        "priority_rank": 4,
        "priority_code": "high",
        "impact_text": (
            "Every scoped email needs paragraph segments before graph evidence is "
            "complete."
        ),
        "recommended_next_step": (
            "Backfill DOM paragraph segmentation for unsegmented scoped emails."
        ),
    },
    "knowledge_graph_coverage": {
        "action_key": "backfill_knowledge_graph_coverage",
        "display_name": "Knowledge graph edge persistence",
        "owner_area": "knowledge_graph",
        "priority_rank": 5,
        "priority_code": "high",
        "impact_text": "Stored edges are required to prove graph extraction coverage.",
        "recommended_next_step": (
            "Persist deterministic knowledge graph edges for emails missing graph "
            "coverage."
        ),
    },
    "content_segment_text_readiness": {
        "action_key": "repair_segment_text_readiness",
        "display_name": "Segment safe text repair",
        "owner_area": "content_graph",
        "priority_rank": 6,
        "priority_code": "high",
        "impact_text": "Paragraph evidence needs non-empty safe text and word counts.",
        "recommended_next_step": (
            "Rebuild affected content segments with safe text and word-count "
            "evidence."
        ),
    },
    "knowledge_graph_evidence_endpoint_readiness": {
        "action_key": "attach_kg_evidence_endpoints",
        "display_name": "KG evidence endpoint repair",
        "owner_area": "knowledge_graph",
        "priority_rank": 7,
        "priority_code": "high",
        "impact_text": "KG edges need paragraph endpoints to be auditable.",
        "recommended_next_step": (
            "Attach source or target paragraph segment endpoints to affected KG "
            "edges."
        ),
    },
    "semantic_relation_source_backing": {
        "action_key": "backfill_semantic_relation_sources",
        "display_name": "Semantic relation source backing",
        "owner_area": "semantic_kg",
        "priority_rank": 8,
        "priority_code": "high",
        "impact_text": "Semantic relations need source message or thread evidence.",
        "recommended_next_step": (
            "Backfill source message or thread links for semantic relation records."
        ),
    },
    "attachment_parse_coverage": {
        "action_key": "expand_attachment_parse_coverage",
        "display_name": "Attachment parser coverage",
        "owner_area": "attachment_parsing",
        "priority_rank": 9,
        "priority_code": "medium",
        "impact_text": "Unsupported attachments leave buyer-visible corpus gaps.",
        "recommended_next_step": (
            "Add parser coverage or metadata-only exception evidence for unsupported "
            "attachment types."
        ),
    },
    "source_registry": {
        "action_key": "register_customer_sources",
        "display_name": "Customer source registration",
        "owner_area": "connector_registry",
        "priority_rank": 10,
        "priority_code": "critical",
        "impact_text": "Customer-owned source visibility anchors diligence scope.",
        "recommended_next_step": (
            "Connect or verify customer-owned repositories for this workspace."
        ),
    },
    "connector_signal": {
        "action_key": "restore_connector_observability",
        "display_name": "Connector observability repair",
        "owner_area": "connector_observability",
        "priority_rank": 11,
        "priority_code": "medium",
        "impact_text": "Connector evidence proves jobs are observable after handoff.",
        "recommended_next_step": (
            "Restore connector heartbeat or job evidence for the workspace."
        ),
    },
    "semantic_kg_readiness": {
        "action_key": "approve_semantic_extraction_evidence",
        "display_name": "Semantic extraction approval",
        "owner_area": "semantic_kg",
        "priority_rank": 12,
        "priority_code": "medium",
        "impact_text": "Semantic KG claims need provenance and correction evidence.",
        "recommended_next_step": (
            "Approve semantic extraction evidence before claiming semantic KG "
            "readiness."
        ),
    },
}
_EXCEPTION_SOURCE_FIELD_BY_CHECK_KEY = {
    "thread_id_integrity": "quality_checks.thread_id_integrity",
    "dedupe_fingerprint": "quality_checks.dedupe_fingerprint",
    "attachment_content": "quality_checks.attachment_content",
    "content_graph_coverage": "quality_checks.content_graph_coverage",
    "knowledge_graph_coverage": "quality_checks.knowledge_graph_coverage",
    "content_segment_text_readiness": "quality_checks.content_segment_text_readiness",
    "knowledge_graph_evidence_endpoint_readiness": (
        "quality_checks.knowledge_graph_evidence_endpoint_readiness"
    ),
    "semantic_relation_source_backing": (
        "quality_checks.semantic_relation_source_backing"
    ),
    "attachment_parse_coverage": "quality_checks.attachment_parse_coverage",
}
_EXCEPTION_ARTIFACT_BY_CHECK_KEY = {
    "thread_id_integrity": "acquisition-readiness-summary.json",
    "dedupe_fingerprint": "acquisition-readiness-summary.json",
    "attachment_content": "remediation-actions.json",
    "content_graph_coverage": "dom-paragraph-evidence-samples.json",
    "knowledge_graph_coverage": "knowledge-graph-evidence-samples.json",
    "content_segment_text_readiness": "dom-paragraph-evidence-samples.json",
    "knowledge_graph_evidence_endpoint_readiness": (
        "knowledge-graph-evidence-samples.json"
    ),
    "semantic_relation_source_backing": "semantic-relation-evidence-samples.json",
    "attachment_parse_coverage": "remediation-actions.json",
}
_RISK_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2}
_RISK_LABEL_BY_SEVERITY = {
    "critical": "Critical close blocker concentration",
    "high": "High diligence evidence gap",
    "medium": "Medium diligence coverage gap",
}
_CLOSE_DEPENDENCY_BY_SEVERITY = {
    "critical": "critical evidence gate",
    "high": "high priority evidence gate",
    "medium": "coverage exception gate",
}
_ARTIFACT_REVIEW_ROLE_BY_SEVERITY = {
    "critical": "executive diligence reviewer",
    "high": "data quality reviewer",
    "medium": "coverage reviewer",
    "none": "buyer reviewer",
}
_ACQUISITION_KPI_TARGETS_BY_CHECK_KEY = {
    "thread_id_integrity": {
        "kpi_key": "thread_id_integrity_target",
        "display_name": "Thread id integrity target",
        "owner_area": "email_ingestion",
        "priority_rank": 1,
        "target_percent": 100,
        "guardrail_text": (
            "Thread provenance must reach target before acquisition close."
        ),
    },
    "dedupe_fingerprint": {
        "kpi_key": "dedupe_fingerprint_target",
        "display_name": "Duplicate fingerprint target",
        "owner_area": "email_ingestion",
        "priority_rank": 2,
        "target_percent": 100,
        "guardrail_text": (
            "Duplicate fingerprints must reach target before corpus valuation."
        ),
    },
    "attachment_content": {
        "kpi_key": "attachment_content_target",
        "display_name": "Attachment content target",
        "owner_area": "attachment_parsing",
        "priority_rank": 3,
        "target_percent": 100,
        "guardrail_text": (
            "Attachment text extraction must reach target before buyer review."
        ),
    },
    "content_graph_coverage": {
        "kpi_key": "content_graph_coverage_target",
        "display_name": "DOM paragraph coverage target",
        "owner_area": "content_graph",
        "priority_rank": 4,
        "target_percent": 100,
        "guardrail_text": (
            "DOM paragraph segmentation must reach target before graph claims."
        ),
    },
    "knowledge_graph_coverage": {
        "kpi_key": "knowledge_graph_coverage_target",
        "display_name": "Knowledge graph coverage target",
        "owner_area": "knowledge_graph",
        "priority_rank": 5,
        "target_percent": 100,
        "guardrail_text": (
            "Knowledge graph edge persistence must reach target before diligence."
        ),
    },
    "content_segment_text_readiness": {
        "kpi_key": "content_segment_text_readiness_target",
        "display_name": "Segment text readiness target",
        "owner_area": "content_graph",
        "priority_rank": 6,
        "target_percent": 100,
        "guardrail_text": "Safe paragraph text and word counts must reach target.",
    },
    "knowledge_graph_evidence_endpoint_readiness": {
        "kpi_key": "kg_evidence_endpoint_target",
        "display_name": "KG evidence endpoint target",
        "owner_area": "knowledge_graph",
        "priority_rank": 7,
        "target_percent": 100,
        "guardrail_text": (
            "KG evidence endpoints must reach target before buyer audit."
        ),
    },
    "semantic_relation_source_backing": {
        "kpi_key": "semantic_relation_source_backing_target",
        "display_name": "Semantic relation source target",
        "owner_area": "semantic_kg",
        "priority_rank": 8,
        "target_percent": 100,
        "guardrail_text": "Semantic relation source backing must reach target.",
    },
    "attachment_parse_coverage": {
        "kpi_key": "attachment_parse_coverage_target",
        "display_name": "Attachment parser coverage target",
        "owner_area": "attachment_parsing",
        "priority_rank": 9,
        "target_percent": 100,
        "guardrail_text": (
            "Attachment parser coverage must reach target or have safe exceptions."
        ),
    },
    "source_registry": {
        "kpi_key": "source_registry_target",
        "display_name": "Source registry target",
        "owner_area": "connector_registry",
        "priority_rank": 10,
        "target_percent": 100,
        "guardrail_text": "Customer-owned source registration must stay complete.",
    },
    "connector_signal": {
        "kpi_key": "connector_signal_target",
        "display_name": "Connector observability target",
        "owner_area": "connector_observability",
        "priority_rank": 11,
        "target_percent": 100,
        "guardrail_text": "Connector observability must stay complete.",
    },
    "semantic_kg_readiness": {
        "kpi_key": "semantic_kg_readiness_target",
        "display_name": "Semantic KG evidence target",
        "owner_area": "semantic_kg",
        "priority_rank": 12,
        "target_percent": 100,
        "guardrail_text": "Semantic KG evidence must remain provenance-approved.",
    },
}


def _normalize_attachment_content_type(value: str | None) -> str:
    normalized = (value or "application/octet-stream").split(";", 1)[0]
    normalized = normalized.strip().lower()
    return normalized or "application/octet-stream"


def _attachment_parse_breakdown_row(
    content_type: str | None,
    parse_content_type: str | None,
    parse_status: str | None,
    parser_key: str | None,
    object_count: int,
) -> DataAttachmentParseBreakdown:
    normalized_content_type = _normalize_attachment_content_type(content_type)
    normalized_parse_content_type = _normalize_attachment_content_type(
        parse_content_type
    )
    safe_parse_status = _safe_display_text(parse_status, "unknown")[:64]
    safe_parser_key = _safe_display_text(parser_key, "unsupported_binary")[:64]
    descriptor = _ATTACHMENT_PARSER_BY_KEY.get(
        safe_parser_key,
        _UNSUPPORTED_ATTACHMENT_PARSER,
    )
    return DataAttachmentParseBreakdown(
        content_type=normalized_content_type,
        parse_content_type=normalized_parse_content_type,
        parse_status=safe_parse_status,
        parser_key=safe_parser_key,
        display_name=descriptor.display_name,
        object_count=int(object_count or 0),
        evidence_source=ATTACHMENT_PARSE_BREAKDOWN_EVIDENCE_SOURCE,
        provider_write_executed=False,
    )


def _content_graph_breakdown_row(
    source_kind: str | None,
    segment_kind: str | None,
    object_count: int,
) -> DataContentGraphBreakdown:
    return DataContentGraphBreakdown(
        source_kind=_safe_display_text(source_kind, "unknown")[:64],
        segment_kind=_safe_display_text(segment_kind, "unknown")[:64],
        object_count=int(object_count or 0),
        evidence_source=CONTENT_GRAPH_BREAKDOWN_EVIDENCE_SOURCE,
        provider_write_executed=False,
    )


def _knowledge_graph_breakdown_row(
    source_kind: str | None,
    edge_kind: str | None,
    object_count: int,
) -> DataKnowledgeGraphBreakdown:
    return DataKnowledgeGraphBreakdown(
        source_kind=_safe_display_text(source_kind, "unknown")[:64],
        edge_kind=_safe_display_text(edge_kind, "unknown")[:64],
        object_count=int(object_count or 0),
        evidence_source=KNOWLEDGE_GRAPH_BREAKDOWN_EVIDENCE_SOURCE,
        provider_write_executed=False,
    )


def _opaque_graph_sample_key(prefix: str, value: str | None) -> str:
    digest = hashlib.sha256((value or prefix).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _safe_graph_path(value: str | None, fallback: str) -> str:
    cleaned = (value or fallback).replace("\x00", "")
    cleaned = cleaned.replace("<", "").replace(">", "").strip()
    return " ".join(cleaned.split())[:240] or fallback


def _content_graph_evidence_sample_row(
    content_segment_uid: str | None,
    source_kind: str | None,
    segment_kind: str | None,
    segment_path: str | None,
    word_count: int | None,
) -> DataContentGraphEvidenceSample:
    return DataContentGraphEvidenceSample(
        sample_key=_opaque_graph_sample_key("segment", content_segment_uid),
        source_kind=_safe_display_text(source_kind, "unknown")[:64],
        segment_kind=_safe_display_text(segment_kind, "unknown")[:64],
        segment_path=_safe_graph_path(segment_path, "/document[1]"),
        word_count=int(word_count or 0),
    )


def _edge_endpoint_status(
    source_segment_id: int | None,
    target_segment_id: int | None,
    source_node_id: int | None,
    target_node_id: int | None,
) -> EndpointStatus:
    if source_segment_id is not None or target_segment_id is not None:
        return "segment_backed"
    if source_node_id is not None or target_node_id is not None:
        return "node_only"
    return "missing_endpoint"


def _knowledge_graph_evidence_sample_row(
    edge_uid: str | None,
    source_kind: str | None,
    edge_kind: str | None,
    edge_path: str | None,
    source_segment_id: int | None,
    target_segment_id: int | None,
    source_node_id: int | None,
    target_node_id: int | None,
) -> DataKnowledgeGraphEvidenceSample:
    return DataKnowledgeGraphEvidenceSample(
        sample_key=_opaque_graph_sample_key("edge", edge_uid),
        source_kind=_safe_display_text(source_kind, "unknown")[:64],
        edge_kind=_safe_display_text(edge_kind, "unknown")[:64],
        edge_path=_safe_graph_path(edge_path, "/document[1]"),
        endpoint_status=_edge_endpoint_status(
            source_segment_id,
            target_segment_id,
            source_node_id,
            target_node_id,
        ),
    )


def _confidence_bucket(value: float | None) -> ConfidenceBucket:
    if value is None:
        return "unknown"
    if value >= 0.8:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def _semantic_relation_source_scope(
    source_message_id: str | None,
    source_thread_id: str | None,
) -> RelationSourceScope:
    if source_message_id and source_thread_id:
        return "message_thread"
    if source_message_id:
        return "message"
    if source_thread_id:
        return "thread"
    return "unknown"


def _semantic_relation_evidence_sample_row(
    sender_email: str | None,
    source_message_id: str | None,
    source_thread_id: str | None,
    relationship_type: str | None,
    confidence_score: float | None,
) -> DataSemanticRelationEvidenceSample:
    safe_relationship_type = _safe_display_text(relationship_type, "Unknown")[:64]
    return DataSemanticRelationEvidenceSample(
        sample_key=_opaque_graph_sample_key(
            "relation",
            (
                f"{sender_email or ''}|{source_message_id or ''}|"
                f"{source_thread_id or ''}|{safe_relationship_type}"
            ),
        ),
        relationship_type=safe_relationship_type,
        confidence_bucket=_confidence_bucket(confidence_score),
        source_scope=_semantic_relation_source_scope(
            source_message_id,
            source_thread_id,
        ),
        next_action=ontology_service.next_action_for_relationship(
            safe_relationship_type
        )["next_action"],
    )


def _semantic_extraction_manifest(
    knowledge_graph_edge_count: int,
    semantic_relation_count: int,
    source_backed_relation_count: int,
) -> list[DataSemanticExtractionManifest]:
    state_code: Literal["provenance_gate_pending", "ready"] = (
        "ready" if source_backed_relation_count > 0 else "provenance_gate_pending"
    )
    detail_text = (
        "Semantic relation evidence is available from source-backed ontology "
        "relationship records."
        if state_code == "ready"
        else (
            "Structural DOM/paragraph edges are stored; semantic entity/relation "
            "extraction has not been enabled for buyer-visible evidence."
        )
    )
    return [
        DataSemanticExtractionManifest(
            manifest_key="entity_relation_extraction",
            display_name="Entity/relation extraction",
            state_code=state_code,
            structural_edge_count=knowledge_graph_edge_count,
            semantic_relation_count=semantic_relation_count,
            source_backed_relation_count=source_backed_relation_count,
            required_evidence=[
                "segment_citation",
                "extractor_version",
                "confidence_score",
                "human_correction_path",
            ],
            detail_text=detail_text,
            provider_write_executed=False,
        )
    ]


def _snapshot_parser_manifest_summary() -> list[DataEvidenceSnapshotParserSummary]:
    return [
        DataEvidenceSnapshotParserSummary(
            parser_key=descriptor.parser_key,
            display_name=descriptor.display_name,
            parse_status=descriptor.parse_status,
            content_types=list(descriptor.content_types),
            extensions=list(descriptor.extensions),
        )
        for descriptor in get_attachment_parser_manifest()
    ]


def _snapshot_privacy_policy() -> DataEvidenceSnapshotPrivacyPolicy:
    return DataEvidenceSnapshotPrivacyPolicy(
        raw_content_exposed=False,
        stable_identifiers_exposed=False,
        provider_credentials_exposed=False,
        redacted_fields=SNAPSHOT_REDACTED_FIELDS,
        allowed_sample_fields=SNAPSHOT_ALLOWED_SAMPLE_FIELDS,
    )


def _snapshot_validation_status(
    quality_checks: list[DataQualityCheck],
) -> DataEvidenceSnapshotValidationStatus:
    checks_passed = sum(1 for check in quality_checks if check.status_code == "pass")
    checks_with_issues = sum(1 for check in quality_checks if check.issue_count > 0)
    if any(check.status_code == "needs_attention" for check in quality_checks):
        status_code: QualityStatus = "needs_attention"
    elif any(check.status_code == "pending" for check in quality_checks):
        status_code = "pending"
    else:
        status_code = "pass"
    return DataEvidenceSnapshotValidationStatus(
        status_code=status_code,
        checks_passed=checks_passed,
        checks_with_issues=checks_with_issues,
        total_checks=len(quality_checks),
    )


def _snapshot_verification_handoff() -> DataEvidenceSnapshotVerificationHandoff:
    return DataEvidenceSnapshotVerificationHandoff(
        verifier_key="offline_evidence_snapshot_verifier",
        verifier_command="python scripts/verify_evidence_snapshot.py <snapshot.json>",
        accepted_input="file_path_or_stdin",
        digest_algorithm="sha256",
        excluded_digest_fields=sorted(SNAPSHOT_DIGEST_EXCLUDED_FIELDS),
        success_exit_code=0,
        failure_exit_codes={
            "invalid_json": 1,
            "missing_snapshot_digest": 2,
            "unsupported_digest_algorithm": 3,
            "digest_mismatch": 4,
        },
        handoff_text=(
            "Save the copied evidence snapshot JSON and verify it with the offline "
            "verifier before sharing diligence materials."
        ),
        provider_write_executed=False,
    )


def _checklist_state(
    is_ready: bool,
    fallback: EvidencePacketChecklistState = "needs_attention",
) -> EvidencePacketChecklistState:
    return "ready" if is_ready else fallback


def _evidence_packet_checklist(
    *,
    surface: DataQualitySurfaceResponse,
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataEvidencePacketChecklistItem]:
    privacy_policy = snapshot.privacy_redaction_policy
    privacy_ready = (
        not privacy_policy.raw_content_exposed
        and not privacy_policy.stable_identifiers_exposed
        and not privacy_policy.provider_credentials_exposed
    )
    semantic_manifest_ready = bool(snapshot.semantic_extraction_manifest) and all(
        item.state_code == "ready" for item in snapshot.semantic_extraction_manifest
    )
    verification_ready = (
        snapshot.verification_handoff.digest_algorithm == "sha256"
        and snapshot.verification_handoff.success_exit_code == 0
        and "digest_mismatch" in snapshot.verification_handoff.failure_exit_codes
    )
    return [
        DataEvidencePacketChecklistItem(
            checklist_key="privacy_redaction_policy",
            display_name="Privacy redaction policy",
            state_code=_checklist_state(privacy_ready),
            source_field="privacy_redaction_policy",
            required_artifact="redacted_snapshot_policy",
            detail_text=(
                "Snapshot excludes raw content, stable identifiers, credentials, "
                "and database evidence strings."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="parser_manifest",
            display_name="Attachment parser manifest",
            state_code=_checklist_state(bool(snapshot.parser_manifest_summary)),
            source_field="parser_manifest_summary",
            required_artifact="attachment_parser_registry",
            detail_text=(
                "Parser family, supported content types, extensions, and unsupported "
                "binary fallback are included."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="content_graph_topology",
            display_name="DOM paragraph topology",
            state_code=_checklist_state(bool(snapshot.content_graph_topology_counts)),
            source_field="content_graph_topology_counts",
            required_artifact="source_kind_segment_kind_counts",
            detail_text=(
                "Email body and attachment segments are summarized by source and "
                "paragraph or heading kind."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="content_graph_samples",
            display_name="Paragraph evidence samples",
            state_code=_checklist_state(bool(snapshot.content_graph_evidence_samples)),
            source_field="content_graph_evidence_samples",
            required_artifact="redacted_segment_samples",
            detail_text=(
                "Redacted paragraph samples include source kind, segment kind, path, "
                "and word count."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="knowledge_graph_topology",
            display_name="Knowledge graph topology",
            state_code=_checklist_state(
                bool(snapshot.knowledge_graph_topology_counts)
            ),
            source_field="knowledge_graph_topology_counts",
            required_artifact="source_kind_edge_kind_counts",
            detail_text=(
                "Stored KG edges are summarized by source and edge kind for "
                "acquisition review."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="knowledge_graph_samples",
            display_name="KG evidence samples",
            state_code=_checklist_state(
                bool(snapshot.knowledge_graph_evidence_samples)
            ),
            source_field="knowledge_graph_evidence_samples",
            required_artifact="redacted_edge_samples",
            detail_text=(
                "Redacted KG samples include edge path and endpoint readiness "
                "without exposing raw IDs."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="semantic_relation_samples",
            display_name="Semantic relation evidence",
            state_code=_checklist_state(
                bool(snapshot.semantic_relation_evidence_samples)
            ),
            source_field="semantic_relation_evidence_samples",
            required_artifact="source_backed_relation_samples",
            detail_text=(
                "Semantic relationship samples include confidence, source scope, "
                "and next action."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="semantic_extraction_manifest",
            display_name="Semantic extraction manifest",
            state_code=_checklist_state(semantic_manifest_ready, "pending"),
            source_field="semantic_extraction_manifest",
            required_artifact="extractor_provenance_manifest",
            detail_text=(
                "Entity/relation extraction readiness and required provenance "
                "evidence are included."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="acquisition_readiness_gate",
            display_name="Acquisition readiness gate",
            state_code=surface.acquisition_readiness_gate.state_code,
            source_field="acquisition_readiness_gate",
            required_artifact="buyer_evidence_readiness_gate",
            detail_text=(
                "Buyer readiness score, blocking checks, KPIs, decision summary, "
                "and remediation actions are included."
            ),
            provider_write_executed=False,
        ),
        DataEvidencePacketChecklistItem(
            checklist_key="offline_snapshot_verification",
            display_name="Offline snapshot verification",
            state_code=_checklist_state(verification_ready),
            source_field="verification_handoff",
            required_artifact="offline_digest_verifier_handoff",
            detail_text=(
                "Offline verifier command, accepted input, digest algorithm, "
                "excluded fields, and exit codes are included."
            ),
            provider_write_executed=False,
        ),
    ]


def _data_room_state(
    is_ready: bool,
    fallback: DataRoomManifestState = "needs_attention",
) -> DataRoomManifestState:
    return "ready" if is_ready else fallback


def _data_room_package_manifest(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataRoomPackageManifestEntry]:
    privacy_policy = snapshot.privacy_redaction_policy
    privacy_ready = (
        not privacy_policy.raw_content_exposed
        and not privacy_policy.stable_identifiers_exposed
        and not privacy_policy.provider_credentials_exposed
    )
    checklist_ready = bool(snapshot.evidence_packet_checklist) and all(
        item.state_code == "ready" for item in snapshot.evidence_packet_checklist
    )
    readiness_gate = snapshot.acquisition_readiness_gate
    remediation_ready = len(readiness_gate.remediation_actions) == 0

    def entry(
        *,
        manifest_key: str,
        file_name: str,
        artifact_type: DataRoomArtifactType,
        display_name: str,
        state_code: DataRoomManifestState,
        source_field: str,
        detail_text: str,
    ) -> DataRoomPackageManifestEntry:
        return DataRoomPackageManifestEntry(
            manifest_key=manifest_key,
            file_name=file_name,
            artifact_type=artifact_type,
            display_name=display_name,
            state_code=state_code,
            source_field=source_field,
            required_for_close=True,
            contains_raw_content=False,
            contains_stable_identifiers=False,
            detail_text=detail_text,
            provider_write_executed=False,
        )

    return [
        entry(
            manifest_key="evidence_snapshot_json",
            file_name="naruon-evidence-snapshot.json",
            artifact_type="snapshot_json",
            display_name="Evidence snapshot JSON",
            state_code=_data_room_state(
                snapshot.snapshot_version == SNAPSHOT_VERSION
                and snapshot.digest_algorithm == "sha256"
            ),
            source_field="snapshot_version,snapshot_digest,canonical_payload_fields",
            detail_text=(
                "Canonical redacted evidence snapshot for buyer diligence and "
                "offline digest verification."
            ),
        ),
        entry(
            manifest_key="offline_verifier",
            file_name="verify-evidence-snapshot.py",
            artifact_type="verifier_script",
            display_name="Offline digest verifier",
            state_code=_data_room_state(
                snapshot.verification_handoff.digest_algorithm == "sha256"
                and snapshot.verification_handoff.success_exit_code == 0
            ),
            source_field="verification_handoff",
            detail_text=(
                "Offline verifier script and expected exit-code contract for "
                "snapshot tamper checks."
            ),
        ),
        entry(
            manifest_key="privacy_policy",
            file_name="privacy-redaction-policy.json",
            artifact_type="policy_json",
            display_name="Privacy redaction policy",
            state_code=_data_room_state(privacy_ready),
            source_field="privacy_redaction_policy",
            detail_text=(
                "Redaction policy proving raw content, credentials, and stable IDs "
                "are excluded."
            ),
        ),
        entry(
            manifest_key="attachment_parser_manifest",
            file_name="attachment-parser-manifest.json",
            artifact_type="manifest_json",
            display_name="Attachment parser manifest",
            state_code=_data_room_state(bool(snapshot.parser_manifest_summary)),
            source_field="parser_manifest_summary",
            detail_text=(
                "Supported attachment parser families, content types, extensions, "
                "and unsupported fallback."
            ),
        ),
        entry(
            manifest_key="dom_paragraph_samples",
            file_name="dom-paragraph-evidence-samples.json",
            artifact_type="evidence_samples_json",
            display_name="DOM paragraph evidence samples",
            state_code=_data_room_state(bool(snapshot.content_graph_evidence_samples)),
            source_field="content_graph_evidence_samples",
            detail_text=(
                "Redacted DOM and paragraph samples for email and attachment "
                "content segmentation."
            ),
        ),
        entry(
            manifest_key="knowledge_graph_samples",
            file_name="knowledge-graph-evidence-samples.json",
            artifact_type="evidence_samples_json",
            display_name="Knowledge graph evidence samples",
            state_code=_data_room_state(
                bool(snapshot.knowledge_graph_evidence_samples)
            ),
            source_field="knowledge_graph_evidence_samples",
            detail_text=(
                "Redacted KG edge samples with safe paths and endpoint readiness."
            ),
        ),
        entry(
            manifest_key="semantic_relation_samples",
            file_name="semantic-relation-evidence-samples.json",
            artifact_type="evidence_samples_json",
            display_name="Semantic relation evidence samples",
            state_code=_data_room_state(
                bool(snapshot.semantic_relation_evidence_samples)
            ),
            source_field="semantic_relation_evidence_samples",
            detail_text=(
                "Source-backed semantic relation samples with confidence and next "
                "action."
            ),
        ),
        entry(
            manifest_key="evidence_packet_checklist",
            file_name="buyer-evidence-packet-checklist.json",
            artifact_type="manifest_json",
            display_name="Buyer evidence packet checklist",
            state_code=_data_room_state(checklist_ready),
            source_field="evidence_packet_checklist",
            detail_text=(
                "Checklist mapping buyer-required packet artifacts to safe snapshot "
                "fields."
            ),
        ),
        entry(
            manifest_key="acquisition_readiness_summary",
            file_name="acquisition-readiness-summary.json",
            artifact_type="readiness_summary_json",
            display_name="Acquisition readiness summary",
            state_code=readiness_gate.state_code,
            source_field="acquisition_readiness_gate",
            detail_text=(
                "Buyer readiness score, close recommendation, KPI gaps, and "
                "blocking checks."
            ),
        ),
        entry(
            manifest_key="remediation_actions",
            file_name="remediation-actions.json",
            artifact_type="readiness_summary_json",
            display_name="Remediation actions",
            state_code=_data_room_state(remediation_ready),
            source_field="acquisition_readiness_gate.remediation_actions",
            detail_text=(
                "Required remediation actions to close remaining diligence gaps."
            ),
        ),
    ]


def _diligence_exception_register(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataDiligenceExceptionRegisterEntry]:
    return [
        DataDiligenceExceptionRegisterEntry(
            exception_key=f"exception_{action.action_key}",
            blocking_check_key=action.blocking_check_key,
            display_name=action.display_name,
            severity_code=action.priority_code,
            owner_area=action.owner_area,
            source_field=_EXCEPTION_SOURCE_FIELD_BY_CHECK_KEY.get(
                action.blocking_check_key,
                "quality_checks",
            ),
            related_artifact=_EXCEPTION_ARTIFACT_BY_CHECK_KEY.get(
                action.blocking_check_key,
                "remediation-actions.json",
            ),
            blocks_close=True,
            detail_text=action.impact_text,
            next_action=action.recommended_next_step,
            provider_write_executed=False,
        )
        for action in snapshot.acquisition_readiness_gate.remediation_actions
    ]


def _risk_matrix_key_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _diligence_risk_matrix(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataDiligenceRiskMatrixEntry]:
    groups: dict[
        tuple[RemediationPriority, str, str],
        list[DataDiligenceExceptionRegisterEntry],
    ] = defaultdict(list)
    for exception in snapshot.diligence_exception_register:
        key = (
            exception.severity_code,
            exception.owner_area,
            exception.related_artifact,
        )
        groups[key].append(exception)

    entries: list[DataDiligenceRiskMatrixEntry] = []
    for (severity, owner_area, related_artifact), exceptions in sorted(
        groups.items(),
        key=lambda item: (
            _RISK_SEVERITY_RANK[item[0][0]],
            item[0][1],
            item[0][2],
        ),
    ):
        exception_keys = [exception.exception_key for exception in exceptions]
        entries.append(
            DataDiligenceRiskMatrixEntry(
                matrix_key=(
                    "risk_"
                    f"{severity}_"
                    f"{_risk_matrix_key_part(owner_area)}_"
                    f"{_risk_matrix_key_part(related_artifact)}"
                ),
                severity_code=severity,
                owner_area=owner_area,
                related_artifact=related_artifact,
                exception_count=len(exceptions),
                representative_exception_keys=exception_keys,
                risk_label=_RISK_LABEL_BY_SEVERITY[severity],
                buyer_implication=(
                    f"{len(exceptions)} {severity} exception(s) in {owner_area} "
                    f"affect {related_artifact} and block buyer close."
                ),
                recommended_next_action=(
                    f"Resolve {', '.join(exception_keys)}, then regenerate the "
                    "evidence snapshot."
                ),
                blocks_close=any(exception.blocks_close for exception in exceptions),
                provider_write_executed=False,
            )
        )
    return entries


def _diligence_close_proof_plan(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataDiligenceCloseProofPlanEntry]:
    return [
        DataDiligenceCloseProofPlanEntry(
            proof_key=f"proof_{risk.matrix_key}",
            severity_code=risk.severity_code,
            owner_area=risk.owner_area,
            related_artifact=risk.related_artifact,
            exception_count=risk.exception_count,
            required_proof_artifact=risk.related_artifact,
            acceptance_criteria=(
                f"All {risk.exception_count} exception(s) for {risk.owner_area} "
                f"are resolved and {risk.related_artifact} is regenerated without "
                "raw content or stable IDs."
            ),
            verification_method=(
                "Regenerate the evidence snapshot and run python "
                "scripts/verify_evidence_snapshot.py <snapshot.json>."
            ),
            buyer_close_dependency=_CLOSE_DEPENDENCY_BY_SEVERITY[
                risk.severity_code
            ],
            close_gate_status="blocked" if risk.blocks_close else "ready",
            next_action=risk.recommended_next_action,
            provider_write_executed=False,
        )
        for risk in snapshot.diligence_risk_matrix
    ]


def _diligence_close_decision_summary(
    snapshot: DataEvidenceSnapshotResponse,
) -> DataDiligenceCloseDecisionSummary:
    proof_plan = snapshot.diligence_close_proof_plan
    blocked = [
        item for item in proof_plan if item.close_gate_status == "blocked"
    ]
    ready = [item for item in proof_plan if item.close_gate_status == "ready"]
    required_artifacts = sorted(
        {item.required_proof_artifact for item in proof_plan}
    )
    critical_blocker_count = sum(
        1 for item in blocked if item.severity_code == "critical"
    )
    high_blocker_count = sum(
        1 for item in blocked if item.severity_code == "high"
    )
    medium_blocker_count = sum(
        1 for item in blocked if item.severity_code == "medium"
    )
    highest_severity: DiligenceCloseSeverity = "none"
    if critical_blocker_count:
        highest_severity = "critical"
    elif high_blocker_count:
        highest_severity = "high"
    elif medium_blocker_count:
        highest_severity = "medium"

    if blocked:
        buyer_summary_text = (
            f"Close remains blocked by {len(blocked)} proof requirement(s) "
            f"across {len(required_artifacts)} required artifact(s)."
        )
        next_action_text = (
            "Resolve critical and high proof blockers, regenerate the "
            "evidence snapshot, and verify the copied JSON with the offline "
            "snapshot verifier."
        )
    else:
        buyer_summary_text = (
            f"Close is ready with {len(ready)} verified proof requirement(s) "
            f"across {len(required_artifacts)} required artifact(s)."
        )
        next_action_text = (
            "Share the verified evidence snapshot and close proof artifacts "
            "with buyer reviewers."
        )

    return DataDiligenceCloseDecisionSummary(
        summary_key="buyer_close_decision",
        decision_code="close_blocked" if blocked else "ready_to_close",
        total_proof_count=len(proof_plan),
        blocked_proof_count=len(blocked),
        ready_proof_count=len(ready),
        critical_blocker_count=critical_blocker_count,
        high_blocker_count=high_blocker_count,
        medium_blocker_count=medium_blocker_count,
        required_artifact_count=len(required_artifacts),
        required_artifacts=required_artifacts,
        highest_severity=highest_severity,
        snapshot_verification_required=bool(proof_plan),
        buyer_summary_text=buyer_summary_text,
        next_action_text=next_action_text,
        provider_write_executed=False,
    )


def _diligence_close_artifact_review_queue(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataDiligenceCloseArtifactReviewQueueEntry]:
    groups: dict[str, list[DataDiligenceCloseProofPlanEntry]] = defaultdict(list)
    for proof in snapshot.diligence_close_proof_plan:
        groups[proof.required_proof_artifact].append(proof)

    entries: list[DataDiligenceCloseArtifactReviewQueueEntry] = []
    for artifact, proofs in sorted(groups.items()):
        blocked_count = sum(
            1 for proof in proofs if proof.close_gate_status == "blocked"
        )
        ready_count = len(proofs) - blocked_count
        highest_severity: DiligenceCloseSeverity = min(
            (proof.severity_code for proof in proofs),
            key=lambda severity: _RISK_SEVERITY_RANK[severity],
        )
        buyer_review_role = _ARTIFACT_REVIEW_ROLE_BY_SEVERITY[highest_severity]
        review_status: DiligenceArtifactReviewStatus = (
            "blocked" if blocked_count else "ready_for_review"
        )
        next_actions = list(dict.fromkeys(proof.next_action for proof in proofs))
        entries.append(
            DataDiligenceCloseArtifactReviewQueueEntry(
                queue_key=f"review_{_risk_matrix_key_part(artifact)}",
                required_proof_artifact=artifact,
                owner_areas=sorted({proof.owner_area for proof in proofs}),
                proof_count=len(proofs),
                blocked_proof_count=blocked_count,
                ready_proof_count=ready_count,
                highest_severity=highest_severity,
                buyer_review_role=buyer_review_role,
                review_status=review_status,
                acceptance_summary=(
                    f"{len(proofs)} proof requirement(s) for {artifact} need "
                    f"{buyer_review_role} review before close."
                ),
                next_action="; ".join(next_actions),
                snapshot_verification_required=True,
                provider_write_executed=False,
            )
        )
    return entries


def _diligence_close_owner_handoff_queue(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataDiligenceCloseOwnerHandoffQueueEntry]:
    groups: dict[str, list[DataDiligenceCloseProofPlanEntry]] = defaultdict(list)
    for proof in snapshot.diligence_close_proof_plan:
        groups[proof.owner_area].append(proof)

    entries: list[DataDiligenceCloseOwnerHandoffQueueEntry] = []
    for owner_area, proofs in sorted(groups.items()):
        blocked_count = sum(
            1 for proof in proofs if proof.close_gate_status == "blocked"
        )
        ready_count = len(proofs) - blocked_count
        highest_severity: DiligenceCloseSeverity = min(
            (proof.severity_code for proof in proofs),
            key=lambda severity: _RISK_SEVERITY_RANK[severity],
        )
        buyer_review_roles = [
            _ARTIFACT_REVIEW_ROLE_BY_SEVERITY[severity]
            for severity in sorted(
                {proof.severity_code for proof in proofs},
                key=lambda severity: _RISK_SEVERITY_RANK[severity],
            )
        ]
        related_artifacts = sorted(
            {proof.required_proof_artifact for proof in proofs}
        )
        handoff_status: DiligenceOwnerHandoffStatus = (
            "blocked" if blocked_count else "ready_for_handoff"
        )
        next_actions = list(dict.fromkeys(proof.next_action for proof in proofs))
        entries.append(
            DataDiligenceCloseOwnerHandoffQueueEntry(
                handoff_key=f"handoff_{_risk_matrix_key_part(owner_area)}",
                owner_area=owner_area,
                related_artifacts=related_artifacts,
                proof_count=len(proofs),
                blocked_proof_count=blocked_count,
                ready_proof_count=ready_count,
                highest_severity=highest_severity,
                buyer_review_roles=buyer_review_roles,
                handoff_status=handoff_status,
                acceptance_summary=(
                    f"{len(proofs)} proof requirement(s) assigned to {owner_area} "
                    f"affect {len(related_artifacts)} artifact(s) before close."
                ),
                next_action="; ".join(next_actions),
                snapshot_verification_required=True,
                provider_write_executed=False,
            )
        )
    return entries


def _diligence_close_traceability_map(
    snapshot: DataEvidenceSnapshotResponse,
) -> list[DataDiligenceCloseTraceabilityMapEntry]:
    risk_by_key = {risk.matrix_key: risk for risk in snapshot.diligence_risk_matrix}
    manifest_by_file = {
        item.file_name: item for item in snapshot.data_room_package_manifest
    }
    artifact_review_by_artifact = {
        item.required_proof_artifact: item
        for item in snapshot.diligence_close_artifact_review_queue
    }
    owner_handoff_by_owner = {
        item.owner_area: item for item in snapshot.diligence_close_owner_handoff_queue
    }

    entries: list[DataDiligenceCloseTraceabilityMapEntry] = []
    for proof in snapshot.diligence_close_proof_plan:
        risk_key = proof.proof_key.removeprefix("proof_")
        risk = risk_by_key[risk_key]
        manifest = manifest_by_file[proof.required_proof_artifact]
        artifact_review = artifact_review_by_artifact[
            proof.required_proof_artifact
        ]
        owner_handoff = owner_handoff_by_owner[proof.owner_area]
        source_field = manifest.source_field
        data_room_artifact = proof.required_proof_artifact
        entries.append(
            DataDiligenceCloseTraceabilityMapEntry(
                trace_key=f"trace_{risk_key}",
                source_field=source_field,
                data_room_artifact=data_room_artifact,
                manifest_key=manifest.manifest_key,
                exception_keys=risk.representative_exception_keys,
                risk_key=risk_key,
                proof_key=proof.proof_key,
                artifact_review_key=artifact_review.queue_key,
                owner_handoff_key=owner_handoff.handoff_key,
                owner_area=proof.owner_area,
                severity_code=proof.severity_code,
                exception_count=proof.exception_count,
                close_gate_status=proof.close_gate_status,
                buyer_review_roles=owner_handoff.buyer_review_roles,
                trace_summary=(
                    f"{source_field} feeds {data_room_artifact} for "
                    f"{proof.owner_area} close proof traceability."
                ),
                next_action=proof.next_action,
                snapshot_verification_required=True,
                provider_write_executed=False,
            )
        )
    return entries


def _acquisition_remediation_actions(
    quality_checks: list[DataQualityCheck],
) -> list[DataAcquisitionRemediationAction]:
    actions: list[DataAcquisitionRemediationAction] = []
    for check in quality_checks:
        if check.status_code == "pass" and check.issue_count <= 0:
            continue
        action = _REMEDIATION_ACTIONS_BY_CHECK_KEY.get(check.check_key)
        if action is None:
            continue
        actions.append(
            DataAcquisitionRemediationAction(
                blocking_check_key=check.check_key,
                provider_write_executed=False,
                **action,
            )
        )
    return sorted(actions, key=lambda action: action.priority_rank)


def _quality_check_completion_percent(check: DataQualityCheck) -> int:
    if check.total_count <= 0:
        return 0
    passed_count = max(check.total_count - check.issue_count, 0)
    return round((passed_count / check.total_count) * 100)


def _acquisition_readiness_kpis(
    quality_checks: list[DataQualityCheck],
) -> list[DataAcquisitionReadinessKpi]:
    kpis: list[DataAcquisitionReadinessKpi] = []
    for check in quality_checks:
        target = _ACQUISITION_KPI_TARGETS_BY_CHECK_KEY.get(check.check_key)
        if target is None:
            continue
        current_percent = _quality_check_completion_percent(check)
        target_percent = int(target["target_percent"])
        kpis.append(
            DataAcquisitionReadinessKpi(
                source_check_key=check.check_key,
                current_percent=current_percent,
                target_met=(
                    check.status_code == "pass" and current_percent >= target_percent
                ),
                status_code=check.status_code,
                provider_write_executed=False,
                **target,
            )
        )
    return sorted(kpis, key=lambda kpi: kpi.priority_rank)


def _acquisition_decision_summary(
    *,
    kpis: list[DataAcquisitionReadinessKpi],
    remediation_actions: list[DataAcquisitionRemediationAction],
    evidence_packet_ready: bool,
    snapshot_verification_ready: bool,
) -> DataAcquisitionDecisionSummary:
    target_gap_count = sum(1 for kpi in kpis if not kpi.target_met)
    critical_action_count = sum(
        1 for action in remediation_actions if action.priority_code == "critical"
    )
    high_action_count = sum(
        1 for action in remediation_actions if action.priority_code == "high"
    )
    medium_action_count = sum(
        1 for action in remediation_actions if action.priority_code == "medium"
    )
    if not evidence_packet_ready or not snapshot_verification_ready:
        recommendation_code: DiligenceRecommendation = "insufficient_evidence"
        risk_level: DiligenceRiskLevel = "high"
        headline_text = "Evidence is insufficient for buyer diligence."
        next_step_text = (
            "Generate the evidence packet and snapshot verification before sharing "
            "diligence materials."
        )
    elif critical_action_count > 0 or target_gap_count > 0:
        recommendation_code = "remediate_before_close"
        risk_level = "high" if critical_action_count > 0 else "medium"
        headline_text = "Remediate acquisition evidence gaps before close."
        next_step_text = (
            "Resolve critical and high remediation actions, then regenerate the "
            "diligence evidence snapshot."
        )
    else:
        recommendation_code = "ready_for_diligence"
        risk_level = "low"
        headline_text = "Evidence is ready for buyer diligence review."
        next_step_text = (
            "Share the verified evidence snapshot with buyer diligence reviewers."
        )
    return DataAcquisitionDecisionSummary(
        summary_key="buyer_diligence_decision",
        recommendation_code=recommendation_code,
        risk_level=risk_level,
        target_gap_count=target_gap_count,
        critical_action_count=critical_action_count,
        high_action_count=high_action_count,
        medium_action_count=medium_action_count,
        headline_text=headline_text,
        next_step_text=next_step_text,
        provider_write_executed=False,
    )


def _acquisition_readiness_gate(
    *,
    quality_checks: list[DataQualityCheck],
    content_graph_evidence_samples: list[DataContentGraphEvidenceSample],
    knowledge_graph_evidence_samples: list[DataKnowledgeGraphEvidenceSample],
    semantic_relation_evidence_samples: list[DataSemanticRelationEvidenceSample],
) -> DataAcquisitionReadinessGate:
    passed_checks = sum(1 for check in quality_checks if check.status_code == "pass")
    pending_checks = sum(
        1 for check in quality_checks if check.status_code == "pending"
    )
    issue_check_keys = [
        check.check_key
        for check in quality_checks
        if check.status_code == "needs_attention" or check.issue_count > 0
    ]
    total_checks = len(quality_checks)
    readiness_score = round((passed_checks / total_checks) * 100) if total_checks else 0
    evidence_packet_ready = bool(
        content_graph_evidence_samples
        and knowledge_graph_evidence_samples
        and semantic_relation_evidence_samples
    )
    kpis = _acquisition_readiness_kpis(quality_checks)
    remediation_actions = _acquisition_remediation_actions(quality_checks)
    if issue_check_keys:
        state_code: AcquisitionReadinessState = "needs_attention"
        detail_text = (
            "Buyer evidence packet is generated, but blocking quality checks remain."
        )
    elif pending_checks > 0 or not evidence_packet_ready:
        state_code = "pending"
        detail_text = "Buyer evidence packet is waiting for pending quality evidence."
    else:
        state_code = "ready"
        detail_text = (
            "Buyer evidence packet has complete quality, graph, semantic, and "
            "snapshot verification evidence."
        )
    return DataAcquisitionReadinessGate(
        gate_key="buyer_evidence_readiness",
        display_name="Buyer evidence readiness",
        state_code=state_code,
        readiness_score=readiness_score,
        passed_checks=passed_checks,
        issue_checks=len(issue_check_keys),
        pending_checks=pending_checks,
        total_checks=total_checks,
        blocking_check_keys=issue_check_keys[:8],
        evidence_packet_ready=evidence_packet_ready,
        snapshot_verification_ready=True,
        provider_write_executed=False,
        kpis=kpis,
        decision_summary=_acquisition_decision_summary(
            kpis=kpis,
            remediation_actions=remediation_actions,
            evidence_packet_ready=evidence_packet_ready,
            snapshot_verification_ready=True,
        ),
        remediation_actions=remediation_actions,
        detail_text=detail_text,
    )


def _snapshot_digest_payload(
    snapshot: DataEvidenceSnapshotResponse,
) -> dict[str, object]:
    payload = snapshot.model_dump(mode="json")
    for field_name in SNAPSHOT_DIGEST_EXCLUDED_FIELDS:
        payload.pop(field_name, None)
    return payload


def _snapshot_digest_for(payload: dict[str, object]) -> str:
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


def _evidence_snapshot_from_surface(
    surface: DataQualitySurfaceResponse,
) -> DataEvidenceSnapshotResponse:
    snapshot = DataEvidenceSnapshotResponse(
        snapshot_version=SNAPSHOT_VERSION,
        generated_at=_datetime_to_utc_iso(datetime.now(timezone.utc)),
        audit_event="data.quality_surface.evidence_snapshot.viewed",
        scope_label="signed_workspace_scope",
        snapshot_digest="",
        digest_algorithm="sha256",
        canonical_payload_fields=[],
        privacy_redaction_policy=_snapshot_privacy_policy(),
        acquisition_readiness_gate=surface.acquisition_readiness_gate,
        validation_status=_snapshot_validation_status(surface.quality_checks),
        verification_handoff=_snapshot_verification_handoff(),
        parser_manifest_summary=_snapshot_parser_manifest_summary(),
        quality_checks=[
            DataEvidenceSnapshotQualityCheck(
                check_key=check.check_key,
                display_name=check.display_name,
                status_code=check.status_code,
                issue_count=check.issue_count,
                total_count=check.total_count,
                detail_text=check.detail_text,
            )
            for check in surface.quality_checks
        ],
        content_graph_topology_counts=[
            DataEvidenceSnapshotContentTopologyCount(
                source_kind=item.source_kind,
                segment_kind=item.segment_kind,
                object_count=item.object_count,
            )
            for item in surface.content_graph_breakdown
        ],
        knowledge_graph_topology_counts=[
            DataEvidenceSnapshotKnowledgeTopologyCount(
                source_kind=item.source_kind,
                edge_kind=item.edge_kind,
                object_count=item.object_count,
            )
            for item in surface.knowledge_graph_breakdown
        ],
        content_graph_evidence_samples=surface.content_graph_evidence_samples,
        knowledge_graph_evidence_samples=surface.knowledge_graph_evidence_samples,
        semantic_relation_evidence_samples=(
            surface.semantic_relation_evidence_samples
        ),
        semantic_extraction_manifest=surface.semantic_extraction_manifest,
    )
    snapshot = snapshot.model_copy(
        update={
            "evidence_packet_checklist": _evidence_packet_checklist(
                surface=surface,
                snapshot=snapshot,
            )
        }
    )
    snapshot = snapshot.model_copy(
        update={"data_room_package_manifest": _data_room_package_manifest(snapshot)}
    )
    snapshot = snapshot.model_copy(
        update={
            "diligence_exception_register": _diligence_exception_register(snapshot)
        }
    )
    snapshot = snapshot.model_copy(
        update={"diligence_risk_matrix": _diligence_risk_matrix(snapshot)}
    )
    snapshot = snapshot.model_copy(
        update={
            "diligence_close_proof_plan": _diligence_close_proof_plan(snapshot)
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "diligence_close_decision_summary": (
                _diligence_close_decision_summary(snapshot)
            )
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "diligence_close_artifact_review_queue": (
                _diligence_close_artifact_review_queue(snapshot)
            )
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "diligence_close_owner_handoff_queue": (
                _diligence_close_owner_handoff_queue(snapshot)
            )
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "diligence_close_traceability_map": (
                _diligence_close_traceability_map(snapshot)
            )
        }
    )
    digest_payload = _snapshot_digest_payload(snapshot)
    return snapshot.model_copy(
        update={
            "snapshot_digest": _snapshot_digest_for(digest_payload),
            "digest_algorithm": "sha256",
            "canonical_payload_fields": sorted(digest_payload),
        }
    )


def _safe_path_segment(value: str | None, fallback: str) -> str:
    cleaned = _safe_display_text(value, fallback)
    cleaned = cleaned.replace("\x00", "").replace("/", "-").replace("\\", "-")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    cleaned = cleaned.strip(" .-_")
    return cleaned[:96] or fallback


def _materialized_document_name(document: Document) -> str:
    return _safe_path_segment(document.document_name, "workspace-document")


def _materialized_document_target_path(document: Document) -> str:
    digest = hashlib.sha256(document.document_id.encode("utf-8")).hexdigest()[:8]
    filename = f"{_materialized_document_name(document)}-{digest}.md"
    return f"/Naruon/Data/{filename}"


# Document statuses whose stored content is not yet materializable parsed text
# (it may be a base64 binary payload awaiting a recognition/conversion worker).
_NON_MATERIALIZABLE_DOCUMENT_STATUSES = frozenset(
    {
        PDF_DOM_RECOGNITION_PENDING_STATUS,
        "hwp_conversion_pending",
    }
)


def _materialized_document_content(document: Document) -> str:
    return (document.document_content or "").strip()


def _document_content_chars(document: Document) -> int:
    return len((document.document_content or "").strip())


def _document_response(
    document: Document,
    *,
    audit_event: str,
    message: str,
) -> DataDocumentActionResponse:
    return DataDocumentActionResponse(
        document_id=document.document_id,
        workspace_id=document.workspace_id,
        document_name=document.document_name,
        document_type=document.document_type,
        document_status=document.document_status,
        content_chars=_document_content_chars(document),
        provider_write_executed=False,
        provenance="server-authoritative",
        audit_event=audit_event,
        message=message,
    )


def _document_webdav_materialization_response(
    document: Document,
    source_result: dict,
) -> dict:
    return {
        "intent": "document_webdav_materialization",
        "status": "intent_ready",
        "document_id": document.document_id,
        "workspace_id": document.workspace_id,
        "document_name": _materialized_document_name(document),
        "document_type": document.document_type,
        "source_id": source_result["source_id"],
        "target_label": source_result["target_label"],
        "target_path": _materialized_document_target_path(document),
        "requires_if_match": source_result["requires_if_match"],
        "if_match": source_result.get("if_match"),
        "provenance": "server-authoritative",
        "provider_write_executed": False,
        "audit_event": "data.document.webdav_materialization_intent.created",
        "runner_request_id": None,
        "provider_status": None,
        "error_code": None,
        "retry_item_uid": None,
        "message": (
            "Workspace document WebDAV materialization intent recorded; "
            "no provider write executed."
        ),
    }


def _document_webdav_runner_command(
    document: Document, intent_result: dict
) -> dict[str, object]:
    return {
        "action": "write_webdav",
        "account": intent_result["source_id"],
        "source_id": intent_result["source_id"],
        "target_path": intent_result["target_path"],
        "if_match": intent_result.get("if_match"),
        "content_type": "text/markdown; charset=utf-8",
        "content": _materialized_document_content(document),
    }


def _merge_document_webdav_dispatch_result(
    intent_result: dict,
    dispatch_result: dict,
) -> dict:
    result = dict(intent_result)
    result["status"] = str(dispatch_result.get("status") or "error")
    result["provider_write_executed"] = bool(
        dispatch_result.get("provider_write_executed", False)
    )
    result["runner_request_id"] = dispatch_result.get("request_id")
    result["provider_status"] = dispatch_result.get("provider_status")
    result["error_code"] = dispatch_result.get("error_code")
    result["retry_item_uid"] = dispatch_result.get("retry_item_uid")
    result["audit_event"] = (
        "data.document.webdav_materialization.executed"
        if result["provider_write_executed"]
        else "data.document.webdav_materialization.dispatch_failed"
    )
    result["message"] = (
        "Workspace document WebDAV materialization executed by the connector."
        if result["provider_write_executed"]
        else "Workspace document WebDAV materialization dispatch failed."
    )
    return result


def _opaque_asset_key(email: Email, attachment: Attachment) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                email.user_id,
                email.organization_id,
                email.message_id,
                attachment.filename,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"asset_{digest[:24]}"


def _opaque_thread_key(email: Email) -> str:
    if not email.thread_id:
        return "thread_missing"
    digest = hashlib.sha256(email.thread_id.encode("utf-8")).hexdigest()
    return f"thread_{digest[:16]}"


def _can_read_org_scope(auth_context: AuthContext) -> bool:
    return is_admin_role(auth_context.role) and auth_context.organization_id is not None


def _owner_scope_statement(model, auth_context: AuthContext):
    statement = select(model)
    if hasattr(model, "workspace_id"):
        statement = statement.where(model.workspace_id == auth_context.workspace_id)
    if _can_read_org_scope(auth_context):
        return statement.where(model.organization_id == auth_context.organization_id)
    organization_filter = (
        model.organization_id == auth_context.organization_id
        if auth_context.organization_id is not None
        else model.organization_id.is_(None)
    )
    return statement.where(model.user_id == auth_context.user_id, organization_filter)


def _email_scope_filter(auth_context: AuthContext) -> EmailScopeFilter:
    # workspace_id is the finest-grained scope and is applied unconditionally,
    # mirroring _owner_scope_statement's pattern for every other
    # workspace_id-bearing model: even an organization admin is scoped to
    # their own workspace, not every workspace in the organization.
    workspace_filter = Email.workspace_id == auth_context.workspace_id
    if _can_read_org_scope(auth_context):
        organization_filter = Email.organization_id == auth_context.organization_id
        return (workspace_filter, organization_filter, organization_filter)
    organization_filter = (
        Email.organization_id == auth_context.organization_id
        if auth_context.organization_id is not None
        else Email.organization_id.is_(None)
    )
    return (workspace_filter, Email.user_id == auth_context.user_id, organization_filter)


async def _scoped_rows(db: AsyncSession, statement):
    result = await db.execute(statement)
    return list(result.scalars().all())


async def _count_scalar(db: AsyncSession, statement) -> int:
    result = await db.execute(statement)
    return int(result.scalar_one() or 0)


async def _get_workspace_document(
    db: AsyncSession,
    auth_context: AuthContext,
    document_id: str,
) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.document_id == document_id,
            Document.workspace_id == auth_context.workspace_id,
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def _get_scoped_attachment(
    db: AsyncSession,
    auth_context: AuthContext,
    attachment_uid: str,
    *,
    lock: bool = False,
) -> Attachment:
    # Attachment carries no workspace_id/user_id/organization_id of its own --
    # it is scoped through its parent Email, same as every other
    # attachment-facing query in this file.
    email_scope = _email_scope_filter(auth_context)
    statement = (
        select(Attachment)
        .join(Email)
        .where(Attachment.attachment_uid == attachment_uid, *email_scope)
    )
    if lock:
        # Concurrent read-then-write status transitions (e.g. reparse-intent)
        # must not race unlocked: without this, a stale request that already
        # read an earlier status could commit after a concurrent request (or
        # the reparse worker) has moved the row further along, silently
        # clobbering that newer result. Scoped to Attachment only so this
        # doesn't also lock the joined Email row.
        statement = statement.with_for_update(of=Attachment)
    result = await db.execute(statement)
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


def _attachment_response(
    attachment: Attachment,
    *,
    audit_event: str,
    message: str,
) -> DataAttachmentActionResponse:
    return DataAttachmentActionResponse(
        attachment_uid=attachment.attachment_uid,
        filename=attachment.filename,
        content_type=attachment.content_type,
        parse_content_type=attachment.parse_content_type,
        parse_status=attachment.parse_status,
        parse_error_code=attachment.parse_error_code,
        provider_write_executed=False,
        provenance="server-authoritative",
        audit_event=audit_event,
        message=message,
    )


def _status_from_ratio(total_count: int, ready_count: int) -> SurfaceStatus:
    if total_count <= 0:
        return "pending"
    if ready_count <= 0:
        return "needs_attention"
    if ready_count < total_count:
        return "running"
    return "ready"


def _progress_percent(total_count: int, ready_count: int) -> int:
    if total_count <= 0:
        return 0
    return max(0, min(100, round((ready_count / total_count) * 100)))


def _quality_status(total_count: int, issue_count: int) -> QualityStatus:
    if total_count <= 0:
        return "pending"
    return "pass" if issue_count == 0 else "needs_attention"


def _quality_detail(
    *,
    total_count: int,
    issue_count: int,
    ready_text: str,
    empty_text: str,
    issue_text: str,
) -> str:
    if total_count <= 0:
        return empty_text
    if issue_count == 0:
        return ready_text
    return issue_text


def _repository_summaries(
    webdav_accounts: list[WebdavAccount],
    project_folders: list[ProjectFolder],
    email_count: int,
    attachment_count: int,
    document_count: int,
) -> list[DataRepositorySummary]:
    repositories: list[DataRepositorySummary] = [
        DataRepositorySummary(
            source_id="email_repository",
            repository_type="email_repository",
            display_name="Scoped email archive",
            object_count=email_count,
            writeback_enabled=None,
            evidence_source="emails",
            provider_write_executed=False,
        ),
        DataRepositorySummary(
            source_id="attachment_repository",
            repository_type="attachment_repository",
            display_name="Scoped attachment archive",
            object_count=attachment_count,
            writeback_enabled=None,
            evidence_source="attachments",
            provider_write_executed=False,
        ),
        DataRepositorySummary(
            source_id="document_repository",
            repository_type="document_repository",
            display_name="Scoped document repository",
            object_count=document_count,
            writeback_enabled=None,
            evidence_source="documents",
            provider_write_executed=False,
        ),
    ]
    repositories.extend(
        DataRepositorySummary(
            source_id=account.source_uid,
            repository_type="webdav_account",
            display_name="Customer WebDAV account",
            object_count=0,
            writeback_enabled=bool(account.writeback_enabled),
            evidence_source="webdav_accounts",
            provider_write_executed=False,
        )
        for account in webdav_accounts
    )
    repositories.extend(
        DataRepositorySummary(
            source_id=folder.folder_uid,
            repository_type="project_folder",
            display_name=folder.project_name,
            object_count=0,
            writeback_enabled=None,
            evidence_source="project_folders",
            provider_write_executed=False,
        )
        for folder in project_folders
    )
    return repositories


def _attachment_repository_assets(
    rows: list[AttachmentAssetRow],
) -> list[DataRepositoryAsset]:
    assets: list[DataRepositoryAsset] = []
    for attachment, email in rows:
        content_chars = len((attachment.content or "").strip())
        has_thread = bool((email.thread_id or "").strip())
        state_code: RepositoryAssetState = (
            "ready" if content_chars > 0 and has_thread else "needs_attention"
        )
        detail_parts: list[str] = []
        if content_chars <= 0:
            detail_parts.append("content extraction pending")
        if not has_thread:
            detail_parts.append("canonical thread pending")
        if not detail_parts:
            detail_parts.append("content and thread evidence ready")
        assets.append(
            DataRepositoryAsset(
                asset_key=_opaque_asset_key(email, attachment),
                asset_type="email_attachment",
                display_name=_safe_display_text(
                    attachment.filename, "email attachment"
                ),
                source_label=_safe_display_text(email.subject, "untitled email"),
                state_code=state_code,
                detail_text=", ".join(detail_parts),
                content_chars=content_chars,
                captured_at=_datetime_to_utc_iso(email.date),
                evidence_source="attachments.content, emails.thread_id",
                thread_key=_opaque_thread_key(email),
                provider_write_executed=False,
            )
        )
    return assets


def _document_repository_assets(documents: list[Document]) -> list[DataRepositoryAsset]:
    assets: list[DataRepositoryAsset] = []
    for document in documents:
        content_chars = _document_content_chars(document)
        pending_statuses = {
            "embedding_pending",
            "hwp_conversion_pending",
            PDF_DOM_RECOGNITION_PENDING_STATUS,
        }
        state_code: RepositoryAssetState = (
            "needs_attention"
            if content_chars <= 0 or document.document_status in pending_statuses
            else "ready"
        )
        assets.append(
            DataRepositoryAsset(
                asset_key=document.document_id,
                asset_type="workspace_document",
                display_name=_safe_display_text(
                    document.document_name,
                    "workspace document",
                ),
                source_label="Workspace document",
                state_code=state_code,
                detail_text=f"document status: {document.document_status}",
                content_chars=content_chars,
                captured_at=_datetime_to_utc_iso(document.created_at),
                evidence_source="documents.document_status",
                thread_key="workspace_document",
                provider_write_executed=False,
            )
        )
    return assets


def _pipeline_stages(
    *,
    source_count: int,
    email_count: int,
    attachment_count: int,
    missing_thread_count: int,
    embedded_total: int,
    object_total: int,
    segmented_email_count: int,
    content_segment_count: int,
    edged_email_count: int,
    knowledge_graph_edge_count: int,
    parsed_attachment_count: int,
    unparsed_attachment_count: int,
    connector_event_count: int,
) -> list[DataPipelineStage]:
    thread_ready = max(0, email_count - missing_thread_count)
    return [
        DataPipelineStage(
            stage_key="source_registry",
            display_name="Source registry",
            status_code="ready" if source_count > 0 else "no_source",
            progress_percent=100 if source_count > 0 else 0,
            evidence_source="webdav_accounts, project_folders",
            detail_text=f"{source_count} customer-owned sources are in scope.",
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="ingestion_inventory",
            display_name="Ingestion inventory",
            status_code="ready" if email_count + attachment_count > 0 else "no_source",
            progress_percent=100 if email_count + attachment_count > 0 else 0,
            evidence_source="emails, attachments",
            detail_text=(
                f"{email_count} emails and {attachment_count} attachments "
                "are visible in the signed workspace scope."
            ),
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="canonical_threading",
            display_name="Canonical threading",
            status_code=_status_from_ratio(email_count, thread_ready),
            progress_percent=_progress_percent(email_count, thread_ready),
            evidence_source="emails.thread_id",
            detail_text=f"{missing_thread_count} emails need canonical thread ids.",
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="embedding_inventory",
            display_name="Embedding inventory",
            status_code=_status_from_ratio(object_total, embedded_total),
            progress_percent=_progress_percent(object_total, embedded_total),
            evidence_source="emails.embedding, attachments.embedding",
            detail_text=f"{embedded_total} of {object_total} objects have vectors.",
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="content_graph_inventory",
            display_name="Content graph inventory",
            status_code=_status_from_ratio(email_count, segmented_email_count),
            progress_percent=_progress_percent(email_count, segmented_email_count),
            evidence_source="content_segments",
            detail_text=(
                f"{segmented_email_count} of {email_count} emails have paragraph "
                f"segments; {content_segment_count} segments are stored."
            ),
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="knowledge_graph_inventory",
            display_name="Knowledge graph inventory",
            status_code=_status_from_ratio(email_count, edged_email_count),
            progress_percent=_progress_percent(email_count, edged_email_count),
            evidence_source="knowledge_graph_edges",
            detail_text=(
                f"{edged_email_count} of {email_count} emails have graph edges; "
                f"{knowledge_graph_edge_count} edges are stored."
            ),
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="attachment_parse_inventory",
            display_name="Attachment parse inventory",
            status_code=_status_from_ratio(attachment_count, parsed_attachment_count),
            progress_percent=_progress_percent(
                attachment_count,
                parsed_attachment_count,
            ),
            evidence_source="email_attachments.parse_status",
            detail_text=(
                f"{parsed_attachment_count} of {attachment_count} attachments "
                "are parseable; "
                f"{unparsed_attachment_count} attachments need parser coverage."
            ),
            provider_write_executed=False,
        ),
        DataPipelineStage(
            stage_key="connector_observability",
            display_name="Connector observability",
            status_code="ready" if connector_event_count > 0 else "pending",
            progress_percent=100 if connector_event_count > 0 else 0,
            evidence_source="connector_signal_events",
            detail_text=f"{connector_event_count} connector events are in scope.",
            provider_write_executed=False,
        ),
    ]


def _embedding_collections(
    *,
    email_count: int,
    embedded_email_count: int,
    attachment_count: int,
    embedded_attachment_count: int,
) -> list[DataEmbeddingCollection]:
    model_name = settings.OPENAI_EMBEDDING_MODEL
    return [
        DataEmbeddingCollection(
            collection_key="emails_embedding",
            display_name="Email vectors",
            object_count=email_count,
            embedded_count=embedded_email_count,
            embedding_model=model_name,
            vector_dimensions=DATA_VECTOR_DIMENSIONS,
            status_code=_status_from_ratio(email_count, embedded_email_count),
            evidence_source="emails.embedding",
            provider_write_executed=False,
        ),
        DataEmbeddingCollection(
            collection_key="attachments_embedding",
            display_name="Attachment vectors",
            object_count=attachment_count,
            embedded_count=embedded_attachment_count,
            embedding_model=model_name,
            vector_dimensions=DATA_VECTOR_DIMENSIONS,
            status_code=_status_from_ratio(
                attachment_count,
                embedded_attachment_count,
            ),
            evidence_source="attachments.embedding",
            provider_write_executed=False,
        ),
    ]


def _check_thread_id_integrity(
    email_count: int, missing_thread_count: int
) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="thread_id_integrity",
        display_name="Thread id integrity",
        status_code=_quality_status(email_count, missing_thread_count),
        issue_count=missing_thread_count,
        total_count=email_count,
        evidence_source="emails.thread_id",
        detail_text=_quality_detail(
            total_count=email_count,
            issue_count=missing_thread_count,
            ready_text="All scoped emails have canonical thread ids.",
            empty_text="No scoped emails are available yet.",
            issue_text="Some scoped emails need canonical thread ids.",
        ),
        provider_write_executed=False,
    )


def _check_dedupe_fingerprint(
    email_count: int, missing_fingerprint_count: int
) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="dedupe_fingerprint",
        display_name="Dedupe fingerprint",
        status_code=_quality_status(email_count, missing_fingerprint_count),
        issue_count=missing_fingerprint_count,
        total_count=email_count,
        evidence_source="emails.fingerprint",
        detail_text=_quality_detail(
            total_count=email_count,
            issue_count=missing_fingerprint_count,
            ready_text="All scoped emails have duplicate-detection fingerprints.",
            empty_text="No scoped emails are available yet.",
            issue_text="Some scoped emails need duplicate-detection fingerprints.",
        ),
        provider_write_executed=False,
    )


def _check_attachment_content(
    attachment_count: int, blank_attachment_count: int
) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="attachment_content",
        display_name="Attachment content",
        status_code=_quality_status(attachment_count, blank_attachment_count),
        issue_count=blank_attachment_count,
        total_count=attachment_count,
        evidence_source="attachments.content",
        detail_text=_quality_detail(
            total_count=attachment_count,
            issue_count=blank_attachment_count,
            ready_text="All scoped attachments have extracted content.",
            empty_text="No scoped attachments are available yet.",
            issue_text="Some scoped attachments need extracted content.",
        ),
        provider_write_executed=False,
    )


def _check_source_registry_coverage(source_count: int) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="source_registry",
        display_name="Source registry coverage",
        status_code="pass" if source_count > 0 else "pending",
        issue_count=0 if source_count > 0 else 1,
        total_count=max(1, source_count),
        evidence_source="webdav_accounts, project_folders",
        detail_text=(
            "Customer-owned repositories are visible."
            if source_count > 0
            else "No customer-owned repositories are visible yet."
        ),
        provider_write_executed=False,
    )


def _check_content_graph_coverage(
    email_count: int,
    segmented_email_count: int,
) -> DataQualityCheck:
    issue_count = max(0, email_count - segmented_email_count)
    return DataQualityCheck(
        check_key="content_graph_coverage",
        display_name="Content graph coverage",
        status_code=_quality_status(email_count, issue_count),
        issue_count=issue_count,
        total_count=email_count,
        evidence_source="content_segments",
        detail_text=_quality_detail(
            total_count=email_count,
            issue_count=issue_count,
            ready_text="All scoped emails have DOM paragraph segments.",
            empty_text="No scoped emails are available yet.",
            issue_text="Some scoped emails need DOM paragraph segmentation.",
        ),
        provider_write_executed=False,
    )


def _check_knowledge_graph_coverage(
    email_count: int,
    edged_email_count: int,
) -> DataQualityCheck:
    issue_count = max(0, email_count - edged_email_count)
    return DataQualityCheck(
        check_key="knowledge_graph_coverage",
        display_name="Knowledge graph coverage",
        status_code=_quality_status(email_count, issue_count),
        issue_count=issue_count,
        total_count=email_count,
        evidence_source="knowledge_graph_edges",
        detail_text=_quality_detail(
            total_count=email_count,
            issue_count=issue_count,
            ready_text="All scoped emails have persisted knowledge graph edges.",
            empty_text="No scoped emails are available yet.",
            issue_text="Some scoped emails need persisted knowledge graph edges.",
        ),
        provider_write_executed=False,
    )


def _check_content_segment_text_readiness(
    total_count: int,
    issue_count: int,
) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="content_segment_text_readiness",
        display_name="Content segment text readiness",
        status_code=_quality_status(total_count, issue_count),
        issue_count=issue_count,
        total_count=total_count,
        evidence_source=CONTENT_SEGMENT_TEXT_READINESS_EVIDENCE_SOURCE,
        detail_text=_quality_detail(
            total_count=total_count,
            issue_count=issue_count,
            ready_text=(
                "All DOM paragraph segments have non-empty safe text and word counts."
            ),
            empty_text="No DOM paragraph segments are available yet.",
            issue_text=(
                "Some DOM paragraph segments need non-empty safe text and word counts."
            ),
        ),
        provider_write_executed=False,
    )


def _check_knowledge_graph_evidence_endpoint_readiness(
    total_count: int,
    issue_count: int,
) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="knowledge_graph_evidence_endpoint_readiness",
        display_name="Knowledge graph evidence endpoints",
        status_code=_quality_status(total_count, issue_count),
        issue_count=issue_count,
        total_count=total_count,
        evidence_source=KNOWLEDGE_GRAPH_EVIDENCE_ENDPOINT_READINESS_EVIDENCE_SOURCE,
        detail_text=_quality_detail(
            total_count=total_count,
            issue_count=issue_count,
            ready_text=(
                "All knowledge graph edges include paragraph segment evidence endpoints."
            ),
            empty_text="No knowledge graph edges are available yet.",
            issue_text=(
                "Some knowledge graph edges need paragraph segment evidence endpoints."
            ),
        ),
        provider_write_executed=False,
    )


def _check_semantic_kg_readiness(
    semantic_relation_count: int,
    source_backed_relation_count: int,
) -> DataQualityCheck:
    if source_backed_relation_count > 0:
        return DataQualityCheck(
            check_key="semantic_kg_readiness",
            display_name="Semantic KG readiness",
            status_code="pass",
            issue_count=0,
            total_count=max(1, semantic_relation_count),
            evidence_source=SEMANTIC_KG_READINESS_EVIDENCE_SOURCE,
            detail_text=(
                "Semantic entity/relation evidence is available for this workspace."
            ),
            provider_write_executed=False,
        )
    return DataQualityCheck(
        check_key="semantic_kg_readiness",
        display_name="Semantic KG readiness",
        status_code="pending",
        issue_count=0,
        total_count=1,
        evidence_source=SEMANTIC_KG_READINESS_EVIDENCE_SOURCE,
        detail_text=(
            "Semantic entity/relation extraction is gated until provenance, "
            "confidence, and correction-path evidence are configured."
        ),
        provider_write_executed=False,
    )


def _check_semantic_relation_source_backing(
    total_count: int,
    source_backed_count: int,
) -> DataQualityCheck:
    issue_count = max(0, total_count - source_backed_count)
    return DataQualityCheck(
        check_key="semantic_relation_source_backing",
        display_name="Semantic relation source backing",
        status_code=_quality_status(total_count, issue_count),
        issue_count=issue_count,
        total_count=total_count,
        evidence_source=SEMANTIC_RELATION_SOURCE_BACKING_EVIDENCE_SOURCE,
        detail_text=_quality_detail(
            total_count=total_count,
            issue_count=issue_count,
            ready_text=(
                "All semantic relations include source message or thread evidence."
            ),
            empty_text="No semantic relations are available yet.",
            issue_text=(
                "Some semantic relations need source message or thread evidence."
            ),
        ),
        provider_write_executed=False,
    )


def _check_attachment_parse_coverage(
    attachment_count: int,
    unparsed_attachment_count: int,
) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="attachment_parse_coverage",
        display_name="Attachment parse coverage",
        status_code=_quality_status(attachment_count, unparsed_attachment_count),
        issue_count=unparsed_attachment_count,
        total_count=attachment_count,
        evidence_source="email_attachments.parse_status",
        detail_text=_quality_detail(
            total_count=attachment_count,
            issue_count=unparsed_attachment_count,
            ready_text="All scoped attachments have parser coverage.",
            empty_text="No scoped attachments are available yet.",
            issue_text="Some scoped attachments need parser coverage.",
        ),
        provider_write_executed=False,
    )


def _check_connector_signal_coverage(connector_event_count: int) -> DataQualityCheck:
    return DataQualityCheck(
        check_key="connector_signal",
        display_name="Connector signal coverage",
        status_code="pass" if connector_event_count > 0 else "pending",
        issue_count=0 if connector_event_count > 0 else 1,
        total_count=max(1, connector_event_count),
        evidence_source="connector_signal_events",
        detail_text=(
            "Connector evidence is visible for this workspace."
            if connector_event_count > 0
            else "Connector jobs have not emitted workspace evidence yet."
        ),
        provider_write_executed=False,
    )


def _quality_checks(
    *,
    email_count: int,
    attachment_count: int,
    missing_thread_count: int,
    missing_fingerprint_count: int,
    blank_attachment_count: int,
    source_count: int,
    segmented_email_count: int,
    edged_email_count: int,
    content_segment_text_issue_count: int,
    content_segment_text_total_count: int,
    knowledge_graph_evidence_endpoint_issue_count: int,
    knowledge_graph_evidence_endpoint_total_count: int,
    semantic_relation_count: int,
    semantic_relation_source_backed_count: int,
    unparsed_attachment_count: int,
    connector_event_count: int,
) -> list[DataQualityCheck]:
    return [
        _check_thread_id_integrity(
            email_count=email_count,
            missing_thread_count=missing_thread_count,
        ),
        _check_dedupe_fingerprint(
            email_count=email_count,
            missing_fingerprint_count=missing_fingerprint_count,
        ),
        _check_attachment_content(
            attachment_count=attachment_count,
            blank_attachment_count=blank_attachment_count,
        ),
        _check_content_graph_coverage(
            email_count=email_count,
            segmented_email_count=segmented_email_count,
        ),
        _check_knowledge_graph_coverage(
            email_count=email_count,
            edged_email_count=edged_email_count,
        ),
        _check_content_segment_text_readiness(
            total_count=content_segment_text_total_count,
            issue_count=content_segment_text_issue_count,
        ),
        _check_knowledge_graph_evidence_endpoint_readiness(
            total_count=knowledge_graph_evidence_endpoint_total_count,
            issue_count=knowledge_graph_evidence_endpoint_issue_count,
        ),
        _check_semantic_kg_readiness(
            semantic_relation_count=semantic_relation_count,
            source_backed_relation_count=semantic_relation_source_backed_count,
        ),
        _check_semantic_relation_source_backing(
            total_count=semantic_relation_count,
            source_backed_count=semantic_relation_source_backed_count,
        ),
        _check_attachment_parse_coverage(
            attachment_count=attachment_count,
            unparsed_attachment_count=unparsed_attachment_count,
        ),
        _check_source_registry_coverage(source_count),
        _check_connector_signal_coverage(connector_event_count),
    ]


@router.post("/documents", response_model=DataDocumentActionResponse)
async def upload_data_document(
    request: DataDocumentUploadRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentActionResponse:
    document = Document(
        workspace_id=auth_context.workspace_id,
        organization_id=auth_context.organization_id,
        document_name=_safe_display_text(request.document_name, "workspace document"),
        document_type=_safe_document_type(request.document_type),
        document_content=request.document_content,
        document_status="uploaded",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return _document_response(
        document,
        audit_event="data.document.uploaded",
        message="Document stored in the signed workspace scope.",
    )


@router.post(
    "/documents/{document_id}/reparse", response_model=DataDocumentActionResponse
)
async def reparse_data_document(
    document_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentActionResponse:
    document = await _get_workspace_document(db, auth_context, document_id)
    document.document_status = "parsed"
    await db.commit()
    await db.refresh(document)
    return _document_response(
        document,
        audit_event="data.document.reparsed",
        message="Document parse metadata refreshed in the signed workspace scope.",
    )


@router.post(
    "/documents/{document_id}/embedding-regeneration-intent",
    response_model=DataDocumentActionResponse,
)
async def create_document_embedding_regeneration_intent(
    document_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentActionResponse:
    document = await _get_workspace_document(db, auth_context, document_id)
    document.document_status = "embedding_pending"
    await db.commit()
    await db.refresh(document)
    return _document_response(
        document,
        audit_event="data.document.embedding_regeneration_intent",
        message="Embedding regeneration intent recorded; no provider write executed.",
    )


@router.post(
    "/documents/{document_id}/hwp-conversion-intent",
    response_model=DataDocumentActionResponse,
)
async def create_document_hwp_conversion_intent(
    document_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentActionResponse:
    document = await _get_workspace_document(db, auth_context, document_id)
    document.document_status = "hwp_conversion_pending"
    await db.commit()
    await db.refresh(document)
    return _document_response(
        document,
        audit_event="data.document.hwp_conversion_intent",
        message="HWP conversion intent recorded; no provider write executed.",
    )


@router.post(
    "/documents/{document_id}/pdf-dom-recognition-intent",
    response_model=DataDocumentActionResponse,
)
async def create_document_pdf_dom_recognition_intent(
    document_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentActionResponse:
    document = await _get_workspace_document(db, auth_context, document_id)
    if (document.document_type or "").strip().lower() != "pdf":
        raise HTTPException(
            status_code=415,
            detail="PDF DOM recognition is only available for PDF documents.",
        )
    try:
        decode_pending_pdf_document_bytes(document)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Stored PDF payload is not valid for DOM recognition.",
        ) from exc
    document.organization_id = auth_context.organization_id
    document.document_status = PDF_DOM_RECOGNITION_PENDING_STATUS
    await db.commit()
    await db.refresh(document)
    return _document_response(
        document,
        audit_event="data.document.pdf_dom_recognition_intent",
        message=(
            "PDF DOM recognition intent recorded; the NewsDOM sidecar worker "
            "will land the structured DOM. No provider write executed."
        ),
    )


@router.post(
    "/attachments/{attachment_uid}/reparse-intent",
    response_model=DataAttachmentActionResponse,
)
async def create_attachment_reparse_intent(
    attachment_uid: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataAttachmentActionResponse:
    attachment = await _get_scoped_attachment(
        db, auth_context, attachment_uid, lock=True
    )
    if attachment.parse_status != CONTENT_TYPE_MISMATCH_QUARANTINED_STATUS:
        raise HTTPException(
            status_code=422,
            detail="Reparse intent is only available for quarantined attachments.",
        )
    attachment.parse_status = ATTACHMENT_REPARSE_PENDING_STATUS
    attachment.parse_error_code = None
    await db.commit()
    await db.refresh(attachment)
    return _attachment_response(
        attachment,
        audit_event="data.attachment.reparse_intent",
        message=(
            "Reparse intent recorded; a future worker pass re-evaluates this "
            "attachment. No synchronous re-parse executed."
        ),
    )


@router.post(
    "/documents/pdf-dom-recognition",
    response_model=DataDocumentActionResponse,
)
async def upload_document_for_pdf_dom_recognition(
    file: UploadFile = File(...),
    # Declared as multipart form data (not a query parameter) so a client
    # sending document_name alongside the file is honored.
    document_name: str | None = Form(None),
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentActionResponse:
    """Binary upload variant: accept a PDF, stash it pending, and defer the
    heavy NewsDOM recognition to the worker."""
    raw = await file.read(_MAX_PDF_DOM_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_PDF_DOM_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF upload is too large.")
    if not raw[:5] == b"%PDF-":
        raise HTTPException(
            status_code=415,
            detail="Only application/pdf uploads are supported for DOM recognition.",
        )
    document = Document(
        workspace_id=auth_context.workspace_id,
        organization_id=auth_context.organization_id,
        document_name=_safe_display_text(
            document_name or file.filename, "workspace document"
        ),
        document_type="pdf",
        document_content=base64.b64encode(raw).decode("ascii"),
        document_status=PDF_DOM_RECOGNITION_PENDING_STATUS,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return _document_response(
        document,
        audit_event="data.document.pdf_dom_recognition_upload",
        message=(
            "PDF stored pending NewsDOM DOM recognition; the worker will parse "
            "it into the content graph. No provider write executed."
        ),
    )


def decode_pending_pdf_document_bytes(document: Document) -> bytes:
    """Decode the base64 PDF payload stashed by the binary upload variant.

    Used by the recognition worker before calling the NewsDOM sidecar.
    """
    try:
        payload = base64.b64decode(
            (document.document_content or "").encode("ascii"), validate=True
        )
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise ValueError("Pending PDF document payload is not valid base64") from exc
    if len(payload) > _MAX_PDF_DOM_UPLOAD_BYTES:
        raise ValueError("Pending PDF document exceeds the upload size limit")
    if not payload.startswith(b"%PDF-"):
        raise ValueError("Pending PDF document payload is not a PDF")
    return payload


@router.post(
    "/documents/{document_id}/webdav-materialization-intent",
    response_model=DataDocumentWebdavMaterializationResponse,
)
async def create_document_webdav_materialization_intent(
    document_id: str,
    request: DataDocumentWebdavMaterializationRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataDocumentWebdavMaterializationResponse:
    document = await _get_workspace_document(db, auth_context, document_id)
    if document.document_status in _NON_MATERIALIZABLE_DOCUMENT_STATUSES:
        # A document whose recognition/conversion is still pending holds a
        # non-text payload (e.g. the base64 PDF stashed for the NewsDOM worker).
        # Materializing it as Markdown would write that raw payload to the
        # customer's WebDAV target. Refuse until recognition has landed real
        # parsed text.
        raise HTTPException(
            status_code=409,
            detail=(
                "Workspace document is still pending recognition; "
                "no materializable content yet."
            ),
        )
    if not _materialized_document_content(document):
        raise HTTPException(
            status_code=422,
            detail="Workspace document has no materializable content.",
        )

    source_result = await webdav_service.determine_webdav_writeback_intent_from_db(
        db,
        auth_context.user_id,
        auth_context.organization_id,
        auth_context.workspace_id,
        target_source_id=request.target_source_id,
    )
    if source_result.get("status") == "error":
        status_code = WEB_DAV_ERROR_STATUS_CODES.get(
            str(source_result.get("error_code") or ""),
            422,
        )
        raise HTTPException(
            status_code=status_code, detail=source_result.get("message")
        )

    result = _document_webdav_materialization_response(document, source_result)
    if request.execute_provider:
        dispatch_result = await runner_manager.dispatch_command(
            auth_context.organization_id,
            auth_context.workspace_id,
            _document_webdav_runner_command(document, result),
        )
        result = _merge_document_webdav_dispatch_result(result, dispatch_result)
    return DataDocumentWebdavMaterializationResponse(**result)


async def _get_email_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> EmailQualityStats:
    # ⚡ Bolt Optimization: Batching scalar counts using CASE
    # Impact: Reduces 7 sequential database queries down to 2, drastically cutting
    # latency from network roundtrips when fetching quality surface metrics.
    email_stats_result = await db.execute(
        select(
            func.count(Email.id),
            func.count(
                case((or_(Email.thread_id.is_(None), Email.thread_id == ""), 1))
            ),
            func.count(
                case((or_(Email.fingerprint.is_(None), Email.fingerprint == ""), 1))
            ),
            func.count(case((Email.embedding.is_not(None), 1))),
        ).where(*email_scope)
    )
    email_stats = email_stats_result.one_or_none()
    email_count = email_stats[0] if email_stats else 0
    missing_thread_count = email_stats[1] if email_stats else 0
    missing_fingerprint_count = email_stats[2] if email_stats else 0
    embedded_email_count = email_stats[3] if email_stats else 0
    return EmailQualityStats(
        count=email_count,
        missing_thread_count=missing_thread_count,
        missing_fingerprint_count=missing_fingerprint_count,
        embedded_count=embedded_email_count,
    )


async def _get_attachment_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> AttachmentQualityStats:
    attachment_stats_result = await db.execute(
        select(
            func.count(Attachment.id),
            func.count(
                case(
                    (
                        or_(
                            Attachment.content.is_(None),
                            func.length(func.trim(Attachment.content)) == 0,
                        ),
                        1,
                    )
                )
            ),
            func.count(case((Attachment.embedding.is_not(None), 1))),
        )
        .join(Email)
        .where(*email_scope)
    )
    attachment_stats = attachment_stats_result.one_or_none()
    attachment_count = attachment_stats[0] if attachment_stats else 0
    blank_attachment_count = attachment_stats[1] if attachment_stats else 0
    embedded_attachment_count = attachment_stats[2] if attachment_stats else 0
    return AttachmentQualityStats(
        count=attachment_count,
        blank_content_count=blank_attachment_count,
        embedded_count=embedded_attachment_count,
    )


async def _get_content_graph_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> ContentGraphQualityStats:
    content_graph_result = await db.execute(
        select(
            func.count(func.distinct(ContentSegmentRecord.email_id)),
            func.count(ContentSegmentRecord.content_segment_id),
        )
        .join(Email, ContentSegmentRecord.email_id == Email.id)
        .where(*email_scope)
    )
    content_graph_stats = content_graph_result.one_or_none()
    segmented_email_count = content_graph_stats[0] if content_graph_stats else 0
    segment_count = content_graph_stats[1] if content_graph_stats else 0
    return ContentGraphQualityStats(
        segmented_email_count=int(segmented_email_count or 0),
        segment_count=int(segment_count or 0),
    )


async def _get_knowledge_graph_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> KnowledgeGraphQualityStats:
    knowledge_graph_result = await db.execute(
        select(
            func.count(func.distinct(KnowledgeGraphEdgeRecord.email_id)),
            func.count(KnowledgeGraphEdgeRecord.knowledge_graph_edge_id),
        )
        .join(Email, KnowledgeGraphEdgeRecord.email_id == Email.id)
        .where(*email_scope)
    )
    knowledge_graph_stats = knowledge_graph_result.one_or_none()
    edged_email_count = knowledge_graph_stats[0] if knowledge_graph_stats else 0
    edge_count = knowledge_graph_stats[1] if knowledge_graph_stats else 0
    return KnowledgeGraphQualityStats(
        edged_email_count=int(edged_email_count or 0),
        edge_count=int(edge_count or 0),
    )


async def _get_content_segment_text_readiness_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> ContentSegmentTextReadinessStats:
    issue_case = case(
        (
            or_(
                ContentSegmentRecord.word_count <= 0,
                func.length(func.trim(ContentSegmentRecord.safe_text_content)) == 0,
            ),
            1,
        )
    )
    result = await db.execute(
        select(
            func.count(ContentSegmentRecord.content_segment_id),
            func.count(issue_case),
        )
        .join(Email, ContentSegmentRecord.email_id == Email.id)
        .where(*email_scope)
    )
    stats = result.one_or_none()
    total_count = stats[0] if stats else 0
    issue_count = stats[1] if stats else 0
    return ContentSegmentTextReadinessStats(
        total_count=int(total_count or 0),
        issue_count=int(issue_count or 0),
    )


async def _get_knowledge_graph_evidence_endpoint_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> KnowledgeGraphEvidenceEndpointStats:
    issue_case = case(
        (
            and_(
                KnowledgeGraphEdgeRecord.source_segment_id.is_(None),
                KnowledgeGraphEdgeRecord.target_segment_id.is_(None),
            ),
            1,
        )
    )
    result = await db.execute(
        select(
            func.count(KnowledgeGraphEdgeRecord.knowledge_graph_edge_id),
            func.count(issue_case),
        )
        .join(Email, KnowledgeGraphEdgeRecord.email_id == Email.id)
        .where(*email_scope)
    )
    stats = result.one_or_none()
    total_count = stats[0] if stats else 0
    issue_count = stats[1] if stats else 0
    return KnowledgeGraphEvidenceEndpointStats(
        total_count=int(total_count or 0),
        issue_count=int(issue_count or 0),
    )


async def _get_content_graph_breakdown(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> list[DataContentGraphBreakdown]:
    object_count = func.count(ContentSegmentRecord.content_segment_id).label(
        "object_count"
    )
    result = await db.execute(
        select(
            ContentSegmentRecord.source_kind,
            ContentSegmentRecord.segment_kind,
            object_count,
        )
        .join(Email, ContentSegmentRecord.email_id == Email.id)
        .where(*email_scope)
        .group_by(ContentSegmentRecord.source_kind, ContentSegmentRecord.segment_kind)
        .order_by(
            object_count.desc(),
            ContentSegmentRecord.source_kind.asc(),
            ContentSegmentRecord.segment_kind.asc(),
        )
        .limit(12)
    )
    return [
        _content_graph_breakdown_row(
            source_kind=source_kind,
            segment_kind=segment_kind,
            object_count=count,
        )
        for source_kind, segment_kind, count in result.all()
    ]


async def _get_knowledge_graph_breakdown(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> list[DataKnowledgeGraphBreakdown]:
    object_count = func.count(KnowledgeGraphEdgeRecord.knowledge_graph_edge_id).label(
        "object_count"
    )
    result = await db.execute(
        select(
            KnowledgeGraphEdgeRecord.source_kind,
            KnowledgeGraphEdgeRecord.edge_kind,
            object_count,
        )
        .join(Email, KnowledgeGraphEdgeRecord.email_id == Email.id)
        .where(*email_scope)
        .group_by(
            KnowledgeGraphEdgeRecord.source_kind,
            KnowledgeGraphEdgeRecord.edge_kind,
        )
        .order_by(
            object_count.desc(),
            KnowledgeGraphEdgeRecord.source_kind.asc(),
            KnowledgeGraphEdgeRecord.edge_kind.asc(),
        )
        .limit(12)
    )
    return [
        _knowledge_graph_breakdown_row(
            source_kind=source_kind,
            edge_kind=edge_kind,
            object_count=count,
        )
        for source_kind, edge_kind, count in result.all()
    ]


async def _get_content_graph_evidence_samples(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> list[DataContentGraphEvidenceSample]:
    result = await db.execute(
        select(
            ContentSegmentRecord.content_segment_uid,
            ContentSegmentRecord.source_kind,
            ContentSegmentRecord.segment_kind,
            ContentSegmentRecord.segment_path,
            ContentSegmentRecord.word_count,
        )
        .join(Email, ContentSegmentRecord.email_id == Email.id)
        .where(*email_scope)
        .order_by(
            ContentSegmentRecord.source_kind.asc(),
            ContentSegmentRecord.source_record_uid.asc(),
            ContentSegmentRecord.ordinal_index.asc(),
            ContentSegmentRecord.segment_path.asc(),
        )
        .limit(8)
    )
    return [
        _content_graph_evidence_sample_row(
            content_segment_uid=content_segment_uid,
            source_kind=source_kind,
            segment_kind=segment_kind,
            segment_path=segment_path,
            word_count=word_count,
        )
        for (
            content_segment_uid,
            source_kind,
            segment_kind,
            segment_path,
            word_count,
        ) in result.all()
    ]


async def _get_knowledge_graph_evidence_samples(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> list[DataKnowledgeGraphEvidenceSample]:
    result = await db.execute(
        select(
            KnowledgeGraphEdgeRecord.edge_uid,
            KnowledgeGraphEdgeRecord.source_kind,
            KnowledgeGraphEdgeRecord.edge_kind,
            KnowledgeGraphEdgeRecord.edge_path,
            KnowledgeGraphEdgeRecord.source_segment_id,
            KnowledgeGraphEdgeRecord.target_segment_id,
            KnowledgeGraphEdgeRecord.source_node_id,
            KnowledgeGraphEdgeRecord.target_node_id,
        )
        .join(Email, KnowledgeGraphEdgeRecord.email_id == Email.id)
        .where(*email_scope)
        .order_by(
            KnowledgeGraphEdgeRecord.source_kind.asc(),
            KnowledgeGraphEdgeRecord.source_record_uid.asc(),
            KnowledgeGraphEdgeRecord.ordinal_index.asc(),
            KnowledgeGraphEdgeRecord.edge_path.asc(),
        )
        .limit(8)
    )
    return [
        _knowledge_graph_evidence_sample_row(
            edge_uid=edge_uid,
            source_kind=source_kind,
            edge_kind=edge_kind,
            edge_path=edge_path,
            source_segment_id=source_segment_id,
            target_segment_id=target_segment_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )
        for (
            edge_uid,
            source_kind,
            edge_kind,
            edge_path,
            source_segment_id,
            target_segment_id,
            source_node_id,
            target_node_id,
        ) in result.all()
    ]


def _sender_relationship_scope_filter(
    auth_context: AuthContext,
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    organization_filter = (
        SenderRelationship.organization_id == auth_context.organization_id
        if auth_context.organization_id is not None
        else SenderRelationship.organization_id.is_(None)
    )
    return (
        SenderRelationship.user_id == auth_context.user_id,
        organization_filter,
    )


def _sender_relationship_has_source() -> ColumnElement[bool]:
    return or_(
        SenderRelationship.source_message_id.is_not(None),
        SenderRelationship.source_thread_id.is_not(None),
    )


async def _get_semantic_relation_evidence_stats(
    db: AsyncSession,
    auth_context: AuthContext,
) -> SemanticRelationEvidenceStats:
    result = await db.execute(
        select(
            func.count(SenderRelationship.id),
            func.count(case((_sender_relationship_has_source(), 1))),
        ).where(*_sender_relationship_scope_filter(auth_context))
    )
    stats = result.one_or_none()
    total_count = stats[0] if stats else 0
    source_backed_count = stats[1] if stats else 0
    return SemanticRelationEvidenceStats(
        total_count=int(total_count or 0),
        source_backed_count=int(source_backed_count or 0),
    )


async def _get_semantic_relation_evidence_samples(
    db: AsyncSession,
    auth_context: AuthContext,
) -> list[DataSemanticRelationEvidenceSample]:
    result = await db.execute(
        select(
            SenderRelationship.sender_email,
            SenderRelationship.source_message_id,
            SenderRelationship.source_thread_id,
            SenderRelationship.relationship_type,
            SenderRelationship.confidence_score,
        )
        .where(
            *_sender_relationship_scope_filter(auth_context),
            _sender_relationship_has_source(),
        )
        .order_by(
            SenderRelationship.confidence_score.desc(),
            SenderRelationship.updated_at.desc(),
            SenderRelationship.relationship_type.asc(),
        )
        .limit(8)
    )
    return [
        _semantic_relation_evidence_sample_row(
            sender_email=sender_email,
            source_message_id=source_message_id,
            source_thread_id=source_thread_id,
            relationship_type=relationship_type,
            confidence_score=confidence_score,
        )
        for (
            sender_email,
            source_message_id,
            source_thread_id,
            relationship_type,
            confidence_score,
        ) in result.all()
    ]


async def _get_attachment_parse_stats(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> AttachmentParseQualityStats:
    attachment_parse_result = await db.execute(
        select(
            func.count(case((Attachment.parse_status == "parsed", 1))),
            func.count(
                case(
                    (
                        or_(
                            Attachment.parse_status.is_(None),
                            Attachment.parse_status != "parsed",
                        ),
                        1,
                    )
                )
            ),
        )
        .join(Email)
        .where(*email_scope)
    )
    attachment_parse_stats = attachment_parse_result.one_or_none()
    parsed_count = attachment_parse_stats[0] if attachment_parse_stats else 0
    unparsed_count = attachment_parse_stats[1] if attachment_parse_stats else 0
    return AttachmentParseQualityStats(
        parsed_count=int(parsed_count or 0),
        unparsed_count=int(unparsed_count or 0),
    )


async def _get_attachment_parse_breakdown(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> list[DataAttachmentParseBreakdown]:
    object_count = func.count(Attachment.id).label("object_count")
    attachment_parse_breakdown_result = await db.execute(
        select(
            Attachment.content_type,
            Attachment.parse_content_type,
            Attachment.parse_status,
            Attachment.parser_key,
            object_count,
        )
        .join(Email)
        .where(*email_scope)
        .group_by(
            Attachment.content_type,
            Attachment.parse_content_type,
            Attachment.parse_status,
            Attachment.parser_key,
        )
        .order_by(
            object_count.desc(),
            Attachment.content_type.asc(),
            Attachment.parse_content_type.asc(),
            Attachment.parse_status.asc(),
            Attachment.parser_key.asc(),
        )
        .limit(12)
    )
    return [
        _attachment_parse_breakdown_row(
            content_type=content_type,
            parse_content_type=parse_content_type,
            parse_status=parse_status,
            parser_key=parser_key,
            object_count=count,
        )
        for (
            content_type,
            parse_content_type,
            parse_status,
            parser_key,
            count,
        ) in attachment_parse_breakdown_result.all()
    ]


async def _get_attachment_assets(
    db: AsyncSession,
    email_scope: EmailScopeFilter,
) -> list[AttachmentAssetRow]:
    attachment_asset_result = await db.execute(
        select(Attachment, Email)
        .join(Email)
        .where(*email_scope)
        .order_by(Email.date.desc(), Attachment.filename.asc())
        .limit(8)
    )
    return list(attachment_asset_result.all())


async def _get_connector_events(
    db: AsyncSession,
    auth_context: AuthContext,
) -> list[ConnectorSignalEvent]:
    connector_statement = connector_scope_statement(auth_context)
    if connector_statement is None:
        return []
    return await _scoped_rows(db, connector_statement)


@router.get("/quality-surface", response_model=DataQualitySurfaceResponse)
async def get_data_quality_surface(
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataQualitySurfaceResponse:
    webdav_accounts = await _scoped_rows(
        db,
        _owner_scope_statement(WebdavAccount, auth_context).order_by(
            WebdavAccount.created_at.asc(),
            WebdavAccount.source_uid.asc(),
        ),
    )
    project_folders = await _scoped_rows(
        db,
        _owner_scope_statement(ProjectFolder, auth_context).order_by(
            ProjectFolder.created_at.asc(),
            ProjectFolder.folder_uid.asc(),
        ),
    )
    documents = await _scoped_rows(
        db,
        select(Document)
        .where(Document.workspace_id == auth_context.workspace_id)
        .order_by(Document.created_at.desc(), Document.document_id.asc())
        .limit(8),
    )
    email_scope = _email_scope_filter(auth_context)

    email_stats = await _get_email_stats(db, email_scope)
    attachment_stats = await _get_attachment_stats(db, email_scope)
    content_graph_stats = await _get_content_graph_stats(db, email_scope)
    knowledge_graph_stats = await _get_knowledge_graph_stats(db, email_scope)
    content_segment_text_readiness_stats = (
        await _get_content_segment_text_readiness_stats(db, email_scope)
    )
    knowledge_graph_evidence_endpoint_stats = (
        await _get_knowledge_graph_evidence_endpoint_stats(db, email_scope)
    )
    content_graph_breakdown = await _get_content_graph_breakdown(db, email_scope)
    knowledge_graph_breakdown = await _get_knowledge_graph_breakdown(db, email_scope)
    content_graph_evidence_samples = await _get_content_graph_evidence_samples(
        db,
        email_scope,
    )
    knowledge_graph_evidence_samples = await _get_knowledge_graph_evidence_samples(
        db,
        email_scope,
    )
    semantic_relation_stats = await _get_semantic_relation_evidence_stats(
        db,
        auth_context,
    )
    semantic_relation_evidence_samples = (
        await _get_semantic_relation_evidence_samples(db, auth_context)
    )
    attachment_parse_stats = await _get_attachment_parse_stats(db, email_scope)
    email_count = email_stats.count
    missing_thread_count = email_stats.missing_thread_count
    missing_fingerprint_count = email_stats.missing_fingerprint_count
    embedded_email_count = email_stats.embedded_count
    attachment_count = attachment_stats.count
    blank_attachment_count = attachment_stats.blank_content_count
    embedded_attachment_count = attachment_stats.embedded_count
    segmented_email_count = content_graph_stats.segmented_email_count
    content_segment_count = content_graph_stats.segment_count
    edged_email_count = knowledge_graph_stats.edged_email_count
    knowledge_graph_edge_count = knowledge_graph_stats.edge_count
    semantic_relation_count = semantic_relation_stats.total_count
    semantic_relation_source_backed_count = (
        semantic_relation_stats.source_backed_count
    )
    parsed_attachment_count = attachment_parse_stats.parsed_count
    unparsed_attachment_count = attachment_parse_stats.unparsed_count

    attachment_parse_breakdown = await _get_attachment_parse_breakdown(
        db,
        email_scope,
    )
    connector_events = await _get_connector_events(db, auth_context)
    attachment_asset_rows = await _get_attachment_assets(db, email_scope)

    source_count = len(webdav_accounts) + len(project_folders)
    embedded_total = embedded_email_count + embedded_attachment_count
    object_total = email_count + attachment_count + len(documents)
    quality_checks = _quality_checks(
        email_count=email_count,
        attachment_count=attachment_count,
        missing_thread_count=missing_thread_count,
        missing_fingerprint_count=missing_fingerprint_count,
        blank_attachment_count=blank_attachment_count,
        source_count=source_count,
        segmented_email_count=segmented_email_count,
        edged_email_count=edged_email_count,
        content_segment_text_total_count=(
            content_segment_text_readiness_stats.total_count
        ),
        content_segment_text_issue_count=(
            content_segment_text_readiness_stats.issue_count
        ),
        knowledge_graph_evidence_endpoint_total_count=(
            knowledge_graph_evidence_endpoint_stats.total_count
        ),
        knowledge_graph_evidence_endpoint_issue_count=(
            knowledge_graph_evidence_endpoint_stats.issue_count
        ),
        semantic_relation_count=semantic_relation_count,
        semantic_relation_source_backed_count=semantic_relation_source_backed_count,
        unparsed_attachment_count=unparsed_attachment_count,
        connector_event_count=len(connector_events),
    )
    return DataQualitySurfaceResponse(
        workspace_id=auth_context.workspace_id,
        organization_id=auth_context.organization_id,
        audit_event="data.quality_surface.viewed",
        provider_write_executed=False,
        acquisition_readiness_gate=_acquisition_readiness_gate(
            quality_checks=quality_checks,
            content_graph_evidence_samples=content_graph_evidence_samples,
            knowledge_graph_evidence_samples=knowledge_graph_evidence_samples,
            semantic_relation_evidence_samples=semantic_relation_evidence_samples,
        ),
        repositories=_repository_summaries(
            webdav_accounts,
            project_folders,
            email_count,
            attachment_count,
            len(documents),
        ),
        repository_assets=[
            *_document_repository_assets(documents),
            *_attachment_repository_assets(attachment_asset_rows),
        ],
        pipeline_stages=_pipeline_stages(
            source_count=source_count,
            email_count=email_count,
            attachment_count=attachment_count,
            missing_thread_count=missing_thread_count,
            embedded_total=embedded_total,
            object_total=object_total,
            segmented_email_count=segmented_email_count,
            content_segment_count=content_segment_count,
            edged_email_count=edged_email_count,
            knowledge_graph_edge_count=knowledge_graph_edge_count,
            parsed_attachment_count=parsed_attachment_count,
            unparsed_attachment_count=unparsed_attachment_count,
            connector_event_count=len(connector_events),
        ),
        embedding_collections=_embedding_collections(
            email_count=email_count,
            embedded_email_count=embedded_email_count,
            attachment_count=attachment_count,
            embedded_attachment_count=embedded_attachment_count,
        ),
        quality_checks=quality_checks,
        attachment_parse_breakdown=attachment_parse_breakdown,
        content_graph_breakdown=content_graph_breakdown,
        knowledge_graph_breakdown=knowledge_graph_breakdown,
        content_graph_evidence_samples=content_graph_evidence_samples,
        knowledge_graph_evidence_samples=knowledge_graph_evidence_samples,
        semantic_relation_evidence_samples=semantic_relation_evidence_samples,
        semantic_extraction_manifest=_semantic_extraction_manifest(
            knowledge_graph_edge_count,
            semantic_relation_count,
            semantic_relation_source_backed_count,
        ),
        connector_events=[
            DataConnectorEvent(
                event_uid=event.event_uid,
                signal_key=event.signal_key,
                state_code=event.state_code,
                detail_text=event.detail_text,
                observed_at=_datetime_to_utc_iso(event.observed_at),
            )
            for event in connector_events
        ],
    )


@router.get(
    "/quality-surface/evidence-snapshot",
    response_model=DataEvidenceSnapshotResponse,
)
async def get_data_quality_evidence_snapshot(
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataEvidenceSnapshotResponse:
    surface = await get_data_quality_surface(auth_context=auth_context, db=db)
    return _evidence_snapshot_from_surface(surface)
