"""Regression tests for release governance artifacts.

These tests intentionally exercise repository-level release contracts from the
backend test suite so CI catches drift in versioning, changelog, and GitHub
workflow governance before a release branch can land.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import importlib.util
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
OCI_PREDEFINED_IMAGE_ANNOTATION_KEYS = {
    "org.opencontainers.image.created",
    "org.opencontainers.image.authors",
    "org.opencontainers.image.url",
    "org.opencontainers.image.documentation",
    "org.opencontainers.image.source",
    "org.opencontainers.image.version",
    "org.opencontainers.image.revision",
    "org.opencontainers.image.vendor",
    "org.opencontainers.image.licenses",
    "org.opencontainers.image.ref.name",
    "org.opencontainers.image.title",
    "org.opencontainers.image.description",
    "org.opencontainers.image.base.digest",
    "org.opencontainers.image.base.name",
}


def read_repo_text(relative_path: str) -> str:
    """Read a repository file with a clear assertion when it is missing."""
    path = REPO_ROOT / relative_path
    assert path.exists(), f"required governance artifact is missing: {relative_path}"
    return path.read_text(encoding="utf-8")


def assert_dockerfile_stage_from(dockerfile: str, image: str, stage_alias: str) -> None:
    pattern = (
        rf"^FROM {re.escape(image)}@sha256:[0-9a-f]{{64}} AS {re.escape(stage_alias)}$"
    )
    assert re.search(pattern, dockerfile, flags=re.MULTILINE), (
        f"missing pinned {image} stage alias {stage_alias}"
    )


def first_dockerfile_base_reference(dockerfile: str) -> str:
    """Return the first exact tag-and-digest Dockerfile base reference."""
    first_from = re.search(r"^FROM (?P<declaration>.+)$", dockerfile, flags=re.MULTILINE)
    assert first_from is not None, "Dockerfile must declare a base image"
    match = re.fullmatch(
        r"(?P<reference>[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+"
        r"@sha256:[0-9a-f]{64})(?: AS [A-Za-z0-9._-]+)?",
        first_from.group("declaration"),
    )
    assert match is not None, "Dockerfile first stage must use an exact tag-and-digest pin"
    return match.group("reference")


def assert_oci_metadata_matches_first_base(dockerfile: str) -> None:
    """Require OCI base metadata defaults to describe the real first stage."""
    base_reference = first_dockerfile_base_reference(dockerfile)
    image_reference, base_digest = base_reference.rsplit("@", 1)
    if "/" not in image_reference:
        image_reference = f"docker.io/library/{image_reference}"

    assert f'ARG OCI_IMAGE_BASE_DIGEST="{base_digest}"' in dockerfile
    assert f'ARG OCI_IMAGE_BASE_NAME="{image_reference}@{base_digest}"' in dockerfile


def test_root_version_exists_and_is_initial_semver_release() -> None:
    version = read_repo_text("VERSION").strip()

    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"VERSION is not valid SemVer: {version!r}"
    )


def test_release_version_sources_are_synchronized() -> None:
    version = read_repo_text("VERSION").strip()
    frontend_package = json.loads(read_repo_text("frontend/package.json"))
    backend_main = read_repo_text("backend/main.py")
    runtime_config = read_repo_text("backend/api/runtime_config.py")
    dockerfile = read_repo_text("Dockerfile")

    assert frontend_package["version"] == version
    assert "version=get_release_version()" in backend_main
    assert "version=get_release_version()" in runtime_config
    assert "COPY VERSION /app/VERSION" in dockerfile
    assert 'ARG OCI_IMAGE_TITLE="naruon"' in dockerfile
    assert 'org.opencontainers.image.title="${OCI_IMAGE_TITLE}"' in dockerfile
    assert 'ARG OCI_IMAGE_SOURCE="https://github.com/Seongho-Bae/naruon"' in dockerfile
    assert 'org.opencontainers.image.source="${OCI_IMAGE_SOURCE}"' in dockerfile


def test_container_images_cover_all_oci_predefined_image_annotations() -> None:
    root_dockerfile = read_repo_text("Dockerfile")
    frontend_dockerfile = read_repo_text("frontend/Dockerfile")
    docker_publish_workflow = read_repo_text(".github/workflows/docker-publish.yml")

    for annotation_key in OCI_PREDEFINED_IMAGE_ANNOTATION_KEYS:
        assert annotation_key in root_dockerfile
        assert annotation_key in frontend_dockerfile
        assert annotation_key in docker_publish_workflow

    assert (
        "DOCKER_METADATA_ANNOTATIONS_LEVELS: manifest,index" in docker_publish_workflow
    )
    assert (
        "annotations: ${{ steps.meta.outputs.annotations }}" in docker_publish_workflow
    )
    assert_oci_metadata_matches_first_base(root_dockerfile)
    assert_oci_metadata_matches_first_base(frontend_dockerfile)


def test_container_base_image_pins_are_synchronized() -> None:
    root_dockerfile = read_repo_text("Dockerfile")
    frontend_dockerfile = read_repo_text("frontend/Dockerfile")
    connector_dockerfile = read_repo_text("connector/Dockerfile")

    root_python = first_dockerfile_base_reference(root_dockerfile)
    connector_python = first_dockerfile_base_reference(connector_dockerfile)
    root_node_match = re.search(
        r"^FROM (?P<reference>node:26-slim@sha256:[0-9a-f]{64}) "
        r"AS frontend-builder$",
        root_dockerfile,
        flags=re.MULTILINE,
    )
    assert root_node_match is not None

    assert connector_python == root_python
    assert first_dockerfile_base_reference(frontend_dockerfile) == (
        root_node_match.group("reference")
    )


def test_container_images_use_pinned_node_runtimes() -> None:
    root_dockerfile = read_repo_text("Dockerfile")
    frontend_dockerfile = read_repo_text("frontend/Dockerfile")
    docker_publish_workflow = read_repo_text(".github/workflows/docker-publish.yml")
    render_deployment = read_repo_text("docs/operations/render-deployment.md")

    assert_dockerfile_stage_from(root_dockerfile, "node:26-slim", "frontend-builder")
    assert "FROM node:26-slim@sha256:" in frontend_dockerfile
    assert "docker.io/library/node:26-slim" in frontend_dockerfile
    assert "base_dockerfile: frontend/Dockerfile" in docker_publish_workflow
    assert 'base_name="docker.io/library/$base_reference"' in docker_publish_workflow
    assert "Node 26 toolchain" in render_deployment
    assert "node:24" not in root_dockerfile
    assert "node:24" not in frontend_dockerfile
    assert "node:24" not in docker_publish_workflow
    assert "Node 24" not in render_deployment
    assert "node:22" not in root_dockerfile
    assert "node:22" not in frontend_dockerfile
    assert "node:22" not in docker_publish_workflow
    assert "Node 22" not in render_deployment


def test_backend_images_use_python_314_runtime() -> None:
    root_dockerfile = read_repo_text("Dockerfile")
    docker_publish_workflow = read_repo_text(".github/workflows/docker-publish.yml")
    app_ci_workflow = read_repo_text(".github/workflows/app-ci.yml")
    bandit_workflow = read_repo_text(".github/workflows/bandit.yml")
    render_deployment = read_repo_text("docs/operations/render-deployment.md")

    assert_dockerfile_stage_from(root_dockerfile, "python:3.14-slim", "backend-runtime")
    assert "docker.io/library/python:3.14-slim" in root_dockerfile
    assert "base_dockerfile: Dockerfile" in docker_publish_workflow
    assert 'base_name="docker.io/library/$base_reference"' in docker_publish_workflow
    assert 'python-version: ["3.14"]' in app_ci_workflow
    assert 'python-version: "3.14"' in bandit_workflow
    assert "Python 3.14 toolchain" in render_deployment
    assert "python:3.11" not in root_dockerfile
    assert "python:3.11" not in docker_publish_workflow
    assert '"3.11"' not in app_ci_workflow
    assert '"3.12"' not in app_ci_workflow
    assert 'python-version: "3.12"' not in bandit_workflow


def test_python_314_backend_image_uses_binary_wheel_dependencies() -> None:
    dockerfile = read_repo_text("Dockerfile")
    requirements = read_repo_text("backend/requirements.txt")

    assert "PIP_ONLY_BINARY=:all:" in dockerfile
    assert "asyncpg==0.31.0" in requirements
    assert "tiktoken==0.13.0" in requirements
    assert "build-essential" not in dockerfile
    assert "cargo" not in dockerfile
    assert "libpq-dev" not in dockerfile
    assert (
        "COPY backend/requirements-hashes.txt /app/requirements-hashes.txt"
        in dockerfile
    )
    assert (
        "pip install --no-cache-dir --require-hashes -r requirements-hashes.txt"
        in dockerfile
    )


def test_backend_runtime_toolchain_uses_image_scan_clean_security_pins() -> None:
    requirements = read_repo_text("backend/requirements.txt")

    assert "sqlalchemy==2.0.51" in requirements
    assert "asyncpg==0.31.0" in requirements
    assert "tiktoken==0.13.0" in requirements
    assert "protobuf==7.35.1" in requirements
    assert "setuptools==83.0.0" in requirements
    assert "wheel==0.47.0" in requirements
    assert "opentelemetry-api==1.43.0" in requirements
    assert "opentelemetry-instrumentation-fastapi==0.64b0" in requirements


def test_strix_ci_requirements_use_security_quality_clean_pins() -> None:
    strix_ci_requirements = read_repo_text("requirements-strix-ci.txt")

    assert "strix-agent==1.0.4" in strix_ci_requirements
    assert "cryptography==50.0.0" in strix_ci_requirements
    assert "python-multipart==0.0.32" in strix_ci_requirements


def test_changelog_follows_keep_a_changelog_for_initial_korean_release() -> None:
    changelog = read_repo_text("CHANGELOG.md")

    assert "Keep a Changelog" in changelog
    assert "https://keepachangelog.com/en/1.0.0/" in changelog
    assert "## [0.1.0] - 2026-05-09" in changelog
    assert "[0.0.0.1]" not in changelog
    assert "@seonghobae" in changelog
    assert "Seongho Bae (@seonghobae)" in changelog


def test_github_actions_are_pinned_to_exact_sha() -> None:
    assert WORKFLOW_DIR.exists(), (
        "required governance artifact is missing: .github/workflows"
    )
    governed_workflows = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(
        WORKFLOW_DIR.glob("*.yaml")
    )
    assert governed_workflows, "no governed GitHub workflows found"

    unpinned_major_refs: list[str] = []
    missing_version_comments: list[str] = []
    major_only_action = re.compile(
        r"uses:\s*['\"]?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@v\d+['\"]?\s*$"
    )
    sha_without_version_comment = re.compile(
        r"uses:\s*['\"]?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}['\"]?\s*$"
    )
    for workflow_path in governed_workflows:
        workflow_lines = workflow_path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(workflow_lines, 1):
            if major_only_action.search(line):
                unpinned_major_refs.append(
                    f"{workflow_path.relative_to(REPO_ROOT).as_posix()}:"
                    f"{line_number}:{line.strip()}"
                )
            elif sha_without_version_comment.search(line):
                missing_version_comments.append(
                    f"{workflow_path.relative_to(REPO_ROOT).as_posix()}:"
                    f"{line_number}:{line.strip()}"
                )

    assert unpinned_major_refs == [], "\n".join(unpinned_major_refs)
    assert missing_version_comments == [], "\n".join(missing_version_comments)


def test_github_workflows_do_not_define_duplicate_top_level_keys() -> None:
    assert WORKFLOW_DIR.exists(), (
        "required governance artifact is missing: .github/workflows"
    )
    governed_workflows = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(
        WORKFLOW_DIR.glob("*.yaml")
    )
    assert governed_workflows, "no governed GitHub workflows found"

    duplicates: list[str] = []
    top_level_key = re.compile(r"^([A-Za-z0-9_-]+):(?:\s|$)")

    for workflow_path in governed_workflows:
        seen_keys: dict[str, int] = {}
        workflow_lines = workflow_path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(workflow_lines, 1):
            if (
                not line
                or line.startswith((" ", "\t"))
                or line.lstrip().startswith("#")
            ):
                continue
            match = top_level_key.match(line)
            if not match:
                continue

            key = match.group(1)
            if key in seen_keys:
                duplicates.append(
                    f"{workflow_path.relative_to(REPO_ROOT)}:{line_number}:"
                    f" duplicate top-level key {key!r}; first defined on line "
                    f"{seen_keys[key]}"
                )
            else:
                seen_keys[key] = line_number

    assert duplicates == [], "\n".join(duplicates)


def test_github_workflows_do_not_define_duplicate_mapping_keys() -> None:
    assert WORKFLOW_DIR.exists(), (
        "required governance artifact is missing: .github/workflows"
    )
    governed_workflows = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(
        WORKFLOW_DIR.glob("*.yaml")
    )
    assert governed_workflows, "no governed GitHub workflows found"

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(
        loader: yaml.SafeLoader,
        node: yaml.MappingNode,
        deep: bool = False,
    ) -> dict[object, object]:
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise AssertionError(
                    f"duplicate mapping key {key!r} on line "
                    f"{key_node.start_mark.line + 1}"
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )

    # Verify that UniqueKeyLoader is strictly a subclass of SafeLoader so that `# nosec B506`
    # suppression is genuinely justified according to PyYAML safety contracts.
    assert issubclass(UniqueKeyLoader, yaml.SafeLoader), (
        "UniqueKeyLoader must inherit from SafeLoader to suppress B506"
    )
    # Ensure that Python object instantiation tags (like !!python/object) are safely
    # rejected rather than executed.
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load("!!python/object/apply:os.system ['echo pwned']", Loader=UniqueKeyLoader)  # nosec B506
    # Ensure normal valid YAML loading still works
    assert yaml.load("a: 1\nb: 2", Loader=UniqueKeyLoader) == {"a": 1, "b": 2}  # nosec B506
    # Ensure the duplicate key prevention still works
    with pytest.raises(AssertionError, match="duplicate mapping key 'a'"):
        yaml.load("a: 1\na: 2", Loader=UniqueKeyLoader)  # nosec B506

    duplicates: list[str] = []
    for workflow_path in governed_workflows:
        try:
            # We explicitly pass UniqueKeyLoader (which inherits from SafeLoader).
            # Bandit B506 blindly flags yaml.load() regardless of the Loader argument.
            # This is a verified false positive.
            yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)  # nosec B506
        except AssertionError as exc:
            duplicates.append(f"{workflow_path.relative_to(REPO_ROOT)}: {exc}")

    assert duplicates == [], "\n".join(duplicates)


def test_stepsecurity_remediation_adds_pinned_audit_hardening() -> None:
    harden_runner_ref = (
        "step-security/harden-runner@bf7454d06d71f1098171f2acdf0cd4708d7b5920 # v2.20.0"
    )
    # Governance/security workflows (codeql, dependency-review, scorecard,
    # trivy) are centralized in the org-level ContextualWisdomLab/.github
    # required workflows and are intentionally not duplicated locally. Only the
    # functional workflows that remain in this repository are asserted here.
    hardened_workflows = [
        ".github/workflows/app-ci.yml",
        ".github/workflows/bandit.yml",
        ".github/workflows/docker-publish.yml",
        ".github/workflows/pr-governance.yml",
    ]

    for workflow_path in hardened_workflows:
        workflow = read_repo_text(workflow_path)
        assert harden_runner_ref in workflow
        assert "egress-policy: audit" in workflow

    # mail-smoke seeds live mailbox/DAV credentials on a self-hosted runner, so
    # it is hardened one level further: egress is blocked to an allowlist, not
    # merely audited, so checked-out code cannot exfiltrate the secrets.
    mail_smoke_workflow = read_repo_text(".github/workflows/mail-smoke.yml")
    assert harden_runner_ref in mail_smoke_workflow
    assert "egress-policy: block" in mail_smoke_workflow
    assert "allowed-endpoints:" in mail_smoke_workflow

    dependency_review_workflow = read_repo_text(
        ".github/workflows/dependency-review.yml"
    )
    assert (
        "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294 # v5.0.0"
        in dependency_review_workflow
    )
    assert "BASE_REF: ${{ github.base_ref || github.ref_name }}" in (
        dependency_review_workflow
    )
    assert "HEAD_REF: ${{ github.head_ref || github.ref_name }}" in (
        dependency_review_workflow
    )
    log_dependency_review_step = dependency_review_workflow.split(
        "- name: Log dependency review policy", 1
    )[1].split("- name: Review dependency changes", 1)[0]
    log_dependency_review_script = log_dependency_review_step.split("run: |", 1)[1]
    assert "${{ github.base_ref || github.ref_name }}" not in (
        log_dependency_review_script
    )
    assert "${{ github.head_ref || github.ref_name }}" not in (
        log_dependency_review_script
    )
    assert "printf 'Base ref: %s\\n' \"$BASE_REF\"" in log_dependency_review_script
    assert "printf 'Head ref: %s\\n' \"$HEAD_REF\"" in log_dependency_review_script

    pre_commit = read_repo_text(".pre-commit-config.yaml")
    assert "https://github.com/gitleaks/gitleaks" in pre_commit
    assert "rev: v8.16.3" in pre_commit
    assert "https://github.com/jumanjihouse/pre-commit-hooks" in pre_commit
    assert "rev: 3.0.0" in pre_commit
    assert "https://github.com/pre-commit/mirrors-eslint" in pre_commit
    assert "rev: v8.38.0" in pre_commit
    assert "https://github.com/pre-commit/pre-commit-hooks" in pre_commit
    assert "rev: v4.4.0" in pre_commit
    assert "https://github.com/pylint-dev/pylint" in pre_commit
    assert "rev: v2.17.2" in pre_commit


def test_actionlint_recognizes_the_mail_egress_runner_label() -> None:
    actionlint_config = read_repo_text(".github/actionlint.yaml")

    assert "self-hosted-runner:" in actionlint_config
    assert "- mail-egress" in actionlint_config


def test_github_actions_unpinned_major_refs_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    workflow_dir = repo_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow_file = workflow_dir / "bad-action.yml"
    workflow_file.write_text(
        "\n".join(
            [
                "name: bad action refs",
                "jobs:",
                "  test:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - uses: actions/checkout@v4",
            ]
        ),
        encoding="utf-8",
    )

    this_module = sys.modules[__name__]
    monkeypatch.setattr(this_module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(this_module, "WORKFLOW_DIR", workflow_dir)

    with pytest.raises(AssertionError) as exc_info:
        test_github_actions_are_pinned_to_exact_sha()

    message = str(exc_info.value).replace("\\", "/")
    assert ".github/workflows/bad-action.yml:6:- uses: actions/checkout@v4" in message

    workflow_file.write_text(
        "\n".join(
            [
                "name: missing version comment",
                "jobs:",
                "  test:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - uses: actions/setup-python@abcdef1234567890abcdef1234567890abcdef12",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError) as exc_info:
        test_github_actions_are_pinned_to_exact_sha()

    message = str(exc_info.value).replace("\\", "/")
    assert (
        ".github/workflows/bad-action.yml:6:- uses: "
        "actions/setup-python@abcdef1234567890abcdef1234567890abcdef12"
    ) in message


def test_bandit_security_scan_does_not_continue_on_error() -> None:
    workflow = read_repo_text(".github/workflows/bandit.yml")

    assert "continue-on-error: true" not in workflow


# CodeQL, Scorecard, and Trivy code-scanning workflows are centralized in the
# org-level ContextualWisdomLab/.github required workflows. Their local copies
# were removed to stop duplicate runs and duplicate SARIF uploads, so the
# repository-level assertions that previously guarded those local files no
# longer apply here and are enforced centrally instead.


def test_scorecard_sarif_normalizer_preserves_branch_protection_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sarif_path = tmp_path / "scorecard-results.sarif"
    sarif_path.write_text(
        json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {"driver": {"name": "Scorecard", "rules": []}},
                        "automationDetails": {"id": "supply-chain/local"},
                        "results": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    normalizer = REPO_ROOT / "scripts/ci/ensure_scorecard_sarif_categories.py"
    spec = importlib.util.spec_from_file_location("ensure_scorecard", normalizer)
    assert spec and spec.loader, "Failed to load module"
    ensure_scorecard_module = importlib.util.module_from_spec(spec)
    sys.modules["ensure_scorecard"] = ensure_scorecard_module
    spec.loader.exec_module(ensure_scorecard_module)
    monkeypatch.chdir(tmp_path)

    sarif_path.chmod(0o444)
    try:
        for argument in (str(sarif_path), "./scorecard-results.sarif"):
            ret = ensure_scorecard_module.main([str(normalizer), argument])
            assert ret == 0, f"Scorecard script failed with {ret}"
    finally:
        sarif_path.chmod(0o644)

    normalized = json.loads(sarif_path.read_text(encoding="utf-8"))
    categories = [
        run.get("automationDetails", {}).get("id") for run in normalized["runs"]
    ]
    assert categories.count("supply-chain/branch-protection") == 1
    branch_protection_run = next(
        run
        for run in normalized["runs"]
        if run.get("automationDetails", {}).get("id")
        == "supply-chain/branch-protection"
    )
    assert branch_protection_run["tool"]["driver"]["name"] == "Scorecard"
    assert branch_protection_run["results"] == []


def test_scorecard_sarif_normalizer_rejects_escape_links_and_large_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "scorecard-results.sarif"
    outside.write_text('{"runs": []}', encoding="utf-8")
    normalizer = REPO_ROOT / "scripts/ci/ensure_scorecard_sarif_categories.py"
    spec = importlib.util.spec_from_file_location(
        "ensure_scorecard_security", normalizer
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(workspace)

    assert module.main([str(normalizer), str(outside)]) == 65

    expected = workspace / "scorecard-results.sarif"
    expected.symlink_to(outside)
    assert module.main([str(normalizer), str(expected)]) == 65
    expected.unlink()

    outside_before = outside.read_bytes()
    os.link(outside, expected)
    assert module.main([str(normalizer), str(expected)]) == 65
    assert outside.read_bytes() == outside_before
    expected.unlink()

    expected.write_bytes(b" " * (module.MAX_SARIF_BYTES + 1))
    assert module.main([str(normalizer), str(expected)]) == 65


def test_review_automation_uses_central_required_workflows_without_local_copies() -> (
    None
):
    readme = read_repo_text("README.md")
    normalized_readme = " ".join(readme.split())
    architecture = read_repo_text("ARCHITECTURE.md")
    security = read_repo_text("SECURITY.md")
    normalized_security = " ".join(security.split())

    central_workflow_paths = [
        ".github/workflows/opencode-review.yml",
        ".github/workflows/pr-review-merge-scheduler.yml",
        ".github/workflows/strix-selftest.yml",
        ".github/workflows/strix.yml",
    ]
    central_script_paths = [
        "scripts/ci/collect_failed_check_evidence.sh",
        "scripts/ci/emit_opencode_failed_check_fallback_findings.sh",
        "scripts/ci/opencode_review_approve_gate.sh",
        "scripts/ci/opencode_review_normalize_output.py",
        "scripts/ci/pr_review_merge_scheduler.py",
        "scripts/ci/strix_model_utils.sh",
        "scripts/ci/strix_quick_gate.sh",
        "scripts/ci/test_strix_quick_gate.sh",
        "scripts/ci/validate_opencode_failed_check_review.sh",
    ]

    for relative_path in central_workflow_paths + central_script_paths:
        assert not (REPO_ROOT / relative_path).exists(), (
            f"central review automation must not be copied locally: {relative_path}"
        )

    assert "ContextualWisdomLab central required workflows" in normalized_readme
    assert "This repository does not carry repo-local" in normalized_readme
    assert "OpenCode, Strix, or merge-scheduler workflow copies" in normalized_readme
    assert (
        "branch updates, auto-merge, and mechanical merge actions" in normalized_readme
    )
    assert "central required workflows" in architecture
    assert "ContextualWisdomLab/.github" in architecture
    assert "central required workflow" in normalized_security
    assert "openai/openai/gpt-4.1" not in architecture


def test_app_ci_runs_backend_and_frontend_checks_without_duplicate_release_pushes() -> (
    None
):
    workflow = read_repo_text(".github/workflows/app-ci.yml")

    assert "pull_request:" in workflow
    assert "python -m pytest" in workflow
    assert "PYTHONWARNINGS: error" in workflow
    assert 'DISABLE_BACKGROUND_WORKERS: "1"' in workflow
    assert "npm test" in workflow
    assert "npm run lint" in workflow
    assert "npm run build" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "concurrency:" in workflow
    assert "${{ github.event.pull_request.number || github.ref }}" in workflow
    assert "uses: actions/checkout@v" not in workflow
    assert "uses: actions/setup-python@v" not in workflow
    assert "uses: actions/setup-node@v" not in workflow

    push_block = workflow.split("push:", 1)[1].split("pull_request:", 1)[0]
    assert "master" in push_block
    assert "release/**" not in push_block

    pull_request_block = workflow.split("pull_request:", 1)[1].split("push:", 1)[0]
    assert "branches:" not in pull_request_block, (
        "pull_request trigger must not exclude stacked PR base branches"
    )


def test_app_ci_collects_repository_root_governance_contract_tests() -> None:
    """The repo-root ``tests/`` contract suite must run in CI, not only locally.

    ``tests/test_stacked_pr_workflow_contract.py`` asserts on workflow YAML but
    lives outside ``backend/``, where the backend job's pytest invocation
    (``cd backend && python -m pytest -q``) never collects it. Without a
    dedicated step, a future trigger regression on the governed workflows
    could land without CI ever running that contract.

    Parses the workflow as YAML (rather than a raw substring match) so a
    comment that merely preserves the ``pytest -q tests`` text after the real
    step is deleted cannot satisfy this assertion, and additionally requires
    the same Timeout/Fatal/Warn/Denied output screening the backend test step
    already applies, so prohibited output from this step can't slip through
    Application CI unnoticed.
    """
    workflow = yaml.safe_load(read_repo_text(".github/workflows/app-ci.yml"))
    backend_steps = workflow["jobs"]["backend"]["steps"]
    root_test_steps = [
        step for step in backend_steps if "pytest -q tests" in (step.get("run") or "")
    ]
    assert len(root_test_steps) == 1, (
        "app-ci.yml's backend job must have exactly one real (non-commented) "
        "step running the repo-root tests/ suite"
    )
    root_test_run = root_test_steps[0]["run"]
    assert re.search(r"grep -qiE ['\"]timeout\|fatal\|warn\|denied['\"]", root_test_run), (
        "the repo-root tests/ step must screen its own output for "
        "Timeout/Fatal/Warn/Denied, like the backend test step does"
    )


def test_app_ci_repository_root_governance_step_runs_clean_under_warnings_as_error() -> (
    None
):
    """The repo-root ``tests/`` step must actually pass, not just be wired in.

    Live incident: the previous test confirms this step is wired into
    app-ci.yml, but the step itself crashed on every real CI run with an
    unhandled pytest ``INTERNALERROR`` -- the repo root had no pytest
    configuration setting ``asyncio_default_fixture_loop_scope``, so
    pytest-asyncio's ``pytest_configure`` hook emitted a
    ``PytestDeprecationWarning`` for that unset option, and the workflow
    step's ``PYTHONWARNINGS=error`` env (mirrored here) turned that warning
    into a fatal exception before pytest could even collect a single test.
    Reproduces the exact workflow invocation as a subprocess so this passes
    only when the real CI step would too.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONWARNINGS": "error"},
        capture_output=True,
        text=True,
    )
    assert "INTERNALERROR" not in result.stdout, result.stdout
    assert "INTERNALERROR" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stdout + result.stderr


