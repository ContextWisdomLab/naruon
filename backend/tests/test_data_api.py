import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api.data as data_api
from api.auth import get_auth_context, get_current_user
from core.config import settings
from db.models import (
    get_fernet,
    Attachment,
    Base,
    ConnectorSignalEvent,
    Document,
    Email,
    ProjectFolder,
    WebdavAccount,
)
from db.session import get_db
from main import app

TEST_SESSION_HMAC_SECRET = "data-quality-surface-hmac-material-32-bytes"  # noqa: S105


class MockResult:
    def __init__(self, obj):
        self.obj = obj

    def scalars(self):
        return self

    def all(self):
        return self.obj if isinstance(self.obj, list) else []

    def scalar_one(self):
        return self.obj

    def scalar_one_or_none(self):
        return self.obj

    def one_or_none(self):
        return self.obj


class MockAsyncSession:
    def __init__(self, results):
        self.results = results
        self.documents: list[Document] = []
        self.attachments: list[Attachment] = []
        self.queries = []
        self.execute_calls = 0

    async def execute(self, query):
        self.queries.append(query)
        rendered_query = str(query)
        rendered_query_lower = rendered_query.lower()
        if "where email_attachments.attachment_uid = " in rendered_query_lower:
            compiled = query.compile()
            params = compiled.params
            attachment_uid = next(
                (
                    value
                    for key, value in params.items()
                    if key.startswith("attachment_uid")
                ),
                None,
            )
            user_id = next(
                (value for key, value in params.items() if key.startswith("user_id")),
                None,
            )
            organization_id = next(
                (
                    value
                    for key, value in params.items()
                    if key.startswith("organization_id")
                ),
                None,
            )
            workspace_id = next(
                (
                    value
                    for key, value in params.items()
                    if key.startswith("workspace_id")
                ),
                None,
            )
            rows = [
                attachment
                for attachment in self.attachments
                if attachment.attachment_uid == attachment_uid
                and (user_id is None or attachment.email.user_id == user_id)
                and (
                    attachment.email.organization_id == organization_id
                    if organization_id is not None
                    else attachment.email.organization_id is None
                )
                and (
                    workspace_id is None
                    or attachment.email.workspace_id == workspace_id
                )
            ]
            return MockResult(rows[0] if rows else None)
        if (
            "webdav_accounts.source_uid" in rendered_query_lower
            and "webdav_accounts.account_id" not in rendered_query_lower
        ):
            result = self.results[self.execute_calls]
            self.execute_calls += 1
            return MockResult(
                [
                    (
                        account.source_uid,
                        account.writeback_enabled,
                        account.etag_value,
                    )
                    for account in result
                ]
            )
        if "from workspace_documents" in rendered_query_lower:
            compiled = query.compile()
            params = compiled.params
            document_id = next(
                (
                    value
                    for key, value in params.items()
                    if key.startswith("document_id")
                ),
                None,
            )
            workspace_id = next(
                (
                    value
                    for key, value in params.items()
                    if key.startswith("workspace_id")
                ),
                None,
            )
            rows = [
                document
                for document in self.documents
                if (document_id is None or document.document_id == document_id)
                and (workspace_id is None or document.workspace_id == workspace_id)
            ]
            if "order by" in rendered_query_lower:
                return MockResult(rows)
            return MockResult(rows[0] if rows else None)
        result = self.results[self.execute_calls]
        self.execute_calls += 1
        return MockResult(result)

    def add(self, obj):
        if isinstance(obj, Document):
            if not obj.document_id:
                obj.document_id = f"doc_mock_{len(self.documents) + 1}"
            if not obj.created_at:
                obj.created_at = _now()
            self.documents.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signed_session_token(payload: dict[str, object]) -> str:
    header_segment = _base64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(
        TEST_SESSION_HMAC_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def _valid_session_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ver": 1,
        "iss": "naruon-control-plane",
        "aud": "naruon-api",
        "sub": "admin",
        "role": "member",
        "org": "org-acme",
        "groups": ["group-data"],
        "workspace": "workspace-org-acme",
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return payload


def _now() -> datetime:
    return datetime(2026, 5, 28, 5, 45, tzinfo=timezone.utc)


def _webdav_account(source_uid: str) -> WebdavAccount:
    return WebdavAccount(
        source_uid=source_uid,
        user_id="owner",
        organization_id="org-acme",
        workspace_id="workspace-org-acme",
        server_url="https://files.acme.example/dav",
        username="files@example.com",
        credentials_encrypted="credential secret",
        writeback_enabled=True,
        etag_value="etag-webdav-primary",
        created_at=_now(),
    )


def _email(
    message_id: str,
    *,
    thread_id: str | None,
    subject: str = "Data source package",
    workspace_id: str = "workspace-org-acme",
) -> Email:
    return Email(
        user_id="owner",
        organization_id="org-acme",
        workspace_id=workspace_id,
        message_id=message_id,
        thread_id=thread_id,
        fingerprint=f"sha256:{message_id}",
        sender="partner@example.com",
        recipients="owner@example.com",
        subject=subject,
        date=_now(),
        body="source email body",
    )


def _attachment(filename: str, content: str) -> Attachment:
    return Attachment(filename=filename, content=content)


def _project_folder(folder_uid: str) -> ProjectFolder:
    return ProjectFolder(
        folder_uid=folder_uid,
        user_id="owner",
        organization_id="org-acme",
        project_name="Naruon Roadmap 2026",
        webdav_path="/Projects/Naruon_Roadmap_2026",
        created_at=_now(),
    )


def _connector_event(event_uid: str) -> ConnectorSignalEvent:
    return ConnectorSignalEvent(
        event_uid=event_uid,
        organization_id="org-acme",
        workspace_id="workspace-org-acme",
        signal_key="connector_heartbeat",
        state_code="heartbeat",
        detail_text="outbound connector heartbeat received",
        observed_at=_now(),
    )


@pytest.fixture
def mock_db():
    ready_email = _email("<asset-ready@example.com>", thread_id="thread-ready")
    pending_email = _email(
        "<asset-pending@example.com>",
        thread_id=None,
        subject="<script>Quarterly source pack</script>",
    )
    return MockAsyncSession(
        [
            [_webdav_account("webdav_src_primary")],
            [_project_folder("webdav_folder_roadmap")],
            (4, 1, 2, 3),  # email stats
            (3, 1, 1),  # attachment stats
            (3, 8),  # content graph stats
            (2, 10),  # knowledge graph stats
            (8, 1),  # content segment text readiness stats
            (10, 2),  # knowledge graph evidence endpoint readiness stats
            [
                ("email_body", "paragraph", 6),
                ("attachment", "heading", 2),
            ],  # content graph breakdown
            [
                ("email_body", "node_has_segment", 8),
                ("attachment", "heading_contains_segment", 2),
            ],  # knowledge graph breakdown
            [
                (
                    "cseg_email_paragraph_1",
                    "email_body",
                    "paragraph",
                    "/document[1]/paragraph[1]",
                    12,
                ),
                (
                    "cseg_attachment_heading_1",
                    "attachment",
                    "heading",
                    "/document[1]/h1[1]",
                    3,
                ),
            ],  # content graph evidence samples
            [
                (
                    "kgedge_email_node_segment_1",
                    "email_body",
                    "node_has_segment",
                    "/document[1]/paragraph[1]/has/segment[1]",
                    None,
                    12,
                    44,
                    None,
                ),
                (
                    "kgedge_attachment_node_only_1",
                    "attachment",
                    "node_contains_node",
                    "/document[1]/contains/h1[1]",
                    None,
                    None,
                    55,
                    56,
                ),
            ],  # knowledge graph evidence samples
            (3, 2),  # semantic relation evidence stats
            [
                (
                    "partner@example.com",
                    "<asset-ready@example.com>",
                    "thread-ready",
                    "Vendor",
                    0.92,
                ),
                (
                    "updates@example.com",
                    "<newsletter@example.com>",
                    None,
                    "Newsletter",
                    0.86,
                ),
            ],  # semantic relation evidence samples
            (2, 1),  # attachment parse stats
            [
                (
                    "application/octet-stream",
                    "text/markdown",
                    "parsed",
                    "markdown",
                    2,
                ),
                (
                    "application/pdf",
                    "application/pdf",
                    "unsupported_content_type",
                    "unsupported_binary",
                    1,
                ),
            ],  # attachment parse breakdown
            [_connector_event("connector_evt_data_quality")],
            [
                (_attachment("roadmap.pdf", "extracted attachment text"), ready_email),
                (_attachment("quarterly.md", ""), pending_email),
            ],
        ]
    )


def _with_signed_auth(mock_db, token: str):
    async def override_get_db():
        yield mock_db

    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    original_overrides = dict(app.dependency_overrides)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    return client, previous_secret, original_overrides


def _restore_overrides(previous_secret, original_overrides):
    settings.AUTH_SESSION_HMAC_SECRET = previous_secret
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def _expected_sample_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _expected_acquisition_readiness_kpis():
    return [
        {
            "kpi_key": "thread_id_integrity_target",
            "source_check_key": "thread_id_integrity",
            "display_name": "Thread id integrity target",
            "owner_area": "email_ingestion",
            "priority_rank": 1,
            "current_percent": 75,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Thread provenance must reach target before acquisition close."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "dedupe_fingerprint_target",
            "source_check_key": "dedupe_fingerprint",
            "display_name": "Duplicate fingerprint target",
            "owner_area": "email_ingestion",
            "priority_rank": 2,
            "current_percent": 50,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Duplicate fingerprints must reach target before corpus valuation."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "attachment_content_target",
            "source_check_key": "attachment_content",
            "display_name": "Attachment content target",
            "owner_area": "attachment_parsing",
            "priority_rank": 3,
            "current_percent": 67,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Attachment text extraction must reach target before buyer review."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "content_graph_coverage_target",
            "source_check_key": "content_graph_coverage",
            "display_name": "DOM paragraph coverage target",
            "owner_area": "content_graph",
            "priority_rank": 4,
            "current_percent": 75,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "DOM paragraph segmentation must reach target before graph claims."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "knowledge_graph_coverage_target",
            "source_check_key": "knowledge_graph_coverage",
            "display_name": "Knowledge graph coverage target",
            "owner_area": "knowledge_graph",
            "priority_rank": 5,
            "current_percent": 50,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Knowledge graph edge persistence must reach target before diligence."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "content_segment_text_readiness_target",
            "source_check_key": "content_segment_text_readiness",
            "display_name": "Segment text readiness target",
            "owner_area": "content_graph",
            "priority_rank": 6,
            "current_percent": 88,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Safe paragraph text and word counts must reach target."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "kg_evidence_endpoint_target",
            "source_check_key": "knowledge_graph_evidence_endpoint_readiness",
            "display_name": "KG evidence endpoint target",
            "owner_area": "knowledge_graph",
            "priority_rank": 7,
            "current_percent": 80,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "KG evidence endpoints must reach target before buyer audit."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "semantic_relation_source_backing_target",
            "source_check_key": "semantic_relation_source_backing",
            "display_name": "Semantic relation source target",
            "owner_area": "semantic_kg",
            "priority_rank": 8,
            "current_percent": 67,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Semantic relation source backing must reach target."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "attachment_parse_coverage_target",
            "source_check_key": "attachment_parse_coverage",
            "display_name": "Attachment parser coverage target",
            "owner_area": "attachment_parsing",
            "priority_rank": 9,
            "current_percent": 67,
            "target_percent": 100,
            "target_met": False,
            "status_code": "needs_attention",
            "guardrail_text": (
                "Attachment parser coverage must reach target or have safe "
                "exceptions."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "source_registry_target",
            "source_check_key": "source_registry",
            "display_name": "Source registry target",
            "owner_area": "connector_registry",
            "priority_rank": 10,
            "current_percent": 100,
            "target_percent": 100,
            "target_met": True,
            "status_code": "pass",
            "guardrail_text": (
                "Customer-owned source registration must stay complete."
            ),
            "provider_write_executed": False,
        },
        {
            "kpi_key": "connector_signal_target",
            "source_check_key": "connector_signal",
            "display_name": "Connector observability target",
            "owner_area": "connector_observability",
            "priority_rank": 11,
            "current_percent": 100,
            "target_percent": 100,
            "target_met": True,
            "status_code": "pass",
            "guardrail_text": "Connector observability must stay complete.",
            "provider_write_executed": False,
        },
        {
            "kpi_key": "semantic_kg_readiness_target",
            "source_check_key": "semantic_kg_readiness",
            "display_name": "Semantic KG evidence target",
            "owner_area": "semantic_kg",
            "priority_rank": 12,
            "current_percent": 100,
            "target_percent": 100,
            "target_met": True,
            "status_code": "pass",
            "guardrail_text": (
                "Semantic KG evidence must remain provenance-approved."
            ),
            "provider_write_executed": False,
        },
    ]


def _expected_acquisition_decision_summary():
    return {
        "summary_key": "buyer_diligence_decision",
        "recommendation_code": "remediate_before_close",
        "risk_level": "high",
        "target_gap_count": 9,
        "critical_action_count": 2,
        "high_action_count": 6,
        "medium_action_count": 1,
        "headline_text": "Remediate acquisition evidence gaps before close.",
        "next_step_text": (
            "Resolve critical and high remediation actions, then regenerate the "
            "diligence evidence snapshot."
        ),
        "provider_write_executed": False,
    }


def _expected_snapshot_verification_handoff():
    return {
        "verifier_key": "offline_evidence_snapshot_verifier",
        "verifier_command": "python scripts/verify_evidence_snapshot.py <snapshot.json>",
        "accepted_input": "file_path_or_stdin",
        "digest_algorithm": "sha256",
        "excluded_digest_fields": [
            "canonical_payload_fields",
            "digest_algorithm",
            "snapshot_digest",
        ],
        "success_exit_code": 0,
        "failure_exit_codes": {
            "invalid_json": 1,
            "missing_snapshot_digest": 2,
            "unsupported_digest_algorithm": 3,
            "digest_mismatch": 4,
        },
        "handoff_text": (
            "Save the copied evidence snapshot JSON and verify it with the offline "
            "verifier before sharing diligence materials."
        ),
        "provider_write_executed": False,
    }


def _expected_evidence_packet_checklist():
    return [
        {
            "checklist_key": "privacy_redaction_policy",
            "display_name": "Privacy redaction policy",
            "state_code": "ready",
            "source_field": "privacy_redaction_policy",
            "required_artifact": "redacted_snapshot_policy",
            "detail_text": (
                "Snapshot excludes raw content, stable identifiers, credentials, "
                "and database evidence strings."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "parser_manifest",
            "display_name": "Attachment parser manifest",
            "state_code": "ready",
            "source_field": "parser_manifest_summary",
            "required_artifact": "attachment_parser_registry",
            "detail_text": (
                "Parser family, supported content types, extensions, and unsupported "
                "binary fallback are included."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "content_graph_topology",
            "display_name": "DOM paragraph topology",
            "state_code": "ready",
            "source_field": "content_graph_topology_counts",
            "required_artifact": "source_kind_segment_kind_counts",
            "detail_text": (
                "Email body and attachment segments are summarized by source and "
                "paragraph or heading kind."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "content_graph_samples",
            "display_name": "Paragraph evidence samples",
            "state_code": "ready",
            "source_field": "content_graph_evidence_samples",
            "required_artifact": "redacted_segment_samples",
            "detail_text": (
                "Redacted paragraph samples include source kind, segment kind, path, "
                "and word count."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "knowledge_graph_topology",
            "display_name": "Knowledge graph topology",
            "state_code": "ready",
            "source_field": "knowledge_graph_topology_counts",
            "required_artifact": "source_kind_edge_kind_counts",
            "detail_text": (
                "Stored KG edges are summarized by source and edge kind for "
                "acquisition review."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "knowledge_graph_samples",
            "display_name": "KG evidence samples",
            "state_code": "ready",
            "source_field": "knowledge_graph_evidence_samples",
            "required_artifact": "redacted_edge_samples",
            "detail_text": (
                "Redacted KG samples include edge path and endpoint readiness "
                "without exposing raw IDs."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "semantic_relation_samples",
            "display_name": "Semantic relation evidence",
            "state_code": "ready",
            "source_field": "semantic_relation_evidence_samples",
            "required_artifact": "source_backed_relation_samples",
            "detail_text": (
                "Semantic relationship samples include confidence, source scope, "
                "and next action."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "semantic_extraction_manifest",
            "display_name": "Semantic extraction manifest",
            "state_code": "ready",
            "source_field": "semantic_extraction_manifest",
            "required_artifact": "extractor_provenance_manifest",
            "detail_text": (
                "Entity/relation extraction readiness and required provenance "
                "evidence are included."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "acquisition_readiness_gate",
            "display_name": "Acquisition readiness gate",
            "state_code": "needs_attention",
            "source_field": "acquisition_readiness_gate",
            "required_artifact": "buyer_evidence_readiness_gate",
            "detail_text": (
                "Buyer readiness score, blocking checks, KPIs, decision summary, "
                "and remediation actions are included."
            ),
            "provider_write_executed": False,
        },
        {
            "checklist_key": "offline_snapshot_verification",
            "display_name": "Offline snapshot verification",
            "state_code": "ready",
            "source_field": "verification_handoff",
            "required_artifact": "offline_digest_verifier_handoff",
            "detail_text": (
                "Offline verifier command, accepted input, digest algorithm, "
                "excluded fields, and exit codes are included."
            ),
            "provider_write_executed": False,
        },
    ]


def _expected_data_room_package_manifest():
    def entry(
        *,
        manifest_key: str,
        file_name: str,
        artifact_type: str,
        display_name: str,
        state_code: str,
        source_field: str,
        detail_text: str,
    ):
        return {
            "manifest_key": manifest_key,
            "file_name": file_name,
            "artifact_type": artifact_type,
            "display_name": display_name,
            "state_code": state_code,
            "source_field": source_field,
            "required_for_close": True,
            "contains_raw_content": False,
            "contains_stable_identifiers": False,
            "detail_text": detail_text,
            "provider_write_executed": False,
        }

    return [
        entry(
            manifest_key="evidence_snapshot_json",
            file_name="naruon-evidence-snapshot.json",
            artifact_type="snapshot_json",
            display_name="Evidence snapshot JSON",
            state_code="ready",
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
            state_code="ready",
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
            state_code="ready",
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
            state_code="ready",
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
            state_code="ready",
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
            state_code="ready",
            source_field="knowledge_graph_evidence_samples",
            detail_text="Redacted KG edge samples with safe paths and endpoint readiness.",
        ),
        entry(
            manifest_key="semantic_relation_samples",
            file_name="semantic-relation-evidence-samples.json",
            artifact_type="evidence_samples_json",
            display_name="Semantic relation evidence samples",
            state_code="ready",
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
            state_code="needs_attention",
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
            state_code="needs_attention",
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
            state_code="needs_attention",
            source_field="acquisition_readiness_gate.remediation_actions",
            detail_text=(
                "Required remediation actions to close remaining diligence gaps."
            ),
        ),
    ]


def _expected_diligence_exception_register():
    related_artifact_by_check_key = {
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
    return [
        {
            "exception_key": f"exception_{action['action_key']}",
            "blocking_check_key": action["blocking_check_key"],
            "display_name": action["display_name"],
            "severity_code": action["priority_code"],
            "owner_area": action["owner_area"],
            "source_field": f"quality_checks.{action['blocking_check_key']}",
            "related_artifact": related_artifact_by_check_key[
                action["blocking_check_key"]
            ],
            "blocks_close": True,
            "detail_text": action["impact_text"],
            "next_action": action["recommended_next_step"],
            "provider_write_executed": False,
        }
        for action in _expected_acquisition_remediation_actions()
    ]


def _expected_diligence_risk_matrix():
    return [
        {
            "matrix_key": (
                "risk_critical_email_ingestion_acquisition_readiness_summary_json"
            ),
            "severity_code": "critical",
            "owner_area": "email_ingestion",
            "related_artifact": "acquisition-readiness-summary.json",
            "exception_count": 2,
            "representative_exception_keys": [
                "exception_repair_thread_id_integrity",
                "exception_backfill_dedupe_fingerprints",
            ],
            "risk_label": "Critical close blocker concentration",
            "buyer_implication": (
                "2 critical exception(s) in email_ingestion affect "
                "acquisition-readiness-summary.json and block buyer close."
            ),
            "recommended_next_action": (
                "Resolve exception_repair_thread_id_integrity, "
                "exception_backfill_dedupe_fingerprints, then regenerate the "
                "evidence snapshot."
            ),
            "blocks_close": True,
            "provider_write_executed": False,
        },
        {
            "matrix_key": "risk_high_attachment_parsing_remediation_actions_json",
            "severity_code": "high",
            "owner_area": "attachment_parsing",
            "related_artifact": "remediation-actions.json",
            "exception_count": 1,
            "representative_exception_keys": [
                "exception_recover_attachment_content",
            ],
            "risk_label": "High diligence evidence gap",
            "buyer_implication": (
                "1 high exception(s) in attachment_parsing affect "
                "remediation-actions.json and block buyer close."
            ),
            "recommended_next_action": (
                "Resolve exception_recover_attachment_content, then regenerate "
                "the evidence snapshot."
            ),
            "blocks_close": True,
            "provider_write_executed": False,
        },
        {
            "matrix_key": "risk_high_content_graph_dom_paragraph_evidence_samples_json",
            "severity_code": "high",
            "owner_area": "content_graph",
            "related_artifact": "dom-paragraph-evidence-samples.json",
            "exception_count": 2,
            "representative_exception_keys": [
                "exception_backfill_content_graph_coverage",
                "exception_repair_segment_text_readiness",
            ],
            "risk_label": "High diligence evidence gap",
            "buyer_implication": (
                "2 high exception(s) in content_graph affect "
                "dom-paragraph-evidence-samples.json and block buyer close."
            ),
            "recommended_next_action": (
                "Resolve exception_backfill_content_graph_coverage, "
                "exception_repair_segment_text_readiness, then regenerate the "
                "evidence snapshot."
            ),
            "blocks_close": True,
            "provider_write_executed": False,
        },
        {
            "matrix_key": (
                "risk_high_knowledge_graph_knowledge_graph_evidence_samples_json"
            ),
            "severity_code": "high",
            "owner_area": "knowledge_graph",
            "related_artifact": "knowledge-graph-evidence-samples.json",
            "exception_count": 2,
            "representative_exception_keys": [
                "exception_backfill_knowledge_graph_coverage",
                "exception_attach_kg_evidence_endpoints",
            ],
            "risk_label": "High diligence evidence gap",
            "buyer_implication": (
                "2 high exception(s) in knowledge_graph affect "
                "knowledge-graph-evidence-samples.json and block buyer close."
            ),
            "recommended_next_action": (
                "Resolve exception_backfill_knowledge_graph_coverage, "
                "exception_attach_kg_evidence_endpoints, then regenerate the "
                "evidence snapshot."
            ),
            "blocks_close": True,
            "provider_write_executed": False,
        },
        {
            "matrix_key": (
                "risk_high_semantic_kg_semantic_relation_evidence_samples_json"
            ),
            "severity_code": "high",
            "owner_area": "semantic_kg",
            "related_artifact": "semantic-relation-evidence-samples.json",
            "exception_count": 1,
            "representative_exception_keys": [
                "exception_backfill_semantic_relation_sources",
            ],
            "risk_label": "High diligence evidence gap",
            "buyer_implication": (
                "1 high exception(s) in semantic_kg affect "
                "semantic-relation-evidence-samples.json and block buyer close."
            ),
            "recommended_next_action": (
                "Resolve exception_backfill_semantic_relation_sources, then "
                "regenerate the evidence snapshot."
            ),
            "blocks_close": True,
            "provider_write_executed": False,
        },
        {
            "matrix_key": "risk_medium_attachment_parsing_remediation_actions_json",
            "severity_code": "medium",
            "owner_area": "attachment_parsing",
            "related_artifact": "remediation-actions.json",
            "exception_count": 1,
            "representative_exception_keys": [
                "exception_expand_attachment_parse_coverage",
            ],
            "risk_label": "Medium diligence coverage gap",
            "buyer_implication": (
                "1 medium exception(s) in attachment_parsing affect "
                "remediation-actions.json and block buyer close."
            ),
            "recommended_next_action": (
                "Resolve exception_expand_attachment_parse_coverage, then "
                "regenerate the evidence snapshot."
            ),
            "blocks_close": True,
            "provider_write_executed": False,
        },
    ]


def _expected_diligence_close_proof_plan():
    dependency_by_severity = {
        "critical": "critical evidence gate",
        "high": "high priority evidence gate",
        "medium": "coverage exception gate",
    }
    return [
        {
            "proof_key": f"proof_{risk['matrix_key']}",
            "severity_code": risk["severity_code"],
            "owner_area": risk["owner_area"],
            "related_artifact": risk["related_artifact"],
            "exception_count": risk["exception_count"],
            "required_proof_artifact": risk["related_artifact"],
            "acceptance_criteria": (
                f"All {risk['exception_count']} exception(s) for "
                f"{risk['owner_area']} are resolved and "
                f"{risk['related_artifact']} is regenerated without raw content "
                "or stable IDs."
            ),
            "verification_method": (
                "Regenerate the evidence snapshot and run python "
                "scripts/verify_evidence_snapshot.py <snapshot.json>."
            ),
            "buyer_close_dependency": dependency_by_severity[
                risk["severity_code"]
            ],
            "close_gate_status": "blocked",
            "next_action": risk["recommended_next_action"],
            "provider_write_executed": False,
        }
        for risk in _expected_diligence_risk_matrix()
    ]


def _expected_diligence_close_decision_summary():
    return {
        "summary_key": "buyer_close_decision",
        "decision_code": "close_blocked",
        "total_proof_count": 6,
        "blocked_proof_count": 6,
        "ready_proof_count": 0,
        "critical_blocker_count": 1,
        "high_blocker_count": 4,
        "medium_blocker_count": 1,
        "required_artifact_count": 5,
        "required_artifacts": [
            "acquisition-readiness-summary.json",
            "dom-paragraph-evidence-samples.json",
            "knowledge-graph-evidence-samples.json",
            "remediation-actions.json",
            "semantic-relation-evidence-samples.json",
        ],
        "highest_severity": "critical",
        "snapshot_verification_required": True,
        "buyer_summary_text": (
            "Close remains blocked by 6 proof requirement(s) across "
            "5 required artifact(s)."
        ),
        "next_action_text": (
            "Resolve critical and high proof blockers, regenerate the "
            "evidence snapshot, and verify the copied JSON with the offline "
            "snapshot verifier."
        ),
        "provider_write_executed": False,
    }


def _expected_diligence_close_artifact_review_queue():
    return [
        {
            "queue_key": "review_acquisition_readiness_summary_json",
            "required_proof_artifact": "acquisition-readiness-summary.json",
            "owner_areas": ["email_ingestion"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "critical",
            "buyer_review_role": "executive diligence reviewer",
            "review_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) for acquisition-readiness-summary.json "
                "need executive diligence reviewer review before close."
            ),
            "next_action": (
                "Resolve exception_repair_thread_id_integrity, "
                "exception_backfill_dedupe_fingerprints, then regenerate the "
                "evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "queue_key": "review_dom_paragraph_evidence_samples_json",
            "required_proof_artifact": "dom-paragraph-evidence-samples.json",
            "owner_areas": ["content_graph"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_role": "data quality reviewer",
            "review_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) for dom-paragraph-evidence-samples.json "
                "need data quality reviewer review before close."
            ),
            "next_action": (
                "Resolve exception_backfill_content_graph_coverage, "
                "exception_repair_segment_text_readiness, then regenerate the "
                "evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "queue_key": "review_knowledge_graph_evidence_samples_json",
            "required_proof_artifact": "knowledge-graph-evidence-samples.json",
            "owner_areas": ["knowledge_graph"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_role": "data quality reviewer",
            "review_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) for knowledge-graph-evidence-samples.json "
                "need data quality reviewer review before close."
            ),
            "next_action": (
                "Resolve exception_backfill_knowledge_graph_coverage, "
                "exception_attach_kg_evidence_endpoints, then regenerate the "
                "evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "queue_key": "review_remediation_actions_json",
            "required_proof_artifact": "remediation-actions.json",
            "owner_areas": ["attachment_parsing"],
            "proof_count": 2,
            "blocked_proof_count": 2,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_role": "data quality reviewer",
            "review_status": "blocked",
            "acceptance_summary": (
                "2 proof requirement(s) for remediation-actions.json need "
                "data quality reviewer review before close."
            ),
            "next_action": (
                "Resolve exception_recover_attachment_content, then regenerate the "
                "evidence snapshot.; Resolve exception_expand_attachment_parse_coverage, "
                "then regenerate the evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "queue_key": "review_semantic_relation_evidence_samples_json",
            "required_proof_artifact": "semantic-relation-evidence-samples.json",
            "owner_areas": ["semantic_kg"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_role": "data quality reviewer",
            "review_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) for semantic-relation-evidence-samples.json "
                "need data quality reviewer review before close."
            ),
            "next_action": (
                "Resolve exception_backfill_semantic_relation_sources, then "
                "regenerate the evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
    ]


def _expected_diligence_close_owner_handoff_queue():
    return [
        {
            "handoff_key": "handoff_attachment_parsing",
            "owner_area": "attachment_parsing",
            "related_artifacts": ["remediation-actions.json"],
            "proof_count": 2,
            "blocked_proof_count": 2,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_roles": ["data quality reviewer", "coverage reviewer"],
            "handoff_status": "blocked",
            "acceptance_summary": (
                "2 proof requirement(s) assigned to attachment_parsing affect "
                "1 artifact(s) before close."
            ),
            "next_action": (
                "Resolve exception_recover_attachment_content, then regenerate the "
                "evidence snapshot.; Resolve exception_expand_attachment_parse_coverage, "
                "then regenerate the evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "handoff_key": "handoff_content_graph",
            "owner_area": "content_graph",
            "related_artifacts": ["dom-paragraph-evidence-samples.json"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_roles": ["data quality reviewer"],
            "handoff_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) assigned to content_graph affect "
                "1 artifact(s) before close."
            ),
            "next_action": (
                "Resolve exception_backfill_content_graph_coverage, "
                "exception_repair_segment_text_readiness, then regenerate the "
                "evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "handoff_key": "handoff_email_ingestion",
            "owner_area": "email_ingestion",
            "related_artifacts": ["acquisition-readiness-summary.json"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "critical",
            "buyer_review_roles": ["executive diligence reviewer"],
            "handoff_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) assigned to email_ingestion affect "
                "1 artifact(s) before close."
            ),
            "next_action": (
                "Resolve exception_repair_thread_id_integrity, "
                "exception_backfill_dedupe_fingerprints, then regenerate the "
                "evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "handoff_key": "handoff_knowledge_graph",
            "owner_area": "knowledge_graph",
            "related_artifacts": ["knowledge-graph-evidence-samples.json"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_roles": ["data quality reviewer"],
            "handoff_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) assigned to knowledge_graph affect "
                "1 artifact(s) before close."
            ),
            "next_action": (
                "Resolve exception_backfill_knowledge_graph_coverage, "
                "exception_attach_kg_evidence_endpoints, then regenerate the "
                "evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
        {
            "handoff_key": "handoff_semantic_kg",
            "owner_area": "semantic_kg",
            "related_artifacts": ["semantic-relation-evidence-samples.json"],
            "proof_count": 1,
            "blocked_proof_count": 1,
            "ready_proof_count": 0,
            "highest_severity": "high",
            "buyer_review_roles": ["data quality reviewer"],
            "handoff_status": "blocked",
            "acceptance_summary": (
                "1 proof requirement(s) assigned to semantic_kg affect "
                "1 artifact(s) before close."
            ),
            "next_action": (
                "Resolve exception_backfill_semantic_relation_sources, then "
                "regenerate the evidence snapshot."
            ),
            "snapshot_verification_required": True,
            "provider_write_executed": False,
        },
    ]


def _expected_diligence_close_traceability_map():
    risk_by_key = {
        risk["matrix_key"]: risk for risk in _expected_diligence_risk_matrix()
    }
    manifest_by_file = {
        item["file_name"]: item for item in _expected_data_room_package_manifest()
    }
    artifact_review_by_artifact = {
        item["required_proof_artifact"]: item
        for item in _expected_diligence_close_artifact_review_queue()
    }
    owner_handoff_by_owner = {
        item["owner_area"]: item for item in _expected_diligence_close_owner_handoff_queue()
    }

    entries = []
    for proof in _expected_diligence_close_proof_plan():
        risk_key = proof["proof_key"].removeprefix("proof_")
        risk = risk_by_key[risk_key]
        manifest = manifest_by_file[proof["required_proof_artifact"]]
        artifact_review = artifact_review_by_artifact[
            proof["required_proof_artifact"]
        ]
        owner_handoff = owner_handoff_by_owner[proof["owner_area"]]
        entries.append(
            {
                "trace_key": f"trace_{risk_key}",
                "source_field": manifest["source_field"],
                "data_room_artifact": proof["required_proof_artifact"],
                "manifest_key": manifest["manifest_key"],
                "exception_keys": risk["representative_exception_keys"],
                "risk_key": risk_key,
                "proof_key": proof["proof_key"],
                "artifact_review_key": artifact_review["queue_key"],
                "owner_handoff_key": owner_handoff["handoff_key"],
                "owner_area": proof["owner_area"],
                "severity_code": proof["severity_code"],
                "exception_count": proof["exception_count"],
                "close_gate_status": proof["close_gate_status"],
                "buyer_review_roles": owner_handoff["buyer_review_roles"],
                "trace_summary": (
                    f"{manifest['source_field']} feeds "
                    f"{proof['required_proof_artifact']} for "
                    f"{proof['owner_area']} close proof traceability."
                ),
                "next_action": proof["next_action"],
                "snapshot_verification_required": True,
                "provider_write_executed": False,
            }
        )
    return entries


def _expected_acquisition_remediation_actions():
    return [
        {
            "action_key": "repair_thread_id_integrity",
            "blocking_check_key": "thread_id_integrity",
            "display_name": "Canonical thread repair",
            "owner_area": "email_ingestion",
            "priority_rank": 1,
            "priority_code": "critical",
            "impact_text": "Thread provenance must be stable before buyer review.",
            "recommended_next_step": (
                "Run canonical threading repair for affected scoped emails."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "backfill_dedupe_fingerprints",
            "blocking_check_key": "dedupe_fingerprint",
            "display_name": "Duplicate fingerprint backfill",
            "owner_area": "email_ingestion",
            "priority_rank": 2,
            "priority_code": "critical",
            "impact_text": "Duplicate detection must be reliable before corpus valuation.",
            "recommended_next_step": (
                "Backfill duplicate-detection fingerprints for scoped email records."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "recover_attachment_content",
            "blocking_check_key": "attachment_content",
            "display_name": "Attachment content extraction",
            "owner_area": "attachment_parsing",
            "priority_rank": 3,
            "priority_code": "high",
            "impact_text": "Attachment text gaps reduce searchable diligence coverage.",
            "recommended_next_step": (
                "Re-run attachment extraction for scoped attachments with blank safe "
                "content."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "backfill_content_graph_coverage",
            "blocking_check_key": "content_graph_coverage",
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
            "provider_write_executed": False,
        },
        {
            "action_key": "backfill_knowledge_graph_coverage",
            "blocking_check_key": "knowledge_graph_coverage",
            "display_name": "Knowledge graph edge persistence",
            "owner_area": "knowledge_graph",
            "priority_rank": 5,
            "priority_code": "high",
            "impact_text": "Stored edges are required to prove graph extraction coverage.",
            "recommended_next_step": (
                "Persist deterministic knowledge graph edges for emails missing graph "
                "coverage."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "repair_segment_text_readiness",
            "blocking_check_key": "content_segment_text_readiness",
            "display_name": "Segment safe text repair",
            "owner_area": "content_graph",
            "priority_rank": 6,
            "priority_code": "high",
            "impact_text": (
                "Paragraph evidence needs non-empty safe text and word counts."
            ),
            "recommended_next_step": (
                "Rebuild affected content segments with safe text and word-count "
                "evidence."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "attach_kg_evidence_endpoints",
            "blocking_check_key": "knowledge_graph_evidence_endpoint_readiness",
            "display_name": "KG evidence endpoint repair",
            "owner_area": "knowledge_graph",
            "priority_rank": 7,
            "priority_code": "high",
            "impact_text": "KG edges need paragraph endpoints to be auditable.",
            "recommended_next_step": (
                "Attach source or target paragraph segment endpoints to affected KG "
                "edges."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "backfill_semantic_relation_sources",
            "blocking_check_key": "semantic_relation_source_backing",
            "display_name": "Semantic relation source backing",
            "owner_area": "semantic_kg",
            "priority_rank": 8,
            "priority_code": "high",
            "impact_text": (
                "Semantic relations need source message or thread evidence."
            ),
            "recommended_next_step": (
                "Backfill source message or thread links for semantic relation "
                "records."
            ),
            "provider_write_executed": False,
        },
        {
            "action_key": "expand_attachment_parse_coverage",
            "blocking_check_key": "attachment_parse_coverage",
            "display_name": "Attachment parser coverage",
            "owner_area": "attachment_parsing",
            "priority_rank": 9,
            "priority_code": "medium",
            "impact_text": "Unsupported attachments leave buyer-visible corpus gaps.",
            "recommended_next_step": (
                "Add parser coverage or metadata-only exception evidence for "
                "unsupported attachment types."
            ),
            "provider_write_executed": False,
        },
    ]


def test_data_quality_surface_returns_source_backed_counts_without_secrets(mock_db):
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.get("/api/data/quality-surface")
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["audit_event"] == "data.quality_surface.viewed"
    assert data["workspace_id"] == "workspace-org-acme"
    assert data["provider_write_executed"] is False
    assert data["acquisition_readiness_gate"] == {
        "gate_key": "buyer_evidence_readiness",
        "display_name": "Buyer evidence readiness",
        "state_code": "needs_attention",
        "readiness_score": 25,
        "passed_checks": 3,
        "issue_checks": 9,
        "pending_checks": 0,
        "total_checks": 12,
        "blocking_check_keys": [
            "thread_id_integrity",
            "dedupe_fingerprint",
            "attachment_content",
            "content_graph_coverage",
            "knowledge_graph_coverage",
            "content_segment_text_readiness",
            "knowledge_graph_evidence_endpoint_readiness",
            "semantic_relation_source_backing",
        ],
        "evidence_packet_ready": True,
        "snapshot_verification_ready": True,
        "provider_write_executed": False,
        "kpis": _expected_acquisition_readiness_kpis(),
        "decision_summary": _expected_acquisition_decision_summary(),
        "remediation_actions": _expected_acquisition_remediation_actions(),
        "detail_text": (
            "Buyer evidence packet is generated, but blocking quality checks remain."
        ),
    }
    assert {source["source_id"] for source in data["repositories"]} == {
        "email_repository",
        "attachment_repository",
        "document_repository",
        "webdav_src_primary",
        "webdav_folder_roadmap",
    }
    assert data["pipeline_stages"][1]["detail_text"] == (
        "4 emails and 3 attachments are visible in the signed workspace scope."
    )
    stage_by_key = {stage["stage_key"]: stage for stage in data["pipeline_stages"]}
    assert stage_by_key["content_graph_inventory"] == {
        "stage_key": "content_graph_inventory",
        "display_name": "Content graph inventory",
        "status_code": "running",
        "progress_percent": 75,
        "evidence_source": "content_segments",
        "detail_text": "3 of 4 emails have paragraph segments; 8 segments are stored.",
        "provider_write_executed": False,
    }
    assert stage_by_key["knowledge_graph_inventory"] == {
        "stage_key": "knowledge_graph_inventory",
        "display_name": "Knowledge graph inventory",
        "status_code": "running",
        "progress_percent": 50,
        "evidence_source": "knowledge_graph_edges",
        "detail_text": "2 of 4 emails have graph edges; 10 edges are stored.",
        "provider_write_executed": False,
    }
    assert stage_by_key["attachment_parse_inventory"] == {
        "stage_key": "attachment_parse_inventory",
        "display_name": "Attachment parse inventory",
        "status_code": "running",
        "progress_percent": 67,
        "evidence_source": "email_attachments.parse_status",
        "detail_text": "2 of 3 attachments are parseable; 1 attachments need parser coverage.",
        "provider_write_executed": False,
    }
    assert data["embedding_collections"][0] == {
        "collection_key": "emails_embedding",
        "display_name": "Email vectors",
        "object_count": 4,
        "embedded_count": 3,
        "embedding_model": settings.OPENAI_EMBEDDING_MODEL,
        "vector_dimensions": 1536,
        "status_code": "running",
        "evidence_source": "emails.embedding",
        "provider_write_executed": False,
    }
    quality_by_key = {check["check_key"]: check for check in data["quality_checks"]}
    assert quality_by_key["thread_id_integrity"]["issue_count"] == 1
    assert quality_by_key["dedupe_fingerprint"]["issue_count"] == 2
    assert quality_by_key["attachment_content"]["issue_count"] == 1
    assert quality_by_key["content_graph_coverage"] == {
        "check_key": "content_graph_coverage",
        "display_name": "Content graph coverage",
        "status_code": "needs_attention",
        "issue_count": 1,
        "total_count": 4,
        "evidence_source": "content_segments",
        "detail_text": "Some scoped emails need DOM paragraph segmentation.",
        "provider_write_executed": False,
    }
    assert quality_by_key["knowledge_graph_coverage"] == {
        "check_key": "knowledge_graph_coverage",
        "display_name": "Knowledge graph coverage",
        "status_code": "needs_attention",
        "issue_count": 2,
        "total_count": 4,
        "evidence_source": "knowledge_graph_edges",
        "detail_text": "Some scoped emails need persisted knowledge graph edges.",
        "provider_write_executed": False,
    }
    assert quality_by_key["content_segment_text_readiness"] == {
        "check_key": "content_segment_text_readiness",
        "display_name": "Content segment text readiness",
        "status_code": "needs_attention",
        "issue_count": 1,
        "total_count": 8,
        "evidence_source": (
            "content_segments.word_count, content_segments.safe_text_content"
        ),
        "detail_text": (
            "Some DOM paragraph segments need non-empty safe text and word counts."
        ),
        "provider_write_executed": False,
    }
    assert quality_by_key["knowledge_graph_evidence_endpoint_readiness"] == {
        "check_key": "knowledge_graph_evidence_endpoint_readiness",
        "display_name": "Knowledge graph evidence endpoints",
        "status_code": "needs_attention",
        "issue_count": 2,
        "total_count": 10,
        "evidence_source": (
            "knowledge_graph_edges.source_segment_id, "
            "knowledge_graph_edges.target_segment_id"
        ),
        "detail_text": (
            "Some knowledge graph edges need paragraph segment evidence endpoints."
        ),
        "provider_write_executed": False,
    }
    assert quality_by_key["semantic_kg_readiness"] == {
        "check_key": "semantic_kg_readiness",
        "display_name": "Semantic KG readiness",
        "status_code": "pass",
        "issue_count": 0,
        "total_count": 3,
        "evidence_source": (
            "knowledge_graph_edges.edge_kind, content_segments.segment_path"
        ),
        "detail_text": (
            "Semantic entity/relation evidence is available for this workspace."
        ),
        "provider_write_executed": False,
    }
    assert quality_by_key["semantic_relation_source_backing"] == {
        "check_key": "semantic_relation_source_backing",
        "display_name": "Semantic relation source backing",
        "status_code": "needs_attention",
        "issue_count": 1,
        "total_count": 3,
        "evidence_source": (
            "sender_relationships.source_message_id, "
            "sender_relationships.source_thread_id"
        ),
        "detail_text": "Some semantic relations need source message or thread evidence.",
        "provider_write_executed": False,
    }
    assert quality_by_key["attachment_parse_coverage"] == {
        "check_key": "attachment_parse_coverage",
        "display_name": "Attachment parse coverage",
        "status_code": "needs_attention",
        "issue_count": 1,
        "total_count": 3,
        "evidence_source": "email_attachments.parse_status",
        "detail_text": "Some scoped attachments need parser coverage.",
        "provider_write_executed": False,
    }
    assert data["content_graph_breakdown"] == [
        {
            "source_kind": "email_body",
            "segment_kind": "paragraph",
            "object_count": 6,
            "evidence_source": (
                "content_segments.source_kind, content_segments.segment_kind"
            ),
            "provider_write_executed": False,
        },
        {
            "source_kind": "attachment",
            "segment_kind": "heading",
            "object_count": 2,
            "evidence_source": (
                "content_segments.source_kind, content_segments.segment_kind"
            ),
            "provider_write_executed": False,
        },
    ]
    assert data["knowledge_graph_breakdown"] == [
        {
            "source_kind": "email_body",
            "edge_kind": "node_has_segment",
            "object_count": 8,
            "evidence_source": (
                "knowledge_graph_edges.source_kind, knowledge_graph_edges.edge_kind"
            ),
            "provider_write_executed": False,
        },
        {
            "source_kind": "attachment",
            "edge_kind": "heading_contains_segment",
            "object_count": 2,
            "evidence_source": (
                "knowledge_graph_edges.source_kind, knowledge_graph_edges.edge_kind"
            ),
            "provider_write_executed": False,
        },
    ]
    assert data["content_graph_evidence_samples"] == [
        {
            "sample_key": _expected_sample_key(
                "segment",
                "cseg_email_paragraph_1",
            ),
            "source_kind": "email_body",
            "segment_kind": "paragraph",
            "segment_path": "/document[1]/paragraph[1]",
            "word_count": 12,
        },
        {
            "sample_key": _expected_sample_key(
                "segment",
                "cseg_attachment_heading_1",
            ),
            "source_kind": "attachment",
            "segment_kind": "heading",
            "segment_path": "/document[1]/h1[1]",
            "word_count": 3,
        },
    ]
    assert data["knowledge_graph_evidence_samples"] == [
        {
            "sample_key": _expected_sample_key(
                "edge",
                "kgedge_email_node_segment_1",
            ),
            "source_kind": "email_body",
            "edge_kind": "node_has_segment",
            "edge_path": "/document[1]/paragraph[1]/has/segment[1]",
            "endpoint_status": "segment_backed",
        },
        {
            "sample_key": _expected_sample_key(
                "edge",
                "kgedge_attachment_node_only_1",
            ),
            "source_kind": "attachment",
            "edge_kind": "node_contains_node",
            "edge_path": "/document[1]/contains/h1[1]",
            "endpoint_status": "node_only",
        },
    ]
    assert data["semantic_extraction_manifest"] == [
        {
            "manifest_key": "entity_relation_extraction",
            "display_name": "Entity/relation extraction",
            "state_code": "ready",
            "structural_edge_count": 10,
            "semantic_relation_count": 3,
            "source_backed_relation_count": 2,
            "required_evidence": [
                "segment_citation",
                "extractor_version",
                "confidence_score",
                "human_correction_path",
            ],
            "detail_text": (
                "Semantic relation evidence is available from source-backed ontology "
                "relationship records."
            ),
            "provider_write_executed": False,
        }
    ]
    assert data["semantic_relation_evidence_samples"] == [
        {
            "sample_key": _expected_sample_key(
                "relation",
                "partner@example.com|<asset-ready@example.com>|thread-ready|Vendor",
            ),
            "relationship_type": "Vendor",
            "confidence_bucket": "high",
            "source_scope": "message_thread",
            "next_action": "prepare_response_draft",
        },
        {
            "sample_key": _expected_sample_key(
                "relation",
                "updates@example.com|<newsletter@example.com>||Newsletter",
            ),
            "relationship_type": "Newsletter",
            "confidence_bucket": "high",
            "source_scope": "message",
            "next_action": "summarize_then_archive",
        },
    ]
    assert data["attachment_parse_breakdown"] == [
        {
            "content_type": "application/octet-stream",
            "parse_content_type": "text/markdown",
            "parse_status": "parsed",
            "parser_key": "markdown",
            "display_name": "Markdown attachments",
            "object_count": 2,
            "evidence_source": (
                "email_attachments.content_type, "
                "email_attachments.parse_content_type, "
                "email_attachments.parse_status, email_attachments.parser_key"
            ),
            "provider_write_executed": False,
        },
        {
            "content_type": "application/pdf",
            "parse_content_type": "application/pdf",
            "parse_status": "unsupported_content_type",
            "parser_key": "unsupported_binary",
            "display_name": "Unsupported binary attachments",
            "object_count": 1,
            "evidence_source": (
                "email_attachments.content_type, "
                "email_attachments.parse_content_type, "
                "email_attachments.parse_status, email_attachments.parser_key"
            ),
            "provider_write_executed": False,
        },
    ]
    assert data["connector_events"][0]["event_uid"] == "connector_evt_data_quality"
    assert data["repository_assets"][0] == {
        "asset_key": data["repository_assets"][0]["asset_key"],
        "asset_type": "email_attachment",
        "display_name": "roadmap.pdf",
        "source_label": "Data source package",
        "state_code": "ready",
        "detail_text": "content and thread evidence ready",
        "content_chars": 25,
        "captured_at": "2026-05-28T05:45:00Z",
        "evidence_source": "attachments.content, emails.thread_id",
        "thread_key": data["repository_assets"][0]["thread_key"],
        "provider_write_executed": False,
    }
    assert data["repository_assets"][0]["asset_key"].startswith("asset_")
    assert data["repository_assets"][0]["thread_key"].startswith("thread_")
    assert data["repository_assets"][1]["state_code"] == "needs_attention"
    assert (
        data["repository_assets"][1]["source_label"]
        == "scriptQuarterly source pack/script"
    )

    serialized = response.text
    for forbidden in (
        "account_id",
        "folder_id",
        "credentials_encrypted",
        "credential secret",
        "username",
        "files@example.com",
        "https://files.acme.example",
        "webdav_path",
        "/Projects/Naruon_Roadmap_2026",
        "segmented body text",
        "cseg_email_paragraph_1",
        "kgedge_email_node_segment_1",
        "<asset-ready@example.com>",
        "<newsletter@example.com>",
        "partner@example.com",
        "updates@example.com",
        "thread-ready",
    ):
        assert forbidden not in serialized


def test_data_quality_evidence_snapshot_returns_shareable_redacted_surface(mock_db):
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.get("/api/data/quality-surface/evidence-snapshot")
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["snapshot_version"] == "data_quality_evidence_snapshot.v1"
    assert snapshot["audit_event"] == "data.quality_surface.evidence_snapshot.viewed"
    assert snapshot["scope_label"] == "signed_workspace_scope"
    assert snapshot["generated_at"].endswith("Z")
    assert snapshot["digest_algorithm"] == "sha256"
    assert len(snapshot["snapshot_digest"]) == 64
    assert set(snapshot["snapshot_digest"]) <= set("0123456789abcdef")
    digest_payload = dict(snapshot)
    for field_name in (
        "snapshot_digest",
        "digest_algorithm",
        "canonical_payload_fields",
    ):
        digest_payload.pop(field_name)
    canonical_payload = json.dumps(
        digest_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert snapshot["snapshot_digest"] == hashlib.sha256(canonical_payload).hexdigest()
    assert snapshot["canonical_payload_fields"] == sorted(digest_payload)
    assert "verification_handoff" in snapshot["canonical_payload_fields"]
    assert snapshot["verification_handoff"] == _expected_snapshot_verification_handoff()
    assert "evidence_packet_checklist" in snapshot["canonical_payload_fields"]
    assert snapshot["evidence_packet_checklist"] == _expected_evidence_packet_checklist()
    assert "data_room_package_manifest" in snapshot["canonical_payload_fields"]
    assert snapshot["data_room_package_manifest"] == _expected_data_room_package_manifest()
    assert "diligence_exception_register" in snapshot["canonical_payload_fields"]
    assert (
        snapshot["diligence_exception_register"]
        == _expected_diligence_exception_register()
    )
    assert "diligence_risk_matrix" in snapshot["canonical_payload_fields"]
    assert snapshot["diligence_risk_matrix"] == _expected_diligence_risk_matrix()
    assert "diligence_close_proof_plan" in snapshot["canonical_payload_fields"]
    assert (
        snapshot["diligence_close_proof_plan"]
        == _expected_diligence_close_proof_plan()
    )
    assert "diligence_close_decision_summary" in snapshot["canonical_payload_fields"]
    assert (
        snapshot["diligence_close_decision_summary"]
        == _expected_diligence_close_decision_summary()
    )
    assert "diligence_close_artifact_review_queue" in (
        snapshot["canonical_payload_fields"]
    )
    assert (
        snapshot["diligence_close_artifact_review_queue"]
        == _expected_diligence_close_artifact_review_queue()
    )
    assert "diligence_close_owner_handoff_queue" in (
        snapshot["canonical_payload_fields"]
    )
    assert (
        snapshot["diligence_close_owner_handoff_queue"]
        == _expected_diligence_close_owner_handoff_queue()
    )
    assert "diligence_close_traceability_map" in (
        snapshot["canonical_payload_fields"]
    )
    assert (
        snapshot["diligence_close_traceability_map"]
        == _expected_diligence_close_traceability_map()
    )
    for forbidden_field in (
        "snapshot_digest",
        "digest_algorithm",
        "canonical_payload_fields",
        "raw_email_body",
        "raw_html",
        "attachment_bytes",
        "message_id",
        "attachment_id",
        "source_record_id",
        "stable_database_id",
        "provider_credentials",
        "db_evidence_column_strings",
    ):
        assert forbidden_field not in snapshot["canonical_payload_fields"]
    assert snapshot["privacy_redaction_policy"]["raw_content_exposed"] is False
    assert snapshot["privacy_redaction_policy"]["stable_identifiers_exposed"] is False
    assert snapshot["privacy_redaction_policy"]["provider_credentials_exposed"] is False
    assert "raw_email_body" in snapshot["privacy_redaction_policy"]["redacted_fields"]
    assert snapshot["privacy_redaction_policy"]["allowed_sample_fields"] == [
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
    assert snapshot["validation_status"] == {
        "status_code": "needs_attention",
        "checks_passed": 3,
        "checks_with_issues": 9,
        "total_checks": 12,
    }
    assert "acquisition_readiness_gate" in snapshot["canonical_payload_fields"]
    assert snapshot["acquisition_readiness_gate"] == {
        "gate_key": "buyer_evidence_readiness",
        "display_name": "Buyer evidence readiness",
        "state_code": "needs_attention",
        "readiness_score": 25,
        "passed_checks": 3,
        "issue_checks": 9,
        "pending_checks": 0,
        "total_checks": 12,
        "blocking_check_keys": [
            "thread_id_integrity",
            "dedupe_fingerprint",
            "attachment_content",
            "content_graph_coverage",
            "knowledge_graph_coverage",
            "content_segment_text_readiness",
            "knowledge_graph_evidence_endpoint_readiness",
            "semantic_relation_source_backing",
        ],
        "evidence_packet_ready": True,
        "snapshot_verification_ready": True,
        "provider_write_executed": False,
        "kpis": _expected_acquisition_readiness_kpis(),
        "decision_summary": _expected_acquisition_decision_summary(),
        "remediation_actions": _expected_acquisition_remediation_actions(),
        "detail_text": (
            "Buyer evidence packet is generated, but blocking quality checks remain."
        ),
    }
    kpis = snapshot["acquisition_readiness_gate"]["kpis"]
    assert len(kpis) == 12
    assert kpis[0]["kpi_key"] == "thread_id_integrity_target"
    assert kpis[0]["current_percent"] == 75
    assert kpis[-1]["target_met"] is True
    summary = snapshot["acquisition_readiness_gate"]["decision_summary"]
    assert summary["recommendation_code"] == "remediate_before_close"
    assert summary["risk_level"] == "high"
    assert summary["target_gap_count"] == 9
    assert summary["provider_write_executed"] is False
    actions = snapshot["acquisition_readiness_gate"]["remediation_actions"]
    assert len(actions) == 9
    assert actions[0]["action_key"] == "repair_thread_id_integrity"
    assert actions[0]["provider_write_executed"] is False
    assert actions[-1]["action_key"] == "expand_attachment_parse_coverage"
    checklist = snapshot["evidence_packet_checklist"]
    assert len(checklist) == 10
    assert checklist[0]["checklist_key"] == "privacy_redaction_policy"
    assert checklist[8]["state_code"] == "needs_attention"
    assert checklist[-1]["source_field"] == "verification_handoff"
    data_room_manifest = snapshot["data_room_package_manifest"]
    assert len(data_room_manifest) == 10
    assert data_room_manifest[0]["file_name"] == "naruon-evidence-snapshot.json"
    assert data_room_manifest[5]["file_name"] == "knowledge-graph-evidence-samples.json"
    assert data_room_manifest[8]["state_code"] == "needs_attention"
    for item in data_room_manifest:
        assert item["required_for_close"] is True
        assert item["contains_raw_content"] is False
        assert item["contains_stable_identifiers"] is False
        assert item["provider_write_executed"] is False
    exception_register = snapshot["diligence_exception_register"]
    assert len(exception_register) == 9
    assert exception_register[0] == {
        "exception_key": "exception_repair_thread_id_integrity",
        "blocking_check_key": "thread_id_integrity",
        "display_name": "Canonical thread repair",
        "severity_code": "critical",
        "owner_area": "email_ingestion",
        "source_field": "quality_checks.thread_id_integrity",
        "related_artifact": "acquisition-readiness-summary.json",
        "blocks_close": True,
        "detail_text": "Thread provenance must be stable before buyer review.",
        "next_action": "Run canonical threading repair for affected scoped emails.",
        "provider_write_executed": False,
    }
    assert exception_register[-1]["exception_key"] == (
        "exception_expand_attachment_parse_coverage"
    )
    assert exception_register[-1]["severity_code"] == "medium"
    assert exception_register[-1]["related_artifact"] == "remediation-actions.json"
    assert all(item["blocks_close"] is True for item in exception_register)
    risk_matrix = snapshot["diligence_risk_matrix"]
    assert len(risk_matrix) == 6
    assert risk_matrix[0] == {
        "matrix_key": "risk_critical_email_ingestion_acquisition_readiness_summary_json",
        "severity_code": "critical",
        "owner_area": "email_ingestion",
        "related_artifact": "acquisition-readiness-summary.json",
        "exception_count": 2,
        "representative_exception_keys": [
            "exception_repair_thread_id_integrity",
            "exception_backfill_dedupe_fingerprints",
        ],
        "risk_label": "Critical close blocker concentration",
        "buyer_implication": (
            "2 critical exception(s) in email_ingestion affect "
            "acquisition-readiness-summary.json and block buyer close."
        ),
        "recommended_next_action": (
            "Resolve exception_repair_thread_id_integrity, "
            "exception_backfill_dedupe_fingerprints, then regenerate the "
            "evidence snapshot."
        ),
        "blocks_close": True,
        "provider_write_executed": False,
    }
    assert risk_matrix[-1]["matrix_key"] == (
        "risk_medium_attachment_parsing_remediation_actions_json"
    )
    assert risk_matrix[-1]["severity_code"] == "medium"
    assert risk_matrix[-1]["exception_count"] == 1
    assert all(item["blocks_close"] is True for item in risk_matrix)
    proof_plan = snapshot["diligence_close_proof_plan"]
    assert len(proof_plan) == 6
    assert proof_plan[0] == {
        "proof_key": "proof_risk_critical_email_ingestion_acquisition_readiness_summary_json",
        "severity_code": "critical",
        "owner_area": "email_ingestion",
        "related_artifact": "acquisition-readiness-summary.json",
        "exception_count": 2,
        "required_proof_artifact": "acquisition-readiness-summary.json",
        "acceptance_criteria": (
            "All 2 exception(s) for email_ingestion are resolved and "
            "acquisition-readiness-summary.json is regenerated without raw content "
            "or stable IDs."
        ),
        "verification_method": (
            "Regenerate the evidence snapshot and run python "
            "scripts/verify_evidence_snapshot.py <snapshot.json>."
        ),
        "buyer_close_dependency": "critical evidence gate",
        "close_gate_status": "blocked",
        "next_action": (
            "Resolve exception_repair_thread_id_integrity, "
            "exception_backfill_dedupe_fingerprints, then regenerate the "
            "evidence snapshot."
        ),
        "provider_write_executed": False,
    }
    assert proof_plan[-1]["proof_key"] == (
        "proof_risk_medium_attachment_parsing_remediation_actions_json"
    )
    assert proof_plan[-1]["severity_code"] == "medium"
    assert proof_plan[-1]["required_proof_artifact"] == "remediation-actions.json"
    assert proof_plan[-1]["close_gate_status"] == "blocked"
    assert snapshot["diligence_close_decision_summary"] == {
        "summary_key": "buyer_close_decision",
        "decision_code": "close_blocked",
        "total_proof_count": 6,
        "blocked_proof_count": 6,
        "ready_proof_count": 0,
        "critical_blocker_count": 1,
        "high_blocker_count": 4,
        "medium_blocker_count": 1,
        "required_artifact_count": 5,
        "required_artifacts": [
            "acquisition-readiness-summary.json",
            "dom-paragraph-evidence-samples.json",
            "knowledge-graph-evidence-samples.json",
            "remediation-actions.json",
            "semantic-relation-evidence-samples.json",
        ],
        "highest_severity": "critical",
        "snapshot_verification_required": True,
        "buyer_summary_text": (
            "Close remains blocked by 6 proof requirement(s) across "
            "5 required artifact(s)."
        ),
        "next_action_text": (
            "Resolve critical and high proof blockers, regenerate the "
            "evidence snapshot, and verify the copied JSON with the offline "
            "snapshot verifier."
        ),
        "provider_write_executed": False,
    }
    artifact_review_queue = snapshot["diligence_close_artifact_review_queue"]
    assert len(artifact_review_queue) == 5
    assert artifact_review_queue[0] == {
        "queue_key": "review_acquisition_readiness_summary_json",
        "required_proof_artifact": "acquisition-readiness-summary.json",
        "owner_areas": ["email_ingestion"],
        "proof_count": 1,
        "blocked_proof_count": 1,
        "ready_proof_count": 0,
        "highest_severity": "critical",
        "buyer_review_role": "executive diligence reviewer",
        "review_status": "blocked",
        "acceptance_summary": (
            "1 proof requirement(s) for acquisition-readiness-summary.json need "
            "executive diligence reviewer review before close."
        ),
        "next_action": (
            "Resolve exception_repair_thread_id_integrity, "
            "exception_backfill_dedupe_fingerprints, then regenerate the "
            "evidence snapshot."
        ),
        "snapshot_verification_required": True,
        "provider_write_executed": False,
    }
    assert artifact_review_queue[3]["required_proof_artifact"] == (
        "remediation-actions.json"
    )
    assert artifact_review_queue[3]["proof_count"] == 2
    assert artifact_review_queue[3]["highest_severity"] == "high"
    assert artifact_review_queue[3]["buyer_review_role"] == "data quality reviewer"
    assert artifact_review_queue[-1]["required_proof_artifact"] == (
        "semantic-relation-evidence-samples.json"
    )
    assert all(
        item["provider_write_executed"] is False for item in artifact_review_queue
    )
    owner_handoff_queue = snapshot["diligence_close_owner_handoff_queue"]
    assert len(owner_handoff_queue) == 5
    assert owner_handoff_queue[0] == {
        "handoff_key": "handoff_attachment_parsing",
        "owner_area": "attachment_parsing",
        "related_artifacts": ["remediation-actions.json"],
        "proof_count": 2,
        "blocked_proof_count": 2,
        "ready_proof_count": 0,
        "highest_severity": "high",
        "buyer_review_roles": ["data quality reviewer", "coverage reviewer"],
        "handoff_status": "blocked",
        "acceptance_summary": (
            "2 proof requirement(s) assigned to attachment_parsing affect "
            "1 artifact(s) before close."
        ),
        "next_action": (
            "Resolve exception_recover_attachment_content, then regenerate the "
            "evidence snapshot.; Resolve exception_expand_attachment_parse_coverage, "
            "then regenerate the evidence snapshot."
        ),
        "snapshot_verification_required": True,
        "provider_write_executed": False,
    }
    assert owner_handoff_queue[2]["owner_area"] == "email_ingestion"
    assert owner_handoff_queue[2]["highest_severity"] == "critical"
    assert owner_handoff_queue[2]["buyer_review_roles"] == [
        "executive diligence reviewer"
    ]
    assert owner_handoff_queue[-1]["owner_area"] == "semantic_kg"
    assert all(
        item["provider_write_executed"] is False for item in owner_handoff_queue
    )
    traceability_map = snapshot["diligence_close_traceability_map"]
    assert len(traceability_map) == 6
    assert traceability_map[0] == {
        "trace_key": "trace_risk_critical_email_ingestion_acquisition_readiness_summary_json",
        "source_field": "acquisition_readiness_gate",
        "data_room_artifact": "acquisition-readiness-summary.json",
        "manifest_key": "acquisition_readiness_summary",
        "exception_keys": [
            "exception_repair_thread_id_integrity",
            "exception_backfill_dedupe_fingerprints",
        ],
        "risk_key": "risk_critical_email_ingestion_acquisition_readiness_summary_json",
        "proof_key": "proof_risk_critical_email_ingestion_acquisition_readiness_summary_json",
        "artifact_review_key": "review_acquisition_readiness_summary_json",
        "owner_handoff_key": "handoff_email_ingestion",
        "owner_area": "email_ingestion",
        "severity_code": "critical",
        "exception_count": 2,
        "close_gate_status": "blocked",
        "buyer_review_roles": ["executive diligence reviewer"],
        "trace_summary": (
            "acquisition_readiness_gate feeds "
            "acquisition-readiness-summary.json for email_ingestion close proof "
            "traceability."
        ),
        "next_action": (
            "Resolve exception_repair_thread_id_integrity, "
            "exception_backfill_dedupe_fingerprints, then regenerate the "
            "evidence snapshot."
        ),
        "snapshot_verification_required": True,
        "provider_write_executed": False,
    }
    assert traceability_map[2]["source_field"] == "content_graph_evidence_samples"
    assert traceability_map[2]["data_room_artifact"] == (
        "dom-paragraph-evidence-samples.json"
    )
    assert traceability_map[3]["source_field"] == "knowledge_graph_evidence_samples"
    assert traceability_map[3]["data_room_artifact"] == (
        "knowledge-graph-evidence-samples.json"
    )
    assert traceability_map[-1]["source_field"] == (
        "acquisition_readiness_gate.remediation_actions"
    )
    assert traceability_map[-1]["owner_handoff_key"] == "handoff_attachment_parsing"
    assert all(
        item["provider_write_executed"] is False for item in traceability_map
    )
    assert "semantic_extraction_manifest" in snapshot["canonical_payload_fields"]
    assert "semantic_relation_evidence_samples" in snapshot["canonical_payload_fields"]
    assert snapshot["parser_manifest_summary"][0] == {
        "parser_key": "plain_text",
        "display_name": "Plain text attachments",
        "parse_status": "parsed",
        "content_types": ["text/plain"],
        "extensions": [".txt", ".text"],
    }
    assert snapshot["content_graph_topology_counts"] == [
        {"source_kind": "email_body", "segment_kind": "paragraph", "object_count": 6},
        {"source_kind": "attachment", "segment_kind": "heading", "object_count": 2},
    ]
    assert snapshot["knowledge_graph_topology_counts"] == [
        {"source_kind": "email_body", "edge_kind": "node_has_segment", "object_count": 8},
        {
            "source_kind": "attachment",
            "edge_kind": "heading_contains_segment",
            "object_count": 2,
        },
    ]
    assert snapshot["quality_checks"][0] == {
        "check_key": "thread_id_integrity",
        "display_name": "Thread id integrity",
        "status_code": "needs_attention",
        "issue_count": 1,
        "total_count": 4,
        "detail_text": "Some scoped emails need canonical thread ids.",
    }
    assert "evidence_source" not in snapshot["quality_checks"][0]
    assert "provider_write_executed" not in snapshot["quality_checks"][0]
    assert snapshot["content_graph_evidence_samples"][0] == {
        "sample_key": _expected_sample_key("segment", "cseg_email_paragraph_1"),
        "source_kind": "email_body",
        "segment_kind": "paragraph",
        "segment_path": "/document[1]/paragraph[1]",
        "word_count": 12,
    }
    assert snapshot["knowledge_graph_evidence_samples"][0] == {
        "sample_key": _expected_sample_key("edge", "kgedge_email_node_segment_1"),
        "source_kind": "email_body",
        "edge_kind": "node_has_segment",
        "edge_path": "/document[1]/paragraph[1]/has/segment[1]",
        "endpoint_status": "segment_backed",
    }
    assert snapshot["semantic_extraction_manifest"] == [
        {
            "manifest_key": "entity_relation_extraction",
            "display_name": "Entity/relation extraction",
            "state_code": "ready",
            "structural_edge_count": 10,
            "semantic_relation_count": 3,
            "source_backed_relation_count": 2,
            "required_evidence": [
                "segment_citation",
                "extractor_version",
                "confidence_score",
                "human_correction_path",
            ],
            "detail_text": (
                "Semantic relation evidence is available from source-backed ontology "
                "relationship records."
            ),
            "provider_write_executed": False,
        }
    ]
    assert snapshot["semantic_relation_evidence_samples"] == [
        {
            "sample_key": _expected_sample_key(
                "relation",
                "partner@example.com|<asset-ready@example.com>|thread-ready|Vendor",
            ),
            "relationship_type": "Vendor",
            "confidence_bucket": "high",
            "source_scope": "message_thread",
            "next_action": "prepare_response_draft",
        },
        {
            "sample_key": _expected_sample_key(
                "relation",
                "updates@example.com|<newsletter@example.com>||Newsletter",
            ),
            "relationship_type": "Newsletter",
            "confidence_bucket": "high",
            "source_scope": "message",
            "next_action": "summarize_then_archive",
        },
    ]

    serialized = response.text
    for forbidden in (
        "source email body",
        "extracted attachment text",
        "content_segments.source_kind",
        "knowledge_graph_edges.source_kind",
        "email_attachments.content_type",
        "cseg_email_paragraph_1",
        "kgedge_email_node_segment_1",
        "<asset-ready@example.com>",
        "<newsletter@example.com>",
        "partner@example.com",
        "updates@example.com",
        "thread-ready",
        "credentials_encrypted",
    ):
        assert forbidden not in serialized


def test_data_quality_surface_rejects_public_identity_headers_without_signed_session(
    mock_db,
):
    async def override_get_db():
        yield mock_db

    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/data/quality-surface",
                headers={
                    "X-User-Id": "admin",
                    "X-User-Role": "tenant_admin",
                    "X-Organization-Id": "org-acme",
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_member_data_quality_queries_are_owner_scoped(mock_db):
    token = _signed_session_token(
        _valid_session_payload(sub="member", role="member")
    )
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.get("/api/data/quality-surface")
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    rendered_queries = "\n".join(str(query) for query in mock_db.queries)
    assert "webdav_accounts.user_id = :user_id_1" in rendered_queries
    assert "webdav_accounts.workspace_id = :workspace_id_1" in rendered_queries
    assert "project_folders.user_id = :user_id_1" in rendered_queries
    assert "email_records.user_id = :user_id_1" in rendered_queries
    assert "email_records.workspace_id = :workspace_id_1" in rendered_queries
    assert "sender_relationships.user_id = :user_id_1" in rendered_queries


def test_data_quality_surface_includes_workspace_document_assets(mock_db):
    mock_db.documents.extend(
        [
            Document(
                document_id="doc_owned",
                workspace_id="workspace-org-acme",
                document_name="<b>roadmap.md</b>",
                document_type="text/markdown",
                document_content="# Roadmap",
                document_status="uploaded",
                created_at=_now(),
            ),
            Document(
                document_id="doc_rival",
                workspace_id="workspace-rival",
                document_name="rival.md",
                document_type="text/markdown",
                document_content="rival",
                document_status="uploaded",
                created_at=_now(),
            ),
        ]
    )
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.get("/api/data/quality-surface")
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    data = response.json()
    repositories_by_type = {
        repository["repository_type"]: repository for repository in data["repositories"]
    }
    assert repositories_by_type["document_repository"] == {
        "source_id": "document_repository",
        "repository_type": "document_repository",
        "display_name": "Scoped document repository",
        "object_count": 1,
        "writeback_enabled": None,
        "evidence_source": "documents",
        "provider_write_executed": False,
    }
    document_assets = [
        asset
        for asset in data["repository_assets"]
        if asset["asset_type"] == "workspace_document"
    ]
    assert document_assets == [
        {
            "asset_key": "doc_owned",
            "asset_type": "workspace_document",
            "display_name": "broadmap.md/b",
            "source_label": "Workspace document",
            "state_code": "ready",
            "detail_text": "document status: uploaded",
            "content_chars": 9,
            "captured_at": "2026-05-28T05:45:00Z",
            "evidence_source": "documents.document_status",
            "thread_key": "workspace_document",
            "provider_write_executed": False,
        }
    ]
    assert "doc_rival" not in response.text


def test_data_document_upload_creates_workspace_scoped_document(mock_db):
    token = _signed_session_token(_valid_session_payload(sub="member"))
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents",
            json={
                "document_name": "<b>roadmap.md</b>",
                "document_type": "text/markdown",
                "document_content": "# Roadmap\nPhase 10",
            },
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data == {
        "document_id": "doc_mock_1",
        "workspace_id": "workspace-org-acme",
        "document_name": "broadmap.md/b",
        "document_type": "text/markdown",
        "document_status": "uploaded",
        "content_chars": 18,
        "provider_write_executed": False,
        "provenance": "server-authoritative",
        "audit_event": "data.document.uploaded",
        "message": "Document stored in the signed workspace scope.",
    }
    stored_document = mock_db.documents[0]
    assert stored_document.workspace_id == "workspace-org-acme"
    assert stored_document.organization_id == "org-acme"
    assert stored_document.document_content == "# Roadmap\nPhase 10"


def test_data_document_actions_are_workspace_scoped_and_intent_only(mock_db):
    document = Document(
        document_id="doc_owned",
        workspace_id="workspace-org-acme",
        document_name="source.hwp",
        document_type="application/x-hwp",
        document_content="opaque hwp extraction placeholder",
        document_status="uploaded",
        created_at=_now(),
    )
    rival_document = Document(
        document_id="doc_rival",
        workspace_id="workspace-rival",
        document_name="rival.md",
        document_type="text/markdown",
        document_content="rival",
        document_status="uploaded",
        created_at=_now(),
    )
    mock_db.documents.extend([document, rival_document])
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        reparse_response = client.post("/api/data/documents/doc_owned/reparse")
        embedding_response = client.post(
            "/api/data/documents/doc_owned/embedding-regeneration-intent"
        )
        hwp_response = client.post(
            "/api/data/documents/doc_owned/hwp-conversion-intent"
        )
        rival_response = client.post("/api/data/documents/doc_rival/reparse")
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert reparse_response.status_code == 200, reparse_response.text
    assert reparse_response.json()["document_status"] == "parsed"
    assert reparse_response.json()["provider_write_executed"] is False
    assert reparse_response.json()["audit_event"] == "data.document.reparsed"

    assert embedding_response.status_code == 200, embedding_response.text
    embedding_data = embedding_response.json()
    assert embedding_data["document_status"] == "embedding_pending"
    assert embedding_data["provider_write_executed"] is False
    assert (
        embedding_data["audit_event"] == "data.document.embedding_regeneration_intent"
    )

    assert hwp_response.status_code == 200, hwp_response.text
    hwp_data = hwp_response.json()
    assert hwp_data["document_status"] == "hwp_conversion_pending"
    assert hwp_data["provider_write_executed"] is False
    assert hwp_data["audit_event"] == "data.document.hwp_conversion_intent"

    assert rival_response.status_code == 404
    assert "doc_rival" not in rival_response.text


def test_data_attachment_reparse_intent_transitions_quarantined_to_pending(mock_db):
    owned_email = _email("<owned-quarantine@example.com>", thread_id="thread-owned")
    attachment = _attachment("invoice.pdf", "")
    attachment.attachment_uid = "attachment_owned"
    attachment.content_type = "application/pdf"
    attachment.parse_content_type = "image/png"
    attachment.parse_status = "content_type_mismatch_quarantined"
    attachment.parse_error_code = "content_type_mismatch_quarantined"
    attachment.email = owned_email
    mock_db.attachments.append(attachment)

    token = _signed_session_token(_valid_session_payload(sub="owner"))
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/attachments/attachment_owned/reparse-intent"
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["attachment_uid"] == "attachment_owned"
    assert data["parse_status"] == "reparse_pending"
    assert data["parse_error_code"] is None
    assert data["provider_write_executed"] is False
    assert data["audit_event"] == "data.attachment.reparse_intent"
    assert attachment.parse_status == "reparse_pending"
    assert attachment.parse_error_code is None


def test_data_attachment_reparse_intent_locks_the_attachment_row(mock_db):
    # Concurrent reparse-intent requests (or a request racing the reparse
    # worker) must never read-then-blindly-overwrite the same unlocked row:
    # a stale request holding an earlier "quarantined" read could otherwise
    # clobber a result the worker already landed. Locking the row for the
    # duration of this transaction serializes that race, exactly like
    # calendar_conflict_judgment_service.apply_correction's FOR UPDATE.
    owned_email = _email("<owned-quarantine-lock@example.com>", thread_id="thread-owned")
    attachment = _attachment("invoice.pdf", "")
    attachment.attachment_uid = "attachment_owned_lock"
    attachment.content_type = "application/pdf"
    attachment.parse_content_type = "image/png"
    attachment.parse_status = "content_type_mismatch_quarantined"
    attachment.parse_error_code = "content_type_mismatch_quarantined"
    attachment.email = owned_email
    mock_db.attachments.append(attachment)

    token = _signed_session_token(_valid_session_payload(sub="owner"))
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/attachments/attachment_owned_lock/reparse-intent"
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    attachment_query = next(
        query
        for query in mock_db.queries
        if "email_attachments.attachment_uid = " in str(query).lower()
    )
    assert "FOR UPDATE" in str(attachment_query)


def test_data_attachment_reparse_intent_rejects_non_quarantined_status(mock_db):
    owned_email = _email("<owned-parsed@example.com>", thread_id="thread-owned")
    attachment = _attachment("notes.txt", "already parsed content")
    attachment.attachment_uid = "attachment_parsed"
    attachment.parse_status = "parsed"
    attachment.email = owned_email
    mock_db.attachments.append(attachment)

    token = _signed_session_token(_valid_session_payload(sub="owner"))
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/attachments/attachment_parsed/reparse-intent"
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 422, response.text
    assert attachment.parse_status == "parsed"


def test_data_attachment_reparse_intent_is_scoped_to_caller(mock_db):
    rival_email = _email(
        "<rival-quarantine@example.com>", thread_id="thread-rival"
    )
    rival_email.user_id = "rival-owner"
    rival_attachment = _attachment("payload.pdf", "")
    rival_attachment.attachment_uid = "attachment_rival"
    rival_attachment.parse_status = "content_type_mismatch_quarantined"
    rival_attachment.email = rival_email
    mock_db.attachments.append(rival_attachment)

    token = _signed_session_token(_valid_session_payload(sub="owner"))
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/attachments/attachment_rival/reparse-intent"
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 404
    assert "attachment_rival" not in response.text
    assert rival_attachment.parse_status == "content_type_mismatch_quarantined"


def test_data_attachment_reparse_intent_is_scoped_to_workspace(mock_db):
    # Same user_id and organization_id as the caller, but a DIFFERENT
    # workspace_id -- the IDOR class this same PR's new reparse-intent route
    # would otherwise open: Email carried no workspace_id at all before this
    # fix, so _email_scope_filter could only ever check user_id/organization_id.
    other_workspace_email = _email(
        "<other-workspace-quarantine@example.com>",
        thread_id="thread-other-workspace",
        workspace_id="workspace-rival",
    )
    other_workspace_attachment = _attachment("payload.pdf", "")
    other_workspace_attachment.attachment_uid = "attachment_other_workspace"
    other_workspace_attachment.parse_status = "content_type_mismatch_quarantined"
    other_workspace_attachment.email = other_workspace_email
    mock_db.attachments.append(other_workspace_attachment)

    token = _signed_session_token(_valid_session_payload(sub="owner"))
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/attachments/attachment_other_workspace/reparse-intent"
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 404
    assert "attachment_other_workspace" not in response.text
    assert (
        other_workspace_attachment.parse_status
        == "content_type_mismatch_quarantined"
    )


def test_data_document_webdav_materialization_executes_source_backed_write(
    mock_db,
    monkeypatch,
):
    mock_db.documents.append(
        Document(
            document_id="doc_owned",
            workspace_id="workspace-org-acme",
            document_name="../<b>roadmap.md</b>",
            document_type="text/markdown",
            document_content="# Roadmap\nPhase 10",
            document_status="uploaded",
            created_at=_now(),
        )
    )
    dispatched: list[tuple[str | None, str, dict[str, object]]] = []

    async def fake_dispatch_command(
        organization_id: str | None,
        workspace_id: str,
        command: dict[str, object],
    ) -> dict[str, object]:
        dispatched.append((organization_id, workspace_id, command))
        return {
            "status": "completed",
            "request_id": "runner_req_data_doc_1",
            "provider_status": 201,
            "provider_write_executed": True,
        }

    monkeypatch.setattr(
        data_api.runner_manager, "dispatch_command", fake_dispatch_command
    )
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents/doc_owned/webdav-materialization-intent",
            json={
                "target_source_id": "webdav_src_primary",
                "execute_provider": True,
            },
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "intent": "document_webdav_materialization",
        "status": "completed",
        "document_id": "doc_owned",
        "workspace_id": "workspace-org-acme",
        "document_name": "broadmap.md-b",
        "document_type": "text/markdown",
        "source_id": "webdav_src_primary",
        "target_label": "WebDAV source webdav_src_primary",
        "target_path": "/Naruon/Data/broadmap.md-b-d5fe4e8b.md",
        "requires_if_match": True,
        "if_match": "etag-webdav-primary",
        "provenance": "server-authoritative",
        "provider_write_executed": True,
        "audit_event": "data.document.webdav_materialization.executed",
        "runner_request_id": "runner_req_data_doc_1",
        "provider_status": 201,
        "error_code": None,
        "retry_item_uid": None,
        "message": "Workspace document WebDAV materialization executed by the connector.",
    }
    assert dispatched == [
        (
            "org-acme",
            "workspace-org-acme",
            {
                "action": "write_webdav",
                "account": "webdav_src_primary",
                "source_id": "webdav_src_primary",
                "target_path": "/Naruon/Data/broadmap.md-b-d5fe4e8b.md",
                "if_match": "etag-webdav-primary",
                "content_type": "text/markdown; charset=utf-8",
                "content": "# Roadmap\nPhase 10",
            },
        )
    ]
    serialized = response.text
    for forbidden in (
        "../",
        "<b>",
        "server_url",
        "username",
        "credentials_encrypted",
        "credential secret",
        "account_id",
    ):
        assert forbidden not in serialized


def test_data_document_webdav_materialization_rejects_empty_document(mock_db):
    mock_db.documents.append(
        Document(
            document_id="doc_empty",
            workspace_id="workspace-org-acme",
            document_name="empty.md",
            document_type="text/markdown",
            document_content="   ",
            document_status="uploaded",
            created_at=_now(),
        )
    )
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents/doc_empty/webdav-materialization-intent",
            json={
                "target_source_id": "webdav_src_primary",
                "execute_provider": True,
            },
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 422
    assert (
        response.json()["detail"] == "Workspace document has no materializable content."
    )


def test_data_document_webdav_materialization_rejects_pending_pdf(mock_db):
    # A PDF still pending NewsDOM recognition holds a base64 payload in
    # document_content; materializing it would write that binary as Markdown.
    mock_db.documents.append(
        Document(
            document_id="doc_pending",
            workspace_id="workspace-org-acme",
            document_name="contract.pdf",
            document_type="pdf",
            document_content="JVBERi0xLjcK",  # base64 %PDF-1.7\n
            document_status="pdf_dom_recognition_pending",
            created_at=_now(),
        )
    )
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents/doc_pending/webdav-materialization-intent",
            json={
                "target_source_id": "webdav_src_primary",
                "execute_provider": True,
            },
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 409, response.text
    assert "pending recognition" in response.json()["detail"]


def test_data_pdf_dom_recognition_intent_rejects_non_pdf_document(mock_db):
    mock_db.documents.append(
        Document(
            document_id="doc_text",
            workspace_id="workspace-org-acme",
            document_name="notes.md",
            document_type="text/markdown",
            document_content="# Notes",
            document_status="uploaded",
            created_at=_now(),
        )
    )
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents/doc_text/pdf-dom-recognition-intent",
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 415, response.text
    # A PDF document is accepted.
    mock_db.documents.append(
        Document(
            document_id="doc_pdf",
            workspace_id="workspace-org-acme",
            document_name="contract.pdf",
            document_type="pdf",
            document_content="JVBERi0xLjcK",
            document_status="uploaded",
            created_at=_now(),
        )
    )
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        ok = client.post(
            "/api/data/documents/doc_pdf/pdf-dom-recognition-intent",
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)
    assert ok.status_code == 200, ok.text
    assert ok.json()["document_status"] == "pdf_dom_recognition_pending"
    assert mock_db.documents[-1].organization_id == "org-acme"


def test_data_pdf_dom_recognition_intent_rejects_invalid_stored_payload(mock_db):
    mock_db.documents.append(
        Document(
            document_id="doc_invalid_pdf",
            workspace_id="workspace-org-acme",
            document_name="contract.pdf",
            document_type="pdf",
            document_content=base64.b64encode(b"not a PDF").decode("ascii"),
            document_status="uploaded",
            created_at=_now(),
        )
    )
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents/doc_invalid_pdf/pdf-dom-recognition-intent",
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "Stored PDF payload is not valid for DOM recognition."
    )
    assert mock_db.documents[-1].document_status == "uploaded"


def test_data_pdf_dom_upload_persists_signed_organization_scope(mock_db):
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        response = client.post(
            "/api/data/documents/pdf-dom-recognition",
            files={"file": ("contract.pdf", b"%PDF-1.7 test", "application/pdf")},
            data={"document_name": "contract.pdf"},
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert response.status_code == 200, response.text
    stored_document = mock_db.documents[-1]
    assert stored_document.organization_id == "org-acme"
    assert stored_document.document_status == "pdf_dom_recognition_pending"


def test_data_pdf_dom_upload_rejects_invalid_signature_and_size(mock_db, monkeypatch):
    token = _signed_session_token(_valid_session_payload())
    client, previous_secret, original_overrides = _with_signed_auth(mock_db, token)
    try:
        invalid = client.post(
            "/api/data/documents/pdf-dom-recognition",
            files={"file": ("contract.pdf", b"not a PDF", "application/pdf")},
        )
        monkeypatch.setattr(data_api, "_MAX_PDF_DOM_UPLOAD_BYTES", 5)
        oversized = client.post(
            "/api/data/documents/pdf-dom-recognition",
            files={"file": ("contract.pdf", b"%PDF-1.7", "application/pdf")},
        )
    finally:
        client.close()
        _restore_overrides(previous_secret, original_overrides)

    assert invalid.status_code == 415, invalid.text
    assert oversized.status_code == 413, oversized.text
    assert mock_db.documents == []


def test_pending_pdf_document_decoder_rejects_malformed_payloads(monkeypatch):
    malformed_base64 = Document(document_content="not@@base64")
    with pytest.raises(ValueError, match="valid base64"):
        data_api.decode_pending_pdf_document_bytes(malformed_base64)

    non_pdf = Document(
        document_content=base64.b64encode(b"not a PDF").decode("ascii")
    )
    with pytest.raises(ValueError, match="not a PDF"):
        data_api.decode_pending_pdf_document_bytes(non_pdf)

    monkeypatch.setattr(data_api, "_MAX_PDF_DOM_UPLOAD_BYTES", 5)
    oversized = Document(
        document_content=base64.b64encode(b"%PDF-1.7").decode("ascii")
    )
    with pytest.raises(ValueError, match="size limit"):
        data_api.decode_pending_pdf_document_bytes(oversized)


async def _seed_smoke_test_data(conn, ids: dict):
    await conn.execute(text("SELECT 1"))
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await conn.run_sync(Base.metadata.create_all)
    first_message_id = f"<data-smoke-{uuid.uuid4().hex}@example.com>"
    second_message_id = f"<data-smoke-missing-{uuid.uuid4().hex}@example.com>"
    rival_message_id = f"<data-rival-{uuid.uuid4().hex}@example.com>"
    first_email = await conn.execute(
        text(
            """
            INSERT INTO email_records (
                user_id, organization_id, workspace_id, message_id, thread_id,
                fingerprint, sender, recipients, subject, "date", body,
                is_read
            )
            VALUES (
                :user_id, :organization_id, :workspace_id, :message_id,
                :thread_id, :fingerprint, :sender, :recipients, :subject,
                now(), :body, true
            )
            RETURNING id
            """
        ),
        {
            "user_id": ids["user_id"],
            "organization_id": ids["organization_id"],
            "workspace_id": ids["workspace_id"],
            "message_id": first_message_id,
            "thread_id": "thread-data-smoke",
            "fingerprint": "sha256:data-smoke",
            "sender": "partner@example.com",
            "recipients": "owner@example.com",
            "subject": "Data smoke ready",
            "body": "ready body",
        },
    )
    second_email = await conn.execute(
        text(
            """
            INSERT INTO email_records (
                user_id, organization_id, workspace_id, message_id, sender,
                recipients, subject, "date", body, is_read
            )
            VALUES (
                :user_id, :organization_id, :workspace_id, :message_id,
                :sender, :recipients, :subject, now(), :body, true
            )
            RETURNING id
            """
        ),
        {
            "user_id": ids["user_id"],
            "organization_id": ids["organization_id"],
            "workspace_id": ids["workspace_id"],
            "message_id": second_message_id,
            "sender": "partner@example.com",
            "recipients": "owner@example.com",
            "subject": "Data smoke missing",
            "body": "missing body",
        },
    )
    rival_email = await conn.execute(
        text(
            """
            INSERT INTO email_records (
                user_id, organization_id, workspace_id, message_id, thread_id,
                fingerprint, sender, recipients, subject, "date", body,
                is_read
            )
            VALUES (
                :user_id, :organization_id, :workspace_id, :message_id,
                :thread_id, :fingerprint, :sender, :recipients, :subject,
                now(), :body, true
            )
            RETURNING id
            """
        ),
        {
            "user_id": ids["rival_user_id"],
            "organization_id": ids["rival_organization_id"],
            "workspace_id": ids["rival_workspace_id"],
            "message_id": rival_message_id,
            "thread_id": "thread-rival",
            "fingerprint": "sha256:rival",
            "sender": "rival@example.com",
            "recipients": "rival@example.com",
            "subject": "Rival",
            "body": "rival body",
        },
    )
    first_email_id = first_email.scalar_one()
    second_email_id = second_email.scalar_one()
    rival_email_id = rival_email.scalar_one()
    first_node_uid = f"cnode_{uuid.uuid4().hex[:24]}"
    rival_node_uid = f"cnode_{uuid.uuid4().hex[:24]}"
    first_segment_uid = f"cseg_{uuid.uuid4().hex[:24]}"
    rival_segment_uid = f"cseg_{uuid.uuid4().hex[:24]}"
    first_node = await conn.execute(
        text(
            """
            INSERT INTO content_nodes (
                content_node_uid, email_id, source_kind, source_record_uid,
                node_kind, node_path, ordinal_index, safe_text_content,
                content_hash, created_at
            )
            VALUES (
                :content_node_uid, :email_id, 'email_body',
                :source_record_uid, 'paragraph', '/document[1]/paragraph[1]',
                1, 'segmented body text', :content_hash, now()
            )
            RETURNING content_node_id
            """
        ),
        {
            "content_node_uid": first_node_uid,
            "email_id": first_email_id,
            "source_record_uid": f"email:{first_email_id}",
            "content_hash": hashlib.sha256(b"segmented body text").hexdigest(),
        },
    )
    rival_node = await conn.execute(
        text(
            """
            INSERT INTO content_nodes (
                content_node_uid, email_id, source_kind, source_record_uid,
                node_kind, node_path, ordinal_index, safe_text_content,
                content_hash, created_at
            )
            VALUES (
                :content_node_uid, :email_id, 'email_body',
                :source_record_uid, 'paragraph', '/document[1]/paragraph[1]',
                1, 'rival segmented body text', :content_hash, now()
            )
            RETURNING content_node_id
            """
        ),
        {
            "content_node_uid": rival_node_uid,
            "email_id": rival_email_id,
            "source_record_uid": f"email:{rival_email_id}",
            "content_hash": hashlib.sha256(b"rival segmented body text").hexdigest(),
        },
    )
    first_node_id = first_node.scalar_one()
    rival_node_id = rival_node.scalar_one()
    await conn.execute(
        text(
            """
            INSERT INTO content_segments (
                content_segment_uid, email_id, content_node_id, source_kind,
                source_record_uid, segment_kind, segment_path, ordinal_index,
                safe_text_content, content_hash, word_count, created_at
            )
            VALUES
            (
                :first_segment_uid, :first_email_id, :first_content_node_id,
                'email_body', :first_source_record_uid, 'paragraph',
                '/document[1]/paragraph[1]', 1, 'segmented body text',
                :first_content_hash, 3, now()
            ),
            (
                :rival_segment_uid, :rival_email_id, :rival_content_node_id,
                'email_body', :rival_source_record_uid, 'paragraph',
                '/document[1]/paragraph[1]', 1, 'rival segmented body text',
                :rival_content_hash, 4, now()
            )
            """
        ),
        {
            "first_segment_uid": first_segment_uid,
            "first_email_id": first_email_id,
            "first_content_node_id": first_node_id,
            "first_source_record_uid": f"email:{first_email_id}",
            "first_content_hash": hashlib.sha256(b"segmented body text").hexdigest(),
            "rival_segment_uid": rival_segment_uid,
            "rival_email_id": rival_email_id,
            "rival_content_node_id": rival_node_id,
            "rival_source_record_uid": f"email:{rival_email_id}",
            "rival_content_hash": hashlib.sha256(
                b"rival segmented body text"
            ).hexdigest(),
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO knowledge_graph_edges (
                edge_uid, email_id, source_node_id, target_segment_id,
                source_kind, source_record_uid, edge_kind, edge_path,
                ordinal_index, created_at
            )
            SELECT
                :first_edge_uid, CAST(:first_email_id AS INTEGER),
                CAST(:first_node_id AS INTEGER),
                first_segment.content_segment_id,
                'email_body', :first_source_record_uid, 'node_has_segment',
                '/document[1]/paragraph[1]/has/smoke', 1, now()
            FROM content_segments AS first_segment
            WHERE first_segment.content_segment_uid = :first_segment_uid
            UNION ALL
            SELECT
                :rival_edge_uid, CAST(:rival_email_id AS INTEGER),
                CAST(:rival_node_id AS INTEGER),
                rival_segment.content_segment_id,
                'email_body', :rival_source_record_uid, 'node_has_segment',
                '/document[1]/paragraph[1]/has/rival', 1, now()
            FROM content_segments AS rival_segment
            WHERE rival_segment.content_segment_uid = :rival_segment_uid
            """
        ),
        {
            "first_edge_uid": f"kgedge_{uuid.uuid4().hex[:32]}",
            "first_email_id": first_email_id,
            "first_node_id": first_node_id,
            "first_source_record_uid": f"email:{first_email_id}",
            "first_segment_uid": first_segment_uid,
            "rival_edge_uid": f"kgedge_{uuid.uuid4().hex[:32]}",
            "rival_email_id": rival_email_id,
            "rival_node_id": rival_node_id,
            "rival_source_record_uid": f"email:{rival_email_id}",
            "rival_segment_uid": rival_segment_uid,
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO sender_relationships (
                user_id, organization_id, sender_email, source_message_id,
                source_thread_id, relationship_type, confidence_score,
                created_at, updated_at
            )
            VALUES
            (
                :user_id, :organization_id, 'semantic-vendor@example.com',
                :first_message_id, 'thread-data-smoke', 'Vendor', 0.91,
                now(), now()
            ),
            (
                :rival_user_id, :rival_organization_id,
                'rival-semantic@example.com', :rival_message_id,
                'thread-rival', 'Vendor', 0.99, now(), now()
            )
            """
        ),
        {
            "user_id": ids["user_id"],
            "organization_id": ids["organization_id"],
            "first_message_id": first_message_id,
            "rival_user_id": ids["rival_user_id"],
            "rival_organization_id": ids["rival_organization_id"],
            "rival_message_id": rival_message_id,
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO email_attachments (
                attachment_uid, email_id, filename, content,
                content_type, parse_status, parse_content_type,
                parser_key, parse_error_code
            )
            VALUES
            (
                :first_attachment_uid, :first_email_id, 'ready.txt',
                'ready attachment', 'text/plain', 'parsed', 'text/plain',
                'plain_text', NULL
            ),
            (
                :second_attachment_uid, :second_email_id, 'blank.txt', '',
                'application/pdf', 'unsupported_content_type',
                'application/pdf', 'plain_text',
                'unsupported_content_type'
            ),
            (
                :rival_attachment_uid, :rival_email_id, 'rival.txt',
                'rival attachment', 'text/plain', 'parsed', 'text/plain',
                'plain_text', NULL
            )
            """
        ),
        {
            "first_attachment_uid": f"attachment_{uuid.uuid4().hex}",
            "first_email_id": first_email_id,
            "second_attachment_uid": f"attachment_{uuid.uuid4().hex}",
            "second_email_id": second_email_id,
            "rival_attachment_uid": f"attachment_{uuid.uuid4().hex}",
            "rival_email_id": rival_email_id,
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO webdav_accounts (
                source_uid, user_id, organization_id, workspace_id,
                server_url, username, credentials_encrypted,
                writeback_enabled,
                created_at
            )
            VALUES
            (
                :webdav_uid, :user_id, :organization_id, :workspace_id,
                'https://data-files.example/dav', 'data@example.com',
                :webdav_credentials, true, now()
            ),
            (
                :rival_webdav_uid, :rival_user_id, :rival_organization_id,
                :rival_workspace_id,
                'https://rival-files.example/dav', 'rival@example.com',
                :rival_webdav_credentials, true, now()
            )
            """
        ),
        {
            "webdav_uid": ids["webdav_uid"],
            "user_id": ids["user_id"],
            "organization_id": ids["organization_id"],
            "workspace_id": ids["workspace_id"],
            "webdav_credentials": get_fernet()
            .encrypt(b"data-smoke-webdav-secret")
            .decode("ascii"),
            "rival_webdav_uid": ids["rival_webdav_uid"],
            "rival_user_id": ids["rival_user_id"],
            "rival_organization_id": ids["rival_organization_id"],
            "rival_workspace_id": ids["rival_workspace_id"],
            "rival_webdav_credentials": get_fernet()
            .encrypt(b"data-rival-webdav-secret")
            .decode("ascii"),
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO project_folders (
                folder_uid, user_id, organization_id, project_name,
                webdav_path,
                created_at
            )
            VALUES (
                :folder_uid, :user_id, :organization_id,
                'Data Smoke Folder', '/Projects/Data_Smoke', now()
            )
            """
        ),
        {
            "folder_uid": ids["folder_uid"],
            "user_id": ids["user_id"],
            "organization_id": ids["organization_id"],
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO connector_signal_events (
                event_uid, organization_id, workspace_id, signal_key,
                state_code, detail_text, observed_at
            )
            VALUES
            (
                :event_uid, :organization_id, :workspace_id,
                'connector_heartbeat', 'heartbeat',
                'data smoke heartbeat', now()
            ),
            (
                :other_workspace_event_uid, :organization_id,
                'other_workspace', 'connector_heartbeat', 'heartbeat',
                'other workspace heartbeat', now()
            )
            """
        ),
        {
            "event_uid": ids["event_uid"],
            "other_workspace_event_uid": ids["other_workspace_event_uid"],
            "organization_id": ids["organization_id"],
            "workspace_id": ids["workspace_id"],
        },
    )


async def _teardown_smoke_test_data(conn, ids: dict):
    await conn.execute(
        text(
            "DELETE FROM sender_relationships "
            "WHERE user_id IN (:user_id, :rival_user_id)"
        ),
        {"user_id": ids["user_id"], "rival_user_id": ids["rival_user_id"]},
    )
    await conn.execute(
        text(
            """
            DELETE FROM knowledge_graph_edges
            WHERE email_id IN (
                SELECT id FROM email_records
                WHERE user_id IN (:user_id, :rival_user_id)
            )
            """
        ),
        {"user_id": ids["user_id"], "rival_user_id": ids["rival_user_id"]},
    )
    await conn.execute(
        text(
            """
            DELETE FROM content_segments
            WHERE email_id IN (
                SELECT id FROM email_records
                WHERE user_id IN (:user_id, :rival_user_id)
            )
            """
        ),
        {"user_id": ids["user_id"], "rival_user_id": ids["rival_user_id"]},
    )
    await conn.execute(
        text(
            """
            DELETE FROM content_nodes
            WHERE email_id IN (
                SELECT id FROM email_records
                WHERE user_id IN (:user_id, :rival_user_id)
            )
            """
        ),
        {"user_id": ids["user_id"], "rival_user_id": ids["rival_user_id"]},
    )
    await conn.execute(
        text(
            """
            DELETE FROM email_attachments
            WHERE email_id IN (
                SELECT id FROM email_records
                WHERE user_id IN (:user_id, :rival_user_id)
            )
            """
        ),
        {"user_id": ids["user_id"], "rival_user_id": ids["rival_user_id"]},
    )
    await conn.execute(
        text("DELETE FROM email_records WHERE user_id IN (:user_id, :rival_user_id)"),
        {"user_id": ids["user_id"], "rival_user_id": ids["rival_user_id"]},
    )
    await conn.execute(
        text(
            "DELETE FROM webdav_accounts "
            "WHERE source_uid IN (:webdav_uid, :rival_webdav_uid)"
        ),
        {
            "webdav_uid": ids["webdav_uid"],
            "rival_webdav_uid": ids["rival_webdav_uid"],
        },
    )
    await conn.execute(
        text("DELETE FROM project_folders WHERE folder_uid = :folder_uid"),
        {"folder_uid": ids["folder_uid"]},
    )
    await conn.execute(
        text(
            "DELETE FROM connector_signal_events "
            "WHERE event_uid IN (:event_uid, :other_workspace_event_uid)"
        ),
        {
            "event_uid": ids["event_uid"],
            "other_workspace_event_uid": ids["other_workspace_event_uid"],
        },
    )


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_data_quality_surface_real_postgres_smoke_uses_signed_scope(
    monkeypatch,
):
    database_url = getattr(settings, "DATABASE_URL", None)
    if not database_url:
        pytest.skip("PostgreSQL smoke path unavailable: DATABASE_URL is not set")

    # EncryptedString needs a key for both seeding (encrypt) and the API
    # read (decrypt); monkeypatch restores it on any exit incl. skip.
    monkeypatch.setattr(
        settings,
        "ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )

    user_id = f"data_smoke_user_{uuid.uuid4().hex[:12]}"
    organization_id = f"data_smoke_org_{uuid.uuid4().hex[:12]}"
    workspace_id = f"workspace_{organization_id}"
    rival_user_id = f"data_rival_user_{uuid.uuid4().hex[:12]}"
    rival_organization_id = f"data_rival_org_{uuid.uuid4().hex[:12]}"
    rival_workspace_id = f"workspace_{rival_organization_id}"
    webdav_uid = f"webdav_src_data_{uuid.uuid4().hex[:18]}"
    rival_webdav_uid = f"webdav_src_data_rival_{uuid.uuid4().hex[:12]}"
    folder_uid = f"webdav_folder_data_{uuid.uuid4().hex[:18]}"
    event_uid = f"connector_evt_data_{uuid.uuid4().hex[:18]}"
    other_workspace_event_uid = f"connector_evt_other_{uuid.uuid4().hex[:18]}"

    ids = {
        "user_id": user_id,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "rival_user_id": rival_user_id,
        "rival_organization_id": rival_organization_id,
        "rival_workspace_id": rival_workspace_id,
        "webdav_uid": webdav_uid,
        "rival_webdav_uid": rival_webdav_uid,
        "folder_uid": folder_uid,
        "event_uid": event_uid,
        "other_workspace_event_uid": other_workspace_event_uid,
    }

    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.begin() as conn:
            await _seed_smoke_test_data(conn, ids)
    except (
        ConnectionRefusedError,
        OSError,
        OperationalError,
        asyncpg.CannotConnectNowError,
        asyncpg.InvalidAuthorizationSpecificationError,
        asyncpg.InvalidCatalogNameError,
        asyncpg.InvalidPasswordError,
    ):
        await engine.dispose()
        pytest.skip("PostgreSQL smoke path unavailable")
    except Exception:
        await engine.dispose()
        raise

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_real_db():
        async with session_factory() as session:
            yield session

    previous_secret = settings.AUTH_SESSION_HMAC_SECRET
    original_overrides = dict(app.dependency_overrides)
    settings.AUTH_SESSION_HMAC_SECRET = SecretStr(TEST_SESSION_HMAC_SECRET)
    token = _signed_session_token(
        _valid_session_payload(
            sub=user_id,
            org=organization_id,
            workspace=workspace_id,
        )
    )
    app.dependency_overrides[get_db] = override_real_db
    app.dependency_overrides.pop(get_auth_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.get("/api/data/quality-surface")
    finally:
        settings.AUTH_SESSION_HMAC_SECRET = previous_secret
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        async with engine.begin() as conn:
            await _teardown_smoke_test_data(conn, ids)
        await engine.dispose()

    assert response.status_code == 200, response.text
    data = response.json()
    source_ids = {source["source_id"] for source in data["repositories"]}
    assert webdav_uid in source_ids
    assert folder_uid in source_ids
    assert rival_webdav_uid not in response.text
    quality_by_key = {check["check_key"]: check for check in data["quality_checks"]}
    assert quality_by_key["thread_id_integrity"]["issue_count"] == 1
    assert quality_by_key["dedupe_fingerprint"]["issue_count"] == 1
    assert quality_by_key["attachment_content"]["issue_count"] == 1
    assert quality_by_key["content_graph_coverage"]["issue_count"] == 1
    assert quality_by_key["knowledge_graph_coverage"]["issue_count"] == 1
    assert quality_by_key["semantic_relation_source_backing"]["issue_count"] == 0
    assert quality_by_key["attachment_parse_coverage"]["issue_count"] == 1
    assert data["semantic_extraction_manifest"][0]["semantic_relation_count"] == 1
    assert data["semantic_extraction_manifest"][0]["source_backed_relation_count"] == 1
    assert data["semantic_relation_evidence_samples"][0]["relationship_type"] == "Vendor"
    assert event_uid in {event["event_uid"] for event in data["connector_events"]}
    asset_names = {asset["display_name"] for asset in data["repository_assets"]}
    assert {"ready.txt", "blank.txt"} <= asset_names
    assert "rival.txt" not in response.text
    assets_by_name = {
        asset["display_name"]: asset for asset in data["repository_assets"]
    }
    assert assets_by_name["ready.txt"]["state_code"] == "ready"
    assert assets_by_name["blank.txt"]["state_code"] == "needs_attention"
    assert assets_by_name["ready.txt"]["asset_key"].startswith("asset_")
    assert assets_by_name["ready.txt"]["thread_key"].startswith("thread_")
    assert other_workspace_event_uid not in response.text
    assert "rival-semantic@example.com" not in response.text
    assert "semantic-vendor@example.com" not in response.text
    assert "account_id" not in response.text
    assert "encrypted-data-secret" not in response.text
    assert "data@example.com" not in response.text
