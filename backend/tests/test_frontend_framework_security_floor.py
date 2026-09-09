"""Fail closed when frontend framework/image dependencies regress below patched floors."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"


def _exact_version(value: str) -> tuple[int, int, int]:
    """Return a three-part exact version, rejecting ranges and prereleases."""

    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    assert match is not None, f"expected exact semantic version, got {value!r}"
    return tuple(int(part) for part in match.groups())


def _assert_weak_lock_text_contract(
    lock_text: str, next_value: str, sharp_value: str
) -> None:
    """Preserve the predecessor lock checks while stronger regressions are RED."""

    assert f"next@{next_value}" in lock_text, (
        "lockfile must resolve the reviewed Next.js release"
    )
    assert f"sharp@{sharp_value}" in lock_text, (
        "lockfile must resolve the reviewed sharp release"
    )
    assert "next@16.3.1" not in lock_text, (
        "vulnerable Next.js 16.3.1 must not remain locked"
    )
    assert "sharp@0.35.0" not in lock_text, (
        "vulnerable sharp 0.35.0 must not remain locked"
    )


def test_frontend_framework_and_image_security_floors() -> None:
    """Keep Next.js and sharp at releases containing the reviewed security fixes."""

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    next_value = package["dependencies"]["next"]
    eslint_next_value = package["devDependencies"]["eslint-config-next"]

    assert _exact_version(next_value) >= (16, 3, 3), (
        "Next.js must include the fixes for CVE-2026-75604 and "
        "GHSA-2xp9-vwfh-vxw4"
    )
    assert eslint_next_value == next_value, (
        "eslint-config-next must stay on the same reviewed release as Next.js"
    )

    workspace = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    )
    sharp_value = str(workspace["overrides"]["sharp"])
    assert _exact_version(sharp_value) >= (0, 35, 4), (
        "sharp must include the fix for GHSA-rgj7-g3m4-5g8c"
    )

    lock_text = (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    _assert_weak_lock_text_contract(lock_text, next_value, sharp_value)


def test_security_floor_rejects_importer_drift() -> None:
    """Reject a partially regenerated lock whose root importer drifts below the floor."""

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    next_value = package["dependencies"]["next"]
    workspace = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    )
    sharp_value = str(workspace["overrides"]["sharp"])
    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )
    lock["importers"]["."]["dependencies"]["next"]["specifier"] = "16.3.2"

    with pytest.raises(AssertionError):
        _assert_weak_lock_text_contract(
            yaml.safe_dump(lock, sort_keys=False), next_value, sharp_value
        )


def test_security_floor_rejects_any_below_floor_lock_entry() -> None:
    """Reject stale vulnerable package/snapshot entries, not only two known literals."""

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    next_value = package["dependencies"]["next"]
    workspace = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    )
    sharp_value = str(workspace["overrides"]["sharp"])
    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )
    lock["packages"]["next@16.3.2"] = {}
    lock["snapshots"]["sharp@0.35.3"] = {}

    with pytest.raises(AssertionError):
        _assert_weak_lock_text_contract(
            yaml.safe_dump(lock, sort_keys=False), next_value, sharp_value
        )
