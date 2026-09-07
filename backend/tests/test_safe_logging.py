"""Regression tests for secret-safe exception logging."""

import logging

from core.safe_logging import redacted_exception_info


def _raise_secret_bearing_exception(message: str) -> None:
    raise RuntimeError(message)


def test_redacted_exception_info_keeps_traceback_without_exception_message() -> None:
    """Preserve diagnostic frames while replacing secret-bearing exception text."""
    secret = "super" + "-secret-value"
    message = f"provider token={secret}"
    try:
        _raise_secret_bearing_exception(message)
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

    assert secret not in rendered
    assert "token=" not in rendered
    assert "Exception details redacted" in rendered
    assert "_raise_secret_bearing_exception" in rendered