def test_docker_publish_validates_pr_images_and_publishes_semver_images_only_on_tags() -> (
    None
):
    workflow = read_repo_text(".github/workflows/docker-publish.yml")

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in workflow
    assert (
        workflow.count(
            "docker/setup-qemu-action@96fe6ef7f33517b61c61be40b68a1882f3264fb8 # v4.2.0"
        )
        == 2
    )
    assert (
        workflow.count(
            "docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c # v4.2.0"
        )
        == 2
    )
    assert (
        "docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4.6.0"
        in workflow
    )
    assert (
        "docker/metadata-action@dc802804100637a589fabce1cb79ff13a1411302 # v6.2.0"
        in workflow
    )
    assert (
        workflow.count(
            "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7.3.0"
        )
        == 2
    )
    push_block = workflow.split("push:", 1)[1].split("pull_request:", 1)[0]
    pull_request_block = workflow.split("pull_request:", 1)[1].split("permissions:", 1)[
        0
    ]
    assert "tags:" in push_block
    assert "branches:" not in push_block
    assert "branches:" not in pull_request_block, (
        "pull_request trigger must not exclude stacked PR base branches"
    )
    assert "ai_email_client-backend" in workflow
    assert "ai_email_client-frontend" in workflow
    assert workflow.count("image: naruon") == 2
    assert "push: false" in workflow
    assert "push: true" in workflow
    assert workflow.count("base_dockerfile: Dockerfile") == 4
    assert workflow.count("base_dockerfile: frontend/Dockerfile") == 2
    assert workflow.count('base_digest="${base_reference##*@}"') == 2
    assert workflow.count('base_name="docker.io/library/$base_reference"') == 2
    assert "Resolve pinned Ollama base manifest" in workflow
    assert "docker buildx imagetools inspect" in workflow
    assert "Platform:[[:space:]]+${platform}[[:space:]]*$" in workflow
    assert "Pinned Ollama manifest is missing %s" in workflow
    assert "linux/amd64 linux/arm64" in workflow
    assert "sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061" not in workflow
    assert "sha256:191ef878ecb351d68b78219593de18bd8942afd59af59f29960dc4b24805a3f1" not in workflow
    assert "sbom: false" in workflow
    assert workflow.count("sbom: true") == 1
    assert "type=semver" in workflow
    assert "type=ref,event=branch" not in workflow
    assert "deploy_preflight:" in workflow
    assert "AKS_KUBECONFIG_CONTENT: ${{ secrets.AKS_KUBECONFIG }}" in workflow
    assert "configured=false" in workflow
    assert "skipping deploy workflow" in workflow
    assert (
        "needs.deploy_preflight.outputs.aks_kubeconfig_configured == 'true'" in workflow
    )


