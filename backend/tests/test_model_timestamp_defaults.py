"""Timezone-aware datetime default guard for ORM columns.

Mapped datetime defaults and on-update callables must return timezone-aware
values. SQLAlchemy normalizes callable column defaults to accept an execution
context, so this guard evaluates the actual mapped callable and deliberately
lets evaluation errors fail the test instead of treating them as non-datetime
values.
"""

import datetime

from sqlalchemy import DateTime

from db.models import Base


class _NullOffsetTimezone(datetime.tzinfo):
    """tzinfo stub that is still naive under Python's datetime contract."""

    def utcoffset(self, _value):
        return None

    def dst(self, _value):
        return None

    def tzname(self, _value):
        return "null-offset"


def _datetime_default_callables():
    for mapper in Base.registry.mappers:
        for column in mapper.columns:
            if not isinstance(column.type, DateTime):
                continue
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


def _is_datetime_timezone_aware(value: datetime.datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def _invalid_datetime_default_entries(entries):
    """Return mapped DateTime defaults that violate the timestamp contract."""

    invalid_defaults: list[str] = []
    for table, column, kind, default_callable in entries:
        value = _evaluate_mapped_default(default_callable)
        invalid_value = not isinstance(value, datetime.datetime)
        if invalid_value or not _is_datetime_timezone_aware(value):
            invalid_defaults.append(f"{table}.{column} ({kind})")
    return invalid_defaults


def test_datetime_column_defaults_are_timezone_aware():
    invalid_defaults = _invalid_datetime_default_entries(_datetime_default_callables())

    assert not invalid_defaults, (
        "DateTime defaults/onupdates must return timezone-aware datetime values; "
        "use lambda: datetime.datetime.now(datetime.timezone.utc): "
        + ", ".join(sorted(invalid_defaults))
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


def test_datetime_default_guard_excludes_non_datetime_callable_defaults():
    guarded_columns = {
        (table, column, kind)
        for table, column, kind, _default_callable in _datetime_default_callables()
    }

    assert ("security_audit_events", "event_uid", "default") not in guarded_columns


def test_datetime_default_guard_rejects_non_datetime_results():
    for invalid_value in ("2026-09-11T00:00:00+00:00", 1757548800, None):
        def invalid_default(_context, value=invalid_value):
            return value

        invalid_defaults = _invalid_datetime_default_entries(
            [("example_table", "updated_at", "default", invalid_default)]
        )

        assert invalid_defaults == ["example_table.updated_at (default)"]


def test_timezone_awareness_rejects_tzinfo_with_null_offset():
    value = datetime.datetime(2026, 9, 11, tzinfo=_NullOffsetTimezone())

    assert not _is_datetime_timezone_aware(value)
