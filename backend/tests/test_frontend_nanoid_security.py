"""Fail closed when the frontend lock resolves the vulnerable Nano ID release."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_LOCK = REPO_ROOT / "frontend" / "pnpm-lock.yaml"
PATCHED_NANOID_VERSION = "3.3.18"


def test_frontend_lock_resolves_only_patched_nanoid_3x() -> None:
    """Require PostCSS's Nano ID dependency to resolve to the reviewed patched 3.x release."""
    lock = yaml.safe_load(FRONTEND_LOCK.read_text(encoding="utf-8"))

    for section_name in ("packages", "snapshots"):
        section = lock[section_name]
        nanoid_3x = sorted(
            package_key
            for package_key in section
            if package_key.startswith("nanoid@3.")
        )
        assert nanoid_3x == [f"nanoid@{PATCHED_NANOID_VERSION}"]

    postcss_snapshot = lock["snapshots"]["postcss@8.5.26"]
    assert postcss_snapshot["dependencies"]["nanoid"] == PATCHED_NANOID_VERSION