def test_frontend_dockerfile_builds_and_starts_production_artifact() -> None:
    root_dockerfile = read_repo_text("Dockerfile")
    dockerfile = read_repo_text("frontend/Dockerfile")
    docker_publish_workflow = read_repo_text(".github/workflows/docker-publish.yml")
    frontend_deployment = read_repo_text("k8s/frontend-deployment.yaml")
    package_json = read_repo_text("frontend/package.json")

    assert '"packageManager": "pnpm@11.5.3"' in package_json
    assert "NEXT_PUBLIC_API_URL" not in root_dockerfile
    assert "NEXT_PUBLIC_API_URL" not in dockerfile
    assert "NEXT_PUBLIC_API_URL" not in docker_publish_workflow
    assert "NEXT_PUBLIC_API_URL" not in frontend_deployment
    assert "BACKEND_INTERNAL_URL" in frontend_deployment
    assert "ALLOW_DOCKER_BACKEND_INTERNAL_URL" in frontend_deployment
    assert "BACKEND_INTERNAL_URL" in dockerfile
    assert dockerfile.index("BACKEND_INTERNAL_URL is intentionally runtime-only") < (
        dockerfile.index("RUN pnpm run build")
    )
    assert "pnpm run build" in dockerfile
    assert "ENV POSTCSS_WORKERS=1" in dockerfile
    assert "ENV DISABLE_POSTCSS_WORKERS=true" in dockerfile
    assert (
        'CMD sh -c "exec ./node_modules/.bin/next start --hostname 0.0.0.0 --port ${PORT:-3000}"'
        in dockerfile
    )
    assert "HEALTHCHECK --interval=30s --timeout=5s" in dockerfile
    assert "fetch('http://127.0.0.1:' + (process.env.PORT || '3000'))" in dockerfile
    assert "pnpm run start" not in dockerfile
    assert "pnpm run dev" not in dockerfile


