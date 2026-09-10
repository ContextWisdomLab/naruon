from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

ENV_FILE_PATHS = ("~/.env", "../.env", ".env")


def operator_home() -> Path:
    """Return the operator home directory, preferring explicit HOME overrides."""
    home = Path.home()
    if not home.is_absolute() or home.is_symlink():
        raise ValueError("operator home must be an absolute non-symlink path")
    resolved = home.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("operator home must be a directory")
    return resolved


def expand_operator_path(path: str | os.PathLike[str]) -> Path:
    """Expand leading ``~`` against the operator home directory."""
    path_text = os.fspath(path)
    home = operator_home()
    if path_text == "~":
        return home
    if path_text.startswith("~/") or path_text.startswith("~\\"):
        candidate = (home / path_text[2:]).resolve(strict=False)
        if not candidate.is_relative_to(home):
            raise ValueError("operator path escapes the operator home")
        return candidate
    return Path(path_text).expanduser()


def operator_env_file_paths(paths: Iterable[str] = ENV_FILE_PATHS) -> tuple[str, ...]:
    """Resolve the explicit bootstrap transport, or the existing local defaults."""
    selected_source = os.environ.get("NARUON_ENV_FILE")
    if selected_source:
        return (str(expand_operator_path(selected_source)),)
    return tuple(str(expand_operator_path(path)) for path in paths)
