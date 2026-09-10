"""Timezone-aware datetime default guard for ORM columns (naruon#1041).

Python 3.12+ deprecates ``datetime.datetime.utcnow``: it returns a naive
timestamp whose ``DeprecationWarning`` is fatal under the CI app test
suite's ``PYTHONWARNINGS=error``. Every column default / onupdate that
produces a ``datetime`` must therefore be timezone-aware.

This guard fails when any mapped column default yields a naive datetime,
so a future model cannot silently reintroduce the deprecation.
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


def test_datetime_column_defaults_are_timezone_aware():
    naive_defaults: list[str] = []
    for table, column, kind, default_callable in _datetime_default_callables():
        value = _call_with_context(default_callable)
        if isinstance(value, datetime.datetime) and value.tzinfo is None:
            naive_defaults.append(f"{table}.{column} ({kind})")

    assert not naive_defaults, (
        "naive datetime defaults are deprecated (datetime.utcnow) and fatal "
        "under PYTHONWARNINGS=error; use "
        "lambda: datetime.datetime.now(datetime.timezone.utc): "
        + ", ".join(sorted(naive_defaults))
    )