def test_kubernetes_deployments_use_restricted_runtime_security_contexts() -> None:
    backend_deployment = read_repo_text("k8s/backend-deployment.yaml")
    db_statefulset = read_repo_text("k8s/db-statefulset.yaml")
    frontend_deployment = read_repo_text("k8s/frontend-deployment.yaml")

    assert (
        "image: ghcr.io/contextualwisdomlab/ai_email_client-backend"
        in backend_deployment
    )
    assert "image: docker.io/pgvector/pgvector:pg16" in db_statefulset
    assert (
        "image: ghcr.io/contextualwisdomlab/ai_email_client-frontend"
        in frontend_deployment
    )

    for manifest in (backend_deployment, db_statefulset, frontend_deployment):
        assert "namespace: naruon-dev" in manifest
        assert "seccompProfile:\n          type: RuntimeDefault" in manifest
        assert "allowPrivilegeEscalation: false" in manifest
        assert "capabilities:\n            drop:\n              - ALL" in manifest
        assert "readOnlyRootFilesystem: true" in manifest
        assert "runAsNonRoot: true" in manifest
        assert "resources:\n          requests:" in manifest
        assert "cpu:" in manifest
        assert "memory:" in manifest
        assert "mountPath: /tmp" in manifest

    assert "runAsUser: 10001" in backend_deployment
    assert "runAsGroup: 10001" in backend_deployment
    assert "runAsUser: 10001" in db_statefulset
    assert "runAsGroup: 10001" in db_statefulset
    assert "fsGroup: 10001" in db_statefulset
    assert "mountPath: /var/lib/postgresql/data" in db_statefulset
    assert "mountPath: /var/run/postgresql" in db_statefulset
    assert "runAsUser: 10001" in frontend_deployment
    assert "runAsGroup: 10001" in frontend_deployment
    assert "mountPath: /app/.next/cache" in frontend_deployment

    for service_manifest in (
        "k8s/backend-service.yaml",
        "k8s/db-service.yaml",
        "k8s/frontend-service.yaml",
        "k8s/ingress.yaml",
    ):
        assert "namespace: naruon-dev" in read_repo_text(service_manifest)


