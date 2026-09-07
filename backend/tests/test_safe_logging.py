"""Regression tests for secret-safe exception logging."""

import logging
from core.safe_logging import redacted_exception_info

_t = "token="
_v = "super-secret-value"

def _raise_secret_bearing_exception() -> None:
    # Build it dynamically to avoid literal string matching the source code
    raise RuntimeError("provider " + _t + _v)


def test_redacted_exception_info_keeps_traceback_without_exception_message() -> None:
    """Preserve diagnostic frames while replacing secret-bearing exception text."""
    try:
        _raise_secret_bearing_exception()
    except RuntimeError as exc:
        exc_info = redacted_exception_info(exc)

    record = logging.LogRecord(
        name="naruon.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Provider operation failed",
        args=(),
        exc_info=exc_info,
    )
    rendered = logging.Formatter("%(message)s").format(record)

    assert "super-secret-value" not in rendered
    assert "token=" not in rendered
    assert "Exception details redacted" in rendered
    assert "_raise_secret_bearing_exception" in rendered
