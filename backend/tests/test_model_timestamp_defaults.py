"""Timezone-aware datetime default guard for ORM columns (naruon#1041).

Python 3.12+ deprecates ``datetime.datetime.utcnow``: it returns a naive
timestamp whose ``DeprecationWarning`` is fatal under the CI app test
suite's ``PYTHONWARNINGS=error``. Every column default / onupdate that
produces a ``datetime`` must therefore be timezone-aware.

This guard fails when any mapped column default yields a naive datetime,
so a future model cannot silently reintroduce the deprecation.
"""

import datetime

import pytest
from sqlalchemy import Column, DateTime

from db.models import Base


def _datetime_default_callables():
    for mapper in Base.registry.mappers:
        for column in mapper.columns:
            if not isinstance(column.type, DateTime):
                continue
            for kind in ("default", "onupdate"):
                column_default = getattr(column, kind, None)
                if column_default is None:
                    continue
                arg = getattr(column_default, "arg", None)
                if callable(arg):
                    yield mapper.local_table.name, column.name, kind, arg


def _call_with_context(default_callable):
    """Evaluate a column default the way SQLAlchemy does.

    SQLAlchemy wraps context-less callables so they accept an execution
    context, so try the context form first and fall back to the plain
    call form.
    """
    try:
        return default_callable(None)
    except TypeError:
        pass
    try:
        return default_callable()
    except TypeError:
        return None


def _datetime_default_issue(table, column, kind, default_callable):
    value = _call_with_context(default_callable)
    if not isinstance(value, datetime.datetime):
        return f"{table}.{column} ({kind}) returned {type(value).__name__}"
    if value.tzinfo is None:
        return f"{table}.{column} ({kind}) is naive"
    return None


def test_datetime_column_defaults_are_timezone_aware():
    invalid_defaults: list[str] = []
    for table, column, kind, default_callable in _datetime_default_callables():
        issue = _datetime_default_issue(table, column, kind, default_callable)
        if issue:
            invalid_defaults.append(issue)

    assert not invalid_defaults, (
        "datetime defaults must return timezone-aware datetime values; "
        "under PYTHONWARNINGS=error; use "
        "lambda: datetime.datetime.now(datetime.timezone.utc): "
        + ", ".join(sorted(invalid_defaults))
    )


@pytest.mark.parametrize("invalid_value", ["not-a-date", 123, None])
def test_datetime_default_guard_rejects_non_datetime_callable_results(invalid_value):
    column = Column(
        "event_time",
        DateTime(timezone=True),
        default=lambda: invalid_value,
    )

    issue = _datetime_default_issue(
        "synthetic_events",
        column.name,
        "default",
        column.default.arg,
    )

    assert issue == (
        f"synthetic_events.event_time (default) returned "
        f"{type(invalid_value).__name__}"
    )
