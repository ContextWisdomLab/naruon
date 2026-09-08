"""Logging helpers that preserve diagnostic frames without exception messages."""

from __future__ import annotations

from types import TracebackType

_REDACTED_EXCEPTION_MESSAGE = "Exception details redacted"


def redacted_exception_info(
    exc: BaseException,
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    """Return traceback frames paired with a generic exception value.

    Standard ``exc_info=True`` includes ``str(exc)`` in formatted logs. Provider,
    parser, database, and protocol exceptions can embed credentials or other
    secret-derived values there. Reusing only the traceback object keeps the
    failing call path available to operators while replacing the exception type
    and value with a stable, non-sensitive diagnostic marker.
    """
    return RuntimeError, RuntimeError(_REDACTED_EXCEPTION_MESSAGE), exc.__traceback__
