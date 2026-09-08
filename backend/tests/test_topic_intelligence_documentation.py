"""Machine-check the topic-intelligence documentation authority graph."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = REPO_ROOT / "docs" / "topic-intelligence"
SCHEMA_PATH = DOC_ROOT / "schema" / "topic-inference-result-v1.schema.json"

REQUIRED_DOCUMENTS = (
    "README.md",
    "PRD.md",
    "TRD.md",
    "ARCHITECTURE.md",
    "UML.md",
    "DATA_MODEL.md",
    "API_CONTRACT.md",
    "SECURITY.md",
    "THREAT_MODEL.md",
    "TEST_STRATEGY.md",
    "OPERABILITY.md",
    "TRACEABILITY.md",
    "DOCUMENTATION_FITNESS.md",
    "REFERENCES.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_topic_intelligence_package_is_complete_and_indexed() -> None:
    index = _read(DOC_ROOT / "README.md")

    for filename in REQUIRED_DOCUMENTS:
        assert (DOC_ROOT / filename).is_file()
        if filename != "README.md":
            assert f"({filename})" in index

    assert SCHEMA_PATH.is_file()
    assert "(schema/topic-inference-result-v1.schema.json)" in _read(
        DOC_ROOT / "API_CONTRACT.md"
    )


def test_topic_intelligence_package_is_discoverable_from_root_docs() -> None:
    for path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "ARCHITECTURE.md",
        REPO_ROOT / "CLAUDE.md",
    ):
        assert "docs/topic-intelligence/" in _read(path)


def test_maturity_vocabulary_separates_runtime_truth_from_design() -> None:
    index = _read(DOC_ROOT / "README.md")

    for status in (
        "IMPLEMENTED-ON-PROTECTED-DEVELOP",
        "ACTIVE-PR",
        "ACCEPTED-NARUON-POLICY",
        "PLANNED",
        "BLOCKED-UPSTREAM",
    ):
        assert status in index

    assert "not evidence that STM is available in Naruon" in " ".join(index.split())


def test_platform_plan_does_not_claim_live_stm_signals() -> None:
    plan = " ".join(
        _read(REPO_ROOT / "docs" / "planning" / "naruon-platform-plan.md").split()
    )

    assert "structured topic modeling (STM) feeds search" not in plan
    assert "account, STM topic, past patterns" not in plan
    assert "PLANNED, not LIVE" in plan
    assert "keyword_extractor` is never topic evidence" in plan


def test_contract_separates_errors_from_scientific_abstention() -> None:
    contract = _read(DOC_ROOT / "API_CONTRACT.md")
    normalized_contract = " ".join(contract.split())

    for status_code in ("`409`", "`422`", "`502`", "`503`"):
        assert status_code in contract
    assert "`error_code` is a required Naruon extension" in contract
    assert "`status=abstained`" in contract
    assert "must never return HTTP `200` or `status=abstained`" in normalized_contract


def test_uml_and_erd_are_conceptual_and_fail_closed() -> None:
    uml = _read(DOC_ROOT / "UML.md")
    data_model = _read(DOC_ROOT / "DATA_MODEL.md")

    assert uml.count("```mermaid") >= 4
    assert "no fallback transition" in uml
    assert "**Persistence status:** `NOT-APPLICABLE`" in data_model
    assert "no Alembic migration is authorized" in data_model
    assert data_model.count("```mermaid") >= 3


def test_conceptual_erd_uses_scoped_immutable_identities() -> None:
    data_model = _read(DOC_ROOT / "DATA_MODEL.md")
    agents = " ".join(_read(REPO_ROOT / "AGENTS.md").split())

    for scoped_reference in (
        "snapshot_ref PK",
        "model_artifact_ref PK",
        "component_ref PK",
        "label_evidence_ref PK",
    ):
        assert scoped_reference in data_model

    for unscoped_identity in (
        "string document_ref PK",
        "string model_id PK",
        "int topic_id PK",
        "int topic_id FK",
    ):
        assert unscoped_identity not in data_model

    assert "must not mark a reusable business identifier" in agents
    assert "as an unscoped primary or foreign key" in agents


def test_digest_contract_defines_one_schema_digest_and_raw_byte_boundary() -> None:
    contract = " ".join(_read(DOC_ROOT / "API_CONTRACT.md").split())
    index = " ".join(_read(DOC_ROOT / "README.md").split())

    assert "naruon.topic-inference.schema.v1" in contract
    assert (
        "the complete parsed JSON value of the immutable schema resource "
        "identified by the pinned `$id`"
    ) in contract
    assert "exactly 14 canonical digest fields" in contract
    assert "artifact_digest` binds the fitted-artifact **descriptor**" in contract
    assert "do not by themselves verify descriptor truth or completeness" in index
    assert "does not add a canonical digest field to this inventory" in index


def test_security_treats_every_derived_digest_as_sensitive() -> None:
    security = " ".join(_read(DOC_ROOT / "SECURITY.md").split())

    assert (
        "every content-, evidence-, covariate-, membership-, temporal-, design-, "
        "or label-derived digest. Such digests are sensitive pseudonymous linkage "
        "values"
    ) in security
    assert "sensitive pseudonymous linkage values" in security
    assert "ecological-fallacy" in security


def test_planned_schema_has_closed_revision_and_ownership_metadata() -> None:
    schema = json.loads(_read(SCHEMA_PATH))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "2026-08-09.1" in schema["$id"]
    assert schema["x-owner"] == "NARUON"
    assert "x-upstream-owner" not in schema
    assert schema["x-expected-upstream-producer"] == "TEPP"
    assert schema["x-runtime-status"] == "NOT_IMPLEMENTED"
    assert schema["x-schema-digest-required"] is True
    assert schema["additionalProperties"] is False
    assert schema["properties"]["status"]["enum"] == ["inferred", "abstained"]


def test_every_typed_schema_object_is_closed() -> None:
    schema = json.loads(_read(SCHEMA_PATH))

    def visit(value: object, location: str) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False, location
            for key, child in value.items():
                visit(child, f"{location}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{location}/{index}")

    visit(schema, "#")


def test_schema_requires_input_and_numerical_diagnostics() -> None:
    schema = json.loads(_read(SCHEMA_PATH))
    definitions = schema["$defs"]

    input_required = set(definitions["inputDiagnostics"]["required"])
    assert {"retained_token_count", "out_of_vocabulary_ratio"} <= input_required

    posterior_required = set(definitions["posteriorDiagnostics"]["required"])
    assert {
        "convergence_code",
        "numerical_status",
        "quality_codes",
    } <= posterior_required


def test_schema_declares_required_runtime_cross_field_validation() -> None:
    schema = json.loads(_read(SCHEMA_PATH))
    invariants = " ".join(schema["x-runtime-invariants"])

    for requirement in (
        "fitted_topic_count",
        "observed_topic_count",
        "number of topic_components",
        "snapshot_revision",
        "scope_binding_ref",
        "availability_time is at or before knowledge_cutoff_time",
        "unknown registry version or code is an upstream protocol error",
    ):
        assert requirement in invariants


def test_public_contract_preserves_semantics_and_fail_closed_errors() -> None:
    contract = _read(DOC_ROOT / "API_CONTRACT.md")

    for semantic_field in (
        '"model_id"',
        '"model_version"',
        '"analysis_unit"',
        '"estimand_id"',
        '"causal_design"',
        '"covariate_level"',
    ):
        assert semantic_field in contract

    for error_code in (
        "topic_authentication_required",
        "topic_evidence_forbidden",
        "topic_rate_limited",
        "topic_upstream_timeout",
        "topic_upstream_protocol_error",
    ):
        assert error_code in contract


def test_traceability_covers_every_product_requirement() -> None:
    prd = _read(DOC_ROOT / "PRD.md")
    traceability = _read(DOC_ROOT / "TRACEABILITY.md")

    for number in range(1, 11):
        requirement_id = f"TI-REQ-{number:03d}"
        assert requirement_id in prd
        assert requirement_id in traceability


def test_references_pin_the_inspected_tepp_evidence() -> None:
    references = _read(DOC_ROOT / "REFERENCES.md")

    assert "b8e26aae334397daa1974d4a24c9015cfd682600" in references
    assert "2026-08-06T11:33:18+09:00" in references
    assert "There is no corresponding" in references
    assert "production topic-measurement crate or endpoint" in references
