"""Fail closed when frontend framework/image dependencies regress below patched floors."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"


def _exact_version(value: str) -> tuple[int, int, int]:
    """Return a three-part exact version, rejecting ranges and prereleases."""

    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    assert match is not None, f"expected exact semantic version, got {value!r}"
    return tuple(int(part) for part in match.groups())


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

    workspace = (FRONTEND_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    sharp_match = re.search(
        r"(?m)^\s{2}sharp:\s*[\"']?(\d+\.\d+\.\d+)[\"']?\s*$",
        workspace,
    )
    assert sharp_match is not None, "pnpm workspace must keep an explicit sharp override"
    sharp_value = sharp_match.group(1)
    assert _exact_version(sharp_value) >= (0, 35, 4), (
        "sharp must include the fix for GHSA-rgj7-g3m4-5g8c"
    )

    lock = (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    assert f"next@{next_value}" in lock, "lockfile must resolve the reviewed Next.js release"
    assert f"sharp@{sharp_value}" in lock, "lockfile must resolve the reviewed sharp release"
    assert "next@16.3.1" not in lock, "vulnerable Next.js 16.3.1 must not remain locked"
    assert "sharp@0.35.0" not in lock, "vulnerable sharp 0.35.0 must not remain locked"
