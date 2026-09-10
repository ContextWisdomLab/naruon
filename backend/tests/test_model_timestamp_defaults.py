"""Timezone-aware datetime default guard for ORM columns (naruon#1041).

Mapped datetime defaults and on-update callables must return timezone-aware
values. SQLAlchemy normalizes callable column defaults to accept an execution
context, so this guard evaluates the actual mapped callable and deliberately
lets evaluation errors fail the test instead of treating them as non-datetime
values.
"""

import datetime

from db.models import Base


def _datetime_default_callables():
    for mapper in Base.registry.mappers:
        for column in mapper.columns:
            for kind in ("default", "onupdate"):
                column_default = getattr(column, kind, None)
                if column_default is None:
                    continue
                default_callable = getattr(column_default, "arg", None)
                if callable(default_callable):
                    yield mapper.local_table.name, column.name, kind, default_callable


def _evaluate_mapped_default(default_callable):
    """Evaluate a SQLAlchemy-mapped callable without swallowing its errors."""

    return default_callable(None)


def test_datetime_column_defaults_are_timezone_aware():
    naive_defaults: list[str] = []
    for table, column, kind, default_callable in _datetime_default_callables():
        value = _evaluate_mapped_default(default_callable)
        if isinstance(value, datetime.datetime) and value.tzinfo is None:
            naive_defaults.append(f"{table}.{column} ({kind})")

    assert not naive_defaults, (
        "naive datetime defaults are deprecated (datetime.utcnow) and fatal "
        "under PYTHONWARNINGS=error; use "
        "lambda: datetime.datetime.now(datetime.timezone.utc): "
        + ", ".join(sorted(naive_defaults))
    )


def test_datetime_default_guard_does_not_swallow_callable_failures():
    def broken_default(_context):
        raise TypeError("default evaluation failed")

    try:
        _evaluate_mapped_default(broken_default)
    except TypeError as exc:
        assert str(exc) == "default evaluation failed"
    else:
        raise AssertionError("default evaluation failures must fail closed")