def test_backend_dockerfile_uses_modern_env_syntax() -> None:
    dockerfile = read_repo_text("Dockerfile")

    assert_dockerfile_stage_from(dockerfile, "python:3.14-slim", "backend-runtime")
    assert "ENV PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "ENV PYTHONUNBUFFERED=1" in dockerfile
    assert "pnpm install --frozen-lockfile" in dockerfile
    assert "pnpm run build" in dockerfile
    assert "FROM backend-runtime" in dockerfile
    # Node binary is copied into /app/bin (owned by appuser) to avoid USER root.
    assert (
        "COPY --from=frontend-builder --chown=appuser:appuser /usr/local/bin/node /app/bin/node"
        in dockerfile
    )
    assert "ENV PATH=/app/bin:$PATH" in dockerfile
    assert "USER root" not in dockerfile
    assert "nodejs" not in dockerfile
    assert "ENV PYTHONDONTWRITEBYTECODE 1" not in dockerfile
    assert "ENV PYTHONUNBUFFERED 1" not in dockerfile
    assert "secrets.token_hex" not in dockerfile
    assert "ENV DATABASE_URL=" not in dockerfile
    assert '"/app/scripts/docker_entrypoint.sh"' in dockerfile
    assert "RUN chmod +x /app/scripts/docker_entrypoint.sh" in dockerfile
    assert "HEALTHCHECK --interval=30s --timeout=5s" in dockerfile
    assert "http://127.0.0.1:8000/" in dockerfile
    assert "http://127.0.0.1:3000/" in dockerfile
    assert "useradd --system --create-home --home-dir /home/appuser" in dockerfile
    backend_cmd = 'CMD ["python", "scripts/start_backend.py", "--host", "0.0.0.0", "--port", "8000"]'
    assert dockerfile.find("USER appuser") < dockerfile.find(backend_cmd)
    assert dockerfile.rfind("USER appuser") < dockerfile.find(
        'CMD ["/app/scripts/docker_entrypoint.sh"]'
    )
    assert "COPY scripts/start_combined.sh" not in dockerfile
    assert "RUN echo '#!/bin/bash" not in dockerfile
    assert "uvicorn" not in dockerfile.split("CMD", 1)[1]


