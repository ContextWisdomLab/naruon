"""Focused contract for the documented OpenCode redirect credential boundary."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_opencode_redirect_documentation_keeps_authorization_fail_closed() -> None:
    """Keep the Fetch cross-origin redirect credential behavior explicit."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Fetch transport removes" in readme
    assert "cross-origin redirect" in readme
