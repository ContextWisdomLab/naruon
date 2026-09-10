from pathlib import Path

import pytest

from core.env_paths import expand_operator_path, operator_env_file_paths, operator_home


def test_operator_home_resolves_home_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert operator_home() == home.resolve()
    assert expand_operator_path("~/.env") == home.resolve() / ".env"


def test_operator_home_rejects_symlink(monkeypatch, tmp_path: Path) -> None:
    real_home = tmp_path / "real-home"
    linked_home = tmp_path / "linked-home"
    real_home.mkdir()
    linked_home.symlink_to(real_home, target_is_directory=True)
    monkeypatch.setenv("HOME", str(linked_home))

    with pytest.raises(ValueError, match="non-symlink"):
        operator_home()


def test_expand_operator_path_rejects_home_escape(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(ValueError, match="escapes"):
        expand_operator_path("~/../outside.env")


def test_explicit_bootstrap_source_does_not_include_operator_defaults(monkeypatch):
    """A selected bootstrap transport must replace the implicit file chain."""
    monkeypatch.setenv("NARUON_ENV_FILE", "/dev/null")
    assert operator_env_file_paths() == ("/dev/null",)


def test_bootstrap_defaults_remain_when_no_source_is_selected(monkeypatch):
    """Existing local bootstrap behavior remains available without a selector."""
    monkeypatch.delenv("NARUON_ENV_FILE", raising=False)
    assert operator_env_file_paths() == (
        str(expand_operator_path("~/.env")),
        "../.env",
        ".env",
    )


def test_missing_explicit_bootstrap_file_never_falls_back(monkeypatch, tmp_path):
    """A missing selection cannot silently reload the operator credential chain."""
    selected_source = tmp_path / "missing_source.env"
    monkeypatch.setenv("NARUON_ENV_FILE", str(selected_source))
    assert operator_env_file_paths() == (str(selected_source),)