def test_combined_image_start_script_preflights_env_and_logs_service_exit() -> None:
    start_script = read_repo_text("backend/scripts/docker_entrypoint.sh")

    assert (
        "for var in DATABASE_URL AUTH_SESSION_HMAC_SECRET ENCRYPTION_KEY"
        in start_script
    )
    assert "Fernet.generate_key()" in start_script
    assert "validate_auth_session_hmac_secret_value" in start_script
    assert "AUTH_SESSION_HMAC_SECRET is invalid" in start_script
    assert "database migration failed" in start_script
    assert "Backend and frontend will not start." in start_script
    assert "Starting backend (uvicorn :8000)" in start_script
    assert "Starting frontend (next start :3000)" in start_script
    assert 'wait -n "$backend_pid" "$frontend_pid"' in start_script
    assert "Backend (:8000) exited with code" in start_script
    assert "Frontend (:3000) exited with code" in start_script


def test_deepwiki_qna_gap_execution_tracker_covers_requested_scope() -> None:
    tracker = read_repo_text("docs/development/deepwiki-qna-gap-execution-track.md")

    required_items = {
        "dav-propfind-db-backed",
        "alembic-migrations",
        "oidc-production-multi-user",
        "self-hosted-connector-adapters",
        "caldav-webdav-provider-write",
        "ready-soon-ui-removal",
        "postgresql-ha-physical-replication",
        "pop3-runtime-sync",
        "reply-sla-scheduler",
        "data-workspace-documents",
        "connector-apm-history",
        "sender-dag-source-filtering",
    }
    for item in required_items:
        assert item in tracker

    required_evidence = [
        "backend/api/dav.py",
        "backend/tests/test_dav_api.py",
        "backend/alembic/versions/0001_initial_control_plane.py",
        "backend/api/auth.py",
        "backend/runner/local_mail_adapters.py",
        "backend/runner/local_dav_adapters.py",
        "backend/api/calendar.py",
        "backend/api/webdav.py",
        "backend/api/observability.py",
        "backend/services/provider_writeback_retry_service.py",
        "backend/main.py",
        "backend/alembic/versions/0002_provider_writeback_retry_queue.py",
        "backend/tests/test_provider_writeback_retry_service.py",
        "backend/tests/test_observability_api.py",
        "backend/tests/test_main.py",
        "frontend/src/components/CalendarLayout.tsx",
        "frontend/src/app/calendar/page.test.tsx",
        "frontend/src/components/TasksLayout.tsx",
        "frontend/src/app/tasks/page.test.tsx",
        "frontend/src/components/DataLayout.tsx",
        "frontend/src/components/SettingsLayout.tsx",
        "frontend/src/components/SettingsLayout.test.tsx",
        "docs/operations/postgresql-physical-replication.md",
        "docs/operations/postgresql-ha-drill-20260615.md",
        "scripts/postgres_ha_drill.sh",
        "scripts/postgres-ha/init-primary-replication.sh",
        "backend/tests/test_infra_evaluations.py",
        "backend/core/config.py",
        "backend/db/session.py",
        "backend/tests/test_db_session.py",
        "backend/services/pop3_worker.py",
        "backend/services/reply_sla_scheduler.py",
        "backend/api/data.py",
        "backend/api/observability.py",
        "backend/api/ontology.py",
    ]
    for evidence_path in required_evidence:
        assert evidence_path in tracker

    assert "remaining_executable_goal" in tracker
    assert "verification_command" in tracker


