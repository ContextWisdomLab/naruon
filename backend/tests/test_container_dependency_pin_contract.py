"""Regression contracts for container and release dependency security pins.

The container-provenance process depends on repository tests, not prose alone,
to keep independently versioned Python and JavaScript toolchains on the exact
reviewed security floor. These checks parse source manifests, hash-locked Python
artifacts, and the generated pnpm lock so a direct pin cannot drift away from the
resolved artifact graph or pass through an incidental substring match.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
_HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_EXACT_PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)")


def read_repo_text(relative_path: str) -> str:
    """Return one required repository file as UTF-8 text."""
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"required pin contract file is missing: {relative_path}"
    return path.read_text(encoding="utf-8")


def exact_requirement_pins(requirements_text: str) -> dict[str, str]:
    """Parse exact direct requirement pins by normalized package name."""
    pins: dict[str, str] = {}
    for raw_line in requirements_text.splitlines():
        match = _EXACT_PIN_PATTERN.match(raw_line.strip())
        if match is None:
            continue
        package_name, version = match.groups()
        pins[package_name.lower().replace("_", "-")] = version
    return pins


def hashed_requirement_records(requirements_text: str) -> dict[str, frozenset[str]]:
    """Parse each exact requirement record and its complete SHA-256 hash set."""
    records: dict[str, frozenset[str]] = {}
    current_pin: str | None = None
    current_hashes: set[str] = set()

    def finish_record() -> None:
        """Persist one complete requirement record before starting the next."""
        nonlocal current_pin, current_hashes
        if current_pin is None:
            return
        assert current_hashes, f"hash-locked requirement has no hashes: {current_pin}"
        records[current_pin] = frozenset(current_hashes)
        current_pin = None
        current_hashes = set()

    for raw_line in requirements_text.splitlines():
        stripped = raw_line.strip()
        pin_match = _EXACT_PIN_PATTERN.match(stripped)
        if pin_match is not None and not raw_line.startswith((" ", "\t")):
            finish_record()
            package_name, version = pin_match.groups()
            current_pin = f"{package_name.lower().replace('_', '-')}=={version}"
            continue
        hash_match = _HASH_PATTERN.search(stripped)
        if hash_match is not None:
            assert current_pin is not None, "orphaned SHA-256 hash in requirements lock"
            current_hashes.add(hash_match.group(1))
    finish_record()
    return records


def importer_resolution(importer_section: dict[str, object], group: str, name: str) -> dict[str, str]:
    """Return one structurally parsed pnpm root-importer dependency resolution."""
    dependencies = importer_section[group]
    assert isinstance(dependencies, dict)
    resolution = dependencies[name]
    assert isinstance(resolution, dict)
    assert isinstance(resolution.get("specifier"), str)
    assert isinstance(resolution.get("version"), str)
    return resolution


def test_container_provenance_dependency_pins_match_reviewed_manifests() -> None:
    """Keep backend, Strix, and frontend dependency floors reviewable together."""
    backend_pins = exact_requirement_pins(read_repo_text("backend/requirements.txt"))
    backend_records = hashed_requirement_records(
        read_repo_text("backend/requirements-hashes.txt")
    )
    strix_pins = exact_requirement_pins(read_repo_text("requirements-strix-ci.txt"))
    strix_records = hashed_requirement_records(
        read_repo_text("requirements-strix-ci-hashes.txt")
    )
    frontend_package = json.loads(read_repo_text("frontend/package.json"))
    frontend_lock = yaml.safe_load(read_repo_text("frontend/pnpm-lock.yaml"))

    assert backend_pins["cryptography"] == "50.0.0"
    assert backend_pins["protobuf"] == "7.35.1"
    assert "cryptography==50.0.0" in backend_records
    assert "protobuf==7.35.1" in backend_records
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for pin in ("cryptography==50.0.0", "protobuf==7.35.1")
        for digest in backend_records[pin]
    )

    assert strix_pins["cryptography"] == "50.0.0"
    assert strix_pins["protobuf"] == "6.33.6"
    assert "cryptography==50.0.0" in strix_records
    assert "protobuf==6.33.6" in strix_records
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for pin in ("cryptography==50.0.0", "protobuf==6.33.6")
        for digest in strix_records[pin]
    )

    root_importer = frontend_lock["importers"]["."]
    postcss_resolution = importer_resolution(
        root_importer, "devDependencies", "postcss"
    )
    jsdom_resolution = importer_resolution(root_importer, "devDependencies", "jsdom")
    assert postcss_resolution == {"specifier": "8.5.26", "version": "8.5.26"}
    assert jsdom_resolution == {"specifier": "^30.0.1", "version": "30.0.1"}

    assert frontend_package["devDependencies"]["postcss"] == "8.5.26"
    assert frontend_package["devDependencies"]["jsdom"] == "^30.0.1"
    assert frontend_package["overrides"]["postcss"] == "8.5.26"
    assert frontend_package["overrides"]["brace-expansion"] == "5.0.9"
    assert frontend_package["overrides"]["undici"] == "8.9.0"

    assert frontend_lock["overrides"] == {
        **frontend_lock["overrides"],
        "postcss": "8.5.26",
        "brace-expansion": "5.0.9",
        "undici": "8.9.0",
    }
    package_records = frontend_lock["packages"]
    for exact_lock_entry in (
        "postcss@8.5.26",
        "jsdom@30.0.1",
        "brace-expansion@5.0.9",
        "undici@8.9.0",
    ):
        assert exact_lock_entry in package_records
