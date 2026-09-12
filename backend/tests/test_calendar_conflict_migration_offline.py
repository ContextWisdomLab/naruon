"""Offline-mode contract tests for calendar conflict Alembic revisions."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_MIGRATIONS = (
    "0018_calendar_conflict_judgments.py",
    "0021_calendar_correction_rationale.py",
)


def _load_migration(filename: str):
    """Load one revision module without requiring a Python-safe filename."""
    module_path = _VERSIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(
        f"offline_contract_{module_path.stem}", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("filename", _MIGRATIONS)
@pytest.mark.parametrize("direction", ("upgrade", "downgrade"))
def test_calendar_conflict_migrations_do_not_introspect_in_offline_mode(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    direction: str,
) -> None:
    """Offline SQL generation must never require a live database connection."""
    migration = _load_migration(filename)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: True),
        raising=False,
    )
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: pytest.fail("offline migration requested a live Alembic bind"),
    )
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda *_args, **_kwargs: pytest.fail(
            "offline migration attempted live schema introspection"
        ),
    )
    for operation_name in (
        "alter_column",
        "create_index",
        "create_table",
        "drop_index",
        "drop_table",
    ):
        monkeypatch.setattr(
            migration.op,
            operation_name,
            lambda *_args, **_kwargs: None,
        )

    getattr(migration, direction)()