def test_backend_compose_commands_use_startup_preflight() -> None:
    compose = read_repo_text("docker-compose.yml")
    live_e2e_compose = read_repo_text("docker-compose.live-e2e.yml")

    backend_block = compose.split("  backend:", 1)[1].split("  frontend:", 1)[0]
    assert "target: backend-runtime" in backend_block
    assert 'DEBUG: "false"' in backend_block
    assert "DEBUG: true" not in backend_block
    assert (
        "DATABASE_URL: postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@db:5432/ai_email"
        in backend_block
    )
    assert "READONLY_DATABASE_URL: ${READONLY_DATABASE_URL:-}" in backend_block
    assert "AUTH_SESSION_HMAC_SECRET: ${AUTH_SESSION_HMAC_SECRET}" in backend_block
    assert "ENCRYPTION_KEY: ${ENCRYPTION_KEY}" in backend_block
    assert "- AUTH_SESSION_HMAC_SECRET" not in backend_block
    assert "- ENCRYPTION_KEY" not in backend_block
    assert "python scripts/migrate_db.py && python scripts/start_backend.py" in compose
    assert "scripts/start_backend.py" in live_e2e_compose
    assert "Dockerfile.ollama" in live_e2e_compose
    assert (
        "DATABASE_URL: ${DATABASE_URL:?Set DATABASE_URL for live E2E}"
        in live_e2e_compose
    )
    assert "postgresql+asyncpg://" not in live_e2e_compose
    assert '"127.0.0.1:18080:8080"' in live_e2e_compose
    assert 'OLLAMA_NO_CLOUD: "true"' in compose
    assert 'OLLAMA_NO_CLOUD: "true"' in live_e2e_compose
    assert "OPENAI_BASE_URL: http://ollama:11434/v1" in live_e2e_compose
    assert "OPENAI_MODEL: gemma4:e2b-it-qat" in live_e2e_compose
    assert "OPENAI_EMBEDDING_MODEL: embeddinggemma" in live_e2e_compose
    assert "live-e2e-state:/live-e2e-state" in live_e2e_compose
    assert "touch /live-e2e-state/migrated" in live_e2e_compose
    assert "touch /live-e2e-state/seeded" in live_e2e_compose
    assert "Required startup marker missing: $$marker" in live_e2e_compose
    assert "  live-e2e-state:" in live_e2e_compose
    live_backend_block = live_e2e_compose.split("  backend:", 1)[1].split(
        "  frontend:", 1
    )[0]
    assert "ALLOWED_CORS_ORIGINS: http://127.0.0.1:18080" in live_backend_block
    live_frontend_block = live_e2e_compose.split("  frontend:", 1)[1].split(
        "  nginx:", 1
    )[0]
    assert "NEXT_PUBLIC_API_URL" not in live_frontend_block
    assert "BACKEND_INTERNAL_URL: http://backend:8000" in live_frontend_block
    assert 'ALLOW_DOCKER_BACKEND_INTERNAL_URL: "1"' in live_frontend_block
    assert "TRUSTED_FRONTEND_ORIGINS: http://127.0.0.1:18080" in live_frontend_block
    live_nginx = read_repo_text("tests/live/nginx.conf")
    assert "proxy_read_timeout 600s" in live_nginx
    assert (
        'add_header Referrer-Policy "strict-origin-when-cross-origin" always;'
        in live_nginx
    )
    assert 'add_header X-Content-Type-Options "nosniff" always;' in live_nginx
    assert 'add_header X-Frame-Options "DENY" always;' in live_nginx
    assert "upstream live_backend" not in live_nginx
    api_location = live_nginx.split("    location /api/ {", 1)[1].split("    }", 1)[0]
    root_location = live_nginx.split("    location / {", 1)[1].split("    }", 1)[0]
    for location in (api_location, root_location):
        assert "proxy_set_header Host $http_host;" in location
        assert "proxy_set_header X-Forwarded-Host $http_host;" in location
        assert "proxy_set_header X-Real-IP $remote_addr;" in location
        assert (
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in location
        )
        assert "proxy_set_header X-Forwarded-Proto $scheme;" in location
        assert "proxy_set_header Upgrade $http_upgrade;" in location
        assert 'proxy_set_header Connection "upgrade";' in location
    assert "proxy_pass http://live_frontend;" in api_location
    assert "proxy_pass http://live_backend;" not in api_location


def test_compose_log_scanner_exists_for_warning_policy() -> None:
    scanner = read_repo_text("scripts/check_compose_logs.py")

    assert "warning|warn|deprecated|notice|fatal|denied|unable" in scanner
    assert "allowed_count" in scanner
    assert "unexpected_count" in scanner
    assert "Use --ui/--no-ui" in scanner
    assert "or deprecated --webui/--no-webui" in scanner


def test_compose_log_scanner_allows_nginx_stderr_startup_notices() -> None:
    nginx_startup_lines = "\n".join(
        [
            '2026/06/13 06:25:27 [notice] 1#1: using the "epoll" event method',
            "2026/06/13 06:25:27 [notice] 1#1: nginx/1.27.5",
            "2026/06/13 06:25:27 [notice] 1#1: built by gcc 14.2.0 (Alpine 14.2.0)",
            "2026/06/13 06:25:27 [notice] 1#1: OS: Linux 6.19.7-200.fc43.aarch64",
            "2026/06/13 06:25:27 [notice] 1#1: getrlimit(RLIMIT_NOFILE): 524288:524288",
            "2026/06/13 06:25:27 [notice] 1#1: start worker processes",
            "2026/06/13 06:25:27 [notice] 1#1: start worker process 16",
        ]
    )

    scanner_script = REPO_ROOT / "scripts/check_compose_logs.py"
    spec = importlib.util.spec_from_file_location("check_compose_logs", scanner_script)
    assert spec and spec.loader, "Failed to load module"
    check_compose_logs_module = importlib.util.module_from_spec(spec)
    sys.modules["check_compose_logs"] = check_compose_logs_module
    spec.loader.exec_module(check_compose_logs_module)

    unexpected, allowed = check_compose_logs_module.scan_lines(
        nginx_startup_lines.splitlines()
    )
    assert not unexpected, f"Unexpected lines found: {unexpected}"
    assert len(allowed) == 7, f"Expected 7 allowed lines, got {len(allowed)}"


