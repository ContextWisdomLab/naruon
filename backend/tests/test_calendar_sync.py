import datetime

import pytest
from icalendar import Calendar

from services.calendar_sync import CalendarTask, generate_ics_from_task


def test_generate_ics_from_task():
    task_uid = "abc-123"
    title = "Review Q2 Marketing Report"
    status = "in_progress"
    created_at = datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc)
    updated_at = datetime.datetime(2026, 5, 23, 11, 0, tzinfo=datetime.timezone.utc)
    due_date = datetime.datetime(2026, 5, 25, 15, 0, tzinfo=datetime.timezone.utc)

    task = CalendarTask(
        task_uid=task_uid,
        title=title,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        due_date=due_date,
    )

    ics_content = generate_ics_from_task(task)

    assert "BEGIN:VCALENDAR" in ics_content
    assert "VERSION:2.0" in ics_content
    assert "PRODID:-//Naruon//AI Workspace//EN" in ics_content
    assert "BEGIN:VTODO" in ics_content
    assert "UID:abc-123" in ics_content
    assert "SUMMARY:Review Q2 Marketing Report" in ics_content
    assert "STATUS:IN-PROCESS" in ics_content
    assert "DUE:20260525T150000Z" in ics_content
    parsed = Calendar.from_ical(ics_content)
    vtodo = next(component for component in parsed.walk() if component.name == "VTODO")
    assert vtodo.decoded("CREATED") == created_at
    assert "END:VTODO" in ics_content


def test_generate_ics_from_task_serializes_created_and_dtstamp_in_utc():
    task = CalendarTask(
        task_uid="utc-1",
        title="UTC timestamps",
        status="in_progress",
        created_at=datetime.datetime(
            2026,
            5,
            23,
            10,
            0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=9)),
        ),
        updated_at=datetime.datetime(
            2026,
            5,
            23,
            11,
            0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=-5)),
        ),
    )

    ics_content = generate_ics_from_task(task)

    assert "CREATED:20260523T010000Z" in ics_content
    assert "DTSTAMP:20260523T160000Z" in ics_content


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_generate_ics_from_task_rejects_naive_change_management_time(
    field_name: str,
):
    aware = datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc)
    task_values = {
        "task_uid": "naive-1",
        "title": "Naive timestamp",
        "status": "in_progress",
        "created_at": aware,
        "updated_at": aware,
    }
    task_values[field_name] = datetime.datetime(2026, 5, 23, 10, 0)

    with pytest.raises(ValueError, match=f"{field_name} must be timezone-aware"):
        generate_ics_from_task(CalendarTask(**task_values))


def test_generate_ics_from_task_escapes_summary_text():
    task = CalendarTask(
        task_uid="escape-1",
        title="Review, Q2; follow\\up\nnotes",
        status="in_progress",
        created_at=datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2026, 5, 23, 11, 0, tzinfo=datetime.timezone.utc),
    )

    ics_content = generate_ics_from_task(task)

    assert "SUMMARY:Review\\, Q2\\; follow\\\\up\\nnotes" in ics_content


def test_generate_ics_from_task_status_done():
    task = CalendarTask(
        task_uid="done-1",
        title="Done Task",
        status="done",
        created_at=datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2026, 5, 23, 11, 0, tzinfo=datetime.timezone.utc),
    )
    ics_content = generate_ics_from_task(task)
    assert "STATUS:COMPLETED" in ics_content


def test_generate_ics_from_task_status_blocked():
    task = CalendarTask(
        task_uid="blocked-1",
        title="Blocked Task",
        status="blocked",
        created_at=datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2026, 5, 23, 11, 0, tzinfo=datetime.timezone.utc),
    )
    ics_content = generate_ics_from_task(task)
    assert "STATUS:NEEDS-ACTION" in ics_content


def test_generate_ics_from_task_status_unknown():
    task = CalendarTask(
        task_uid="unknown-1",
        title="Unknown Status Task",
        status="some_weird_status",
        created_at=datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2026, 5, 23, 11, 0, tzinfo=datetime.timezone.utc),
    )
    ics_content = generate_ics_from_task(task)
    # Default is NEEDS-ACTION
    assert "STATUS:NEEDS-ACTION" in ics_content


def test_generate_ics_from_task_no_due_date():
    task = CalendarTask(
        task_uid="no-due-1",
        title="No Due Date Task",
        status="in_progress",
        created_at=datetime.datetime(2026, 5, 23, 10, 0, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2026, 5, 23, 11, 0, tzinfo=datetime.timezone.utc),
        due_date=None,
    )
    ics_content = generate_ics_from_task(task)
    assert "DUE:" not in ics_content
