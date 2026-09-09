"""Fail closed when frontend framework/image dependencies regress below patched floors."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"
NEXT_SECURITY_FLOOR = (16, 3, 3)
SHARP_SECURITY_FLOOR = (0, 35, 4)
JS_YAML_SECURITY_FLOOR = (4, 3, 2)
VITEST_SECURITY_FLOOR = (4, 1, 11)


def _exact_version(value: str) -> tuple[int, int, int]:
    """Return a three-part exact version, rejecting ranges and prereleases."""

    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    assert match is not None, f"expected exact semantic version, got {value!r}"
    return tuple(int(part) for part in match.groups())


def _resolved_version(value: str) -> tuple[int, int, int]:
    """Return the exact version prefix from a pnpm peer-qualified resolution."""

    version = value.split("(", 1)[0]
    return _exact_version(version)


def _package_key_version(package_key: str, package_name: str) -> tuple[int, int, int]:
    """Return the version encoded by one pnpm package/snapshot key."""

    prefix = f"{package_name}@"
    assert package_key.startswith(prefix), (
        f"expected {package_name!r} lock key, got {package_key!r}"
    )
    return _resolved_version(package_key[len(prefix) :])


def _assert_lock_contract(
    lock: dict[str, Any],
    next_value: str,
    eslint_next_value: str,
    sharp_value: str,
) -> None:
    """Validate root resolution identity and every locked Next.js/sharp security floor."""

    importer = lock["importers"]["."]
    next_import = importer["dependencies"]["next"]
    assert next_import["specifier"] == next_value, (
        "root importer must preserve the package.json Next.js specifier"
    )
    assert _resolved_version(str(next_import["version"])) == _exact_version(next_value), (
        "root importer must resolve the reviewed Next.js release"
    )
    assert f"next@{next_import['version']}" in lock["snapshots"], (
        "root importer Next.js resolution must reference an existing snapshot"
    )

    eslint_next_import = importer["devDependencies"]["eslint-config-next"]
    assert eslint_next_import["specifier"] == eslint_next_value, (
        "root importer must preserve the eslint-config-next specifier"
    )
    assert _resolved_version(str(eslint_next_import["version"])) == _exact_version(
        eslint_next_value
    ), "root importer must resolve the reviewed eslint-config-next release"
    assert f"eslint-config-next@{eslint_next_import['version']}" in lock["snapshots"], (
        "root importer eslint-config-next resolution must reference an existing snapshot"
    )

    assert str(lock["overrides"]["sharp"]) == sharp_value, (
        "lockfile sharp override must match the reviewed workspace override"
    )

    expected_next = _exact_version(next_value)
    expected_sharp = _exact_version(sharp_value)
    for section_name in ("packages", "snapshots"):
        section = lock[section_name]
        next_keys = [key for key in section if key.startswith("next@")]
        sharp_keys = [key for key in section if key.startswith("sharp@")]

        assert next_keys, f"{section_name} must contain a Next.js resolution"
        assert sharp_keys, f"{section_name} must contain a sharp resolution"
        assert any(
            _package_key_version(key, "next") == expected_next for key in next_keys
        ), f"{section_name} must contain the reviewed Next.js release"
        assert any(
            _package_key_version(key, "sharp") == expected_sharp for key in sharp_keys
        ), f"{section_name} must contain the reviewed sharp release"

        for package_key in next_keys:
            assert _package_key_version(package_key, "next") >= NEXT_SECURITY_FLOOR, (
                f"{section_name} contains Next.js below the reviewed security floor: "
                f"{package_key}"
            )
        for package_key in sharp_keys:
            assert _package_key_version(package_key, "sharp") >= SHARP_SECURITY_FLOOR, (
                f"{section_name} contains sharp below the reviewed security floor: "
                f"{package_key}"
            )


def _frontend_security_inputs() -> tuple[str, str, str, dict[str, Any]]:
    """Load the manifest, workspace override, and generated lock contract."""

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    next_value = package["dependencies"]["next"]
    eslint_next_value = package["devDependencies"]["eslint-config-next"]
    workspace = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    )
    sharp_value = str(workspace["overrides"]["sharp"])
    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )
    return next_value, eslint_next_value, sharp_value, lock


def test_frontend_framework_and_image_security_floors() -> None:
    """Keep manifests and every generated lock resolution at reviewed patched releases."""

    next_value, eslint_next_value, sharp_value, lock = _frontend_security_inputs()

    assert _exact_version(next_value) >= NEXT_SECURITY_FLOOR, (
        "Next.js must include the fixes for CVE-2026-75604 and "
        "GHSA-2xp9-vwfh-vxw4"
    )
    assert eslint_next_value == next_value, (
        "eslint-config-next must stay on the same reviewed release as Next.js"
    )
    assert _exact_version(sharp_value) >= SHARP_SECURITY_FLOOR, (
        "sharp must include the fix for GHSA-rgj7-g3m4-5g8c"
    )
    _assert_lock_contract(lock, next_value, eslint_next_value, sharp_value)


def test_js_yaml_security_floor_covers_every_lock_resolution() -> None:
    """Keep every js-yaml resolution above the reviewed denial-of-service floor."""

    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )
    for section_name in ("packages", "snapshots"):
        js_yaml_keys = [
            key for key in lock[section_name] if key.startswith("js-yaml@")
        ]
        for package_key in js_yaml_keys:
            assert (
                _package_key_version(package_key, "js-yaml")
                >= JS_YAML_SECURITY_FLOOR
            ), f"{section_name} contains js-yaml below the reviewed security floor"


def test_vitest_security_floor_covers_manifest_and_lock() -> None:
    """Keep Vitest and its coverage package above the reviewed traversal floor."""

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )
    for package_name in ("vitest", "@vitest/coverage-v8"):
        declared_value = package["devDependencies"][package_name]
        assert _exact_version(declared_value) >= VITEST_SECURITY_FLOOR
        for section_name in ("packages", "snapshots"):
            for package_key in lock[section_name]:
                if package_key.startswith(f"{package_name}@"):
                    assert (
                        _package_key_version(package_key, package_name)
                        >= VITEST_SECURITY_FLOOR
                    ), f"{section_name} contains {package_name} below the reviewed floor"


@pytest.mark.parametrize("package_name", ["vitest", "@vitest/coverage-v8"])
@pytest.mark.parametrize("section_name", ["packages", "snapshots"])
def test_vitest_security_floor_rejects_missing_lock_resolution(
    monkeypatch: pytest.MonkeyPatch,
    package_name: str,
    section_name: str,
) -> None:
    """Reject a regenerated lock section that drops an expected Vitest resolution."""

    package_text = (FRONTEND_ROOT / "package.json").read_text(encoding="utf-8")
    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )
    lock[section_name] = {
        key: value
        for key, value in lock[section_name].items()
        if not key.startswith(f"{package_name}@")
    }
    lock_text = yaml.safe_dump(lock)
    original_read_text = Path.read_text

    def _read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == FRONTEND_ROOT / "package.json":
            return package_text
        if path == FRONTEND_ROOT / "pnpm-lock.yaml":
            return lock_text
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text)
    with pytest.raises(AssertionError):
        test_vitest_security_floor_covers_manifest_and_lock()


@pytest.mark.parametrize("field", ["specifier", "version"])
def test_security_floor_rejects_root_importer_drift(field: str) -> None:
    """Reject a partially regenerated lock whose root Next.js importer drifts."""

    next_value, eslint_next_value, sharp_value, lock = _frontend_security_inputs()
    lock["importers"]["."]["dependencies"]["next"][field] = "16.3.2"

    with pytest.raises(AssertionError):
        _assert_lock_contract(lock, next_value, eslint_next_value, sharp_value)


@pytest.mark.parametrize(
    ("section_name", "package_key"),
    [("packages", "next@16.3.2"), ("snapshots", "sharp@0.35.3")],
)
def test_security_floor_rejects_every_below_floor_lock_entry(
    section_name: str, package_key: str
) -> None:
    """Reject any stale vulnerable Next.js or sharp package/snapshot entry."""

    next_value, eslint_next_value, sharp_value, lock = _frontend_security_inputs()
    lock[section_name][package_key] = {}

    with pytest.raises(AssertionError):
        _assert_lock_contract(lock, next_value, eslint_next_value, sharp_value)
