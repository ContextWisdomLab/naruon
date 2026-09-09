"""Contract for consuming OpenCode review configuration from the central owner."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_required_review_has_no_repository_local_opencode_configuration() -> None:
    """Repository-local OpenCode JSON must not fork the central review policy."""

    for relative_path in ("opencode.json", "opencode.jsonc"):
        assert not (REPO_ROOT / relative_path).exists(), (
            "central OpenCode configuration must remain owner-controlled: "
            f"{relative_path}"
        )