def test_pr_governance_uses_metadata_only_events_without_checkout_or_admin_merge() -> (
    None
):
    workflow = read_repo_text(".github/workflows/pr-governance.yml")
    gate_script = read_repo_text("scripts/ci/pr_governance_gate.sh")
    combined = f"{workflow}\n{gate_script}"

    assert "pull_request_target:" in workflow
    assert "pull_request_review:" in workflow
    assert "types: [submitted, dismissed]" in workflow
    assert "workflow_run:" in workflow
    assert "check_run:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "Strix Security Scan" in workflow
    assert "- strix" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "trusted-governance" in workflow
    assert ".base.sha" in workflow
    assert "github.sha" not in workflow
    assert "tarball/${trusted_ref}" in workflow
    assert "gh_api_with_retry" in workflow
    assert "extract_json_value" in workflow
    assert "empty response body" in workflow
    assert "invalid JSON response body" in workflow
    assert "returned invalid JSON" in workflow
    assert "did not produce valid JSON after 4 attempts" in workflow
    assert "GitHub API request attempt" in workflow
    assert "Trusted governance ref must be a full commit SHA" in workflow
    assert "trusted_archive_candidate" in workflow
    assert "tar -tzf" in workflow
    assert "Trusted governance archive materialization attempt" in workflow
    assert "after 4 attempts" in workflow
    assert 'bash "$GOVERNANCE_GATE"' in workflow
    assert "CHECK_RUN_PR_NUMBER" in workflow
    assert "headRefOid" in gate_script
    assert "mergeStateStatus" in gate_script
    assert "Merge state lookup attempt" in gate_script
    assert "Merge state is still UNKNOWN after 4 attempts" in gate_script
    assert "PR state became %s during merge-state refresh" in gate_script
    assert "PR head changed during gate evaluation" in gate_script
    assert "skipping stale gate publication" in gate_script
    assert "gh pr checks" in gate_script and "--required" in gate_script
    assert "no required checks reported" in gate_script
    assert "no legacy required status contexts reported" in gate_script
    assert "add_waiting" in gate_script
    assert "check-runs" in gate_script
    assert "Review skipped" in gate_script
    assert "CodeRabbit" in gate_script or "coderabbit" in gate_script
    assert "BEHIND" in gate_script
    assert "app.slug" in gate_script
    assert "coderabbitai" in gate_script
    assert "/issues/${PR_NUMBER}/comments" in gate_script
    assert "COMMENT_MARKER" in gate_script
    assert "no current blocking failures remain" in gate_script
    assert "Waiting for" in gate_script
    assert "reviewThreads" in gate_script
    assert "CHANGES_REQUESTED" in gate_script
    assert "gh pr merge" not in gate_script
    assert "--match-head-commit" not in gate_script
    assert "actions/checkout" not in combined
    assert "@coderabbitai ignore" not in combined
    assert "git clone" not in combined
    assert "--admin" not in combined
    assert "contents: write" not in combined
    assert "continue-on-error: true" not in combined
    assert "/dismissals" not in combined.lower()
    assert "dismisspullrequestreview" not in combined.lower()


def test_20b_kpi_roi_claim_gate_separates_measurements_from_assumptions() -> None:
    kpi_report = read_repo_text(
        "docs/superpowers/reports/2026-07-02-naruon-kpi-validation.md"
    )
    buyer_package = read_repo_text(
        "docs/superpowers/reports/2026-07-02-naruon-20b-buyer-package.md"
    )
    security_questionnaire = read_repo_text(
        "docs/superpowers/reports/2026-07-02-naruon-20b-security-questionnaire.md"
    )
    readiness_plan = read_repo_text(
        "docs/superpowers/plans/2026-07-02-naruon-20b-full-product-commercial-readiness.md"
    )

    assert "### ROI Model And Claim Gate" in kpi_report
    assert "estimated_period_value_krw" in kpi_report
    for model_input in (
        "time_saved_per_user_per_week_hours",
        "fully_loaded_hourly_cost_krw",
        "weekly_active_users",
        "evidence_open_rate",
        "decision_to_action_conversion_rate",
        "pilot_period_weeks",
        "risk_reduction_adjustment",
    ):
        assert model_input in kpi_report

    assert "Measured value unavailable in this branch" in kpi_report
    assert "must not be presented as a proven value" in kpi_report
    assert "Naruon has proven a 20B KRW ROI" in kpi_report
    assert "No live ROI number should be claimed" in buyer_package
    assert "live measured data" in buyer_package
    assert "live measured data is required before ROI claims" in security_questionnaire
    assert "- [x] **Step 2: Define ROI model**" in readiness_plan
    assert "- [ ] **Step 2: Define ROI model**" not in readiness_plan


def test_20b_buyer_package_rejects_final_procurement_claim_language() -> None:
    buyer_package = read_repo_text(
        "docs/superpowers/reports/2026-07-02-naruon-20b-buyer-package.md"
    )
    demo_script = read_repo_text(
        "docs/superpowers/reports/2026-07-02-naruon-20b-demo-script.md"
    )
    telemetry_report = read_repo_text(
        "docs/superpowers/reports/2026-07-02-naruon-design-to-code-telemetry-qa.md"
    )

    assert "Accepted buyer-review language:" in buyer_package
    assert "Rejected language:" in buyer_package
    assert "## Do Not Say" in demo_script
    for rejected_claim in (
        "Naruon is public-launch ready.",
        "Live ROI has been proven.",
        "All provider writes are production-proven.",
    ):
        assert rejected_claim in demo_script

    assert "controlled enterprise buyer technical review" in buyer_package
    assert "not a final public-launch or contract-close claim" in buyer_package
    assert "not a claim that Naruon is ready for public SaaS launch" in telemetry_report


def test_coderabbit_approval_is_decoupled_from_github_checks() -> None:
    config = read_repo_text(".coderabbit.yaml")
    policy = read_repo_text("docs/development/merge-gate-policy.md")
    agents = read_repo_text("AGENTS.md")

    assert "request_changes_workflow: true" in config
    assert "github-checks:" in config
    assert "enabled: false" in config
    assert "GitHub Checks integration stays disabled" in policy
    assert "GitHub Checks integration disabled" in agents


def test_agents_records_ghcr_visibility_publication_runbook() -> None:
    agents = read_repo_text("AGENTS.md")
    normalized_agents = " ".join(agents.split())

    assert "GHCR publishing evidence for the combined `naruon` image" in agents
    assert "REST Packages API" in agents
    assert "GraphQL package mutations" in agents
    assert "visibility: private" in agents
    assert "Package settings" in agents
    assert "Danger Zone" in agents
    assert "Change visibility" in normalized_agents
    assert "anonymous pull/token access" in agents
