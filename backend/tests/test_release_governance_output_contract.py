"""Exact-output contract for the repository-root governance subprocess."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROHIBITED_OUTPUT = re.compile(r"timeout|fatal|warn|denied", re.IGNORECASE)


def test_repository_root_governance_subprocess_has_clean_output() -> None:
    """Mirror Application CI's fail-closed log contract for the real root test step."""

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONWARNINGS": "error"},
        capture_output=True,
        text=True,
    )
    output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0, output
    assert "INTERNALERROR" not in output, output
    assert PROHIBITED_OUTPUT.search(output) is None, output
