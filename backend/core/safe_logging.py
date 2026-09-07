"""Logging helpers that preserve diagnostic frames without exception messages."""

from __future__ import annotations

import logging
from types import TracebackType

_REDACTED_EXCEPTION_MESSAGE = "Exception details redacted"
_FACTORY_MARKER = "_naruon_secret_safe_log_record_factory"


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


def _redacting_log_record_factory(previous_factory):
    def factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        if record.exc_info is not None:
            _exc_type, exc_value, traceback = record.exc_info
            already_redacted = (
                isinstance(exc_value, RuntimeError)
                and str(exc_value) == _REDACTED_EXCEPTION_MESSAGE
            )
            if exc_value is not None and not already_redacted:
                record.exc_info = (
                    RuntimeError,
                    RuntimeError(_REDACTED_EXCEPTION_MESSAGE),
                    traceback,
                )
        return record

    setattr(factory, _FACTORY_MARKER, True)
    return factory


def install_secret_safe_log_record_factory() -> None:
    """Redact exception values before any configured handler formats a record.

    Naruon has several independent logging entry points, including API handlers,
    background workers, and CLI importers. Installing the policy at the ``core``
    package boundary keeps raw ``exc_info=True`` records from bypassing redaction
    when a call site does not own a dedicated formatter or filter.
    """
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, _FACTORY_MARKER, False):
        return
    logging.setLogRecordFactory(_redacting_log_record_factory(current_factory))
