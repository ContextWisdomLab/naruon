import datetime
from dataclasses import dataclass
from typing import Optional

from icalendar import Calendar, Todo


@dataclass
class CalendarTask:
    task_uid: str
    title: str
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    due_date: Optional[datetime.datetime] = None


def _calendar_change_timestamp_utc(
    value: datetime.datetime,
    *,
    field_name: str,
) -> datetime.datetime:
    """Return an RFC 5545 change-management timestamp normalized to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(datetime.timezone.utc)


def generate_ics_from_task(task: CalendarTask) -> str:
    """
    Generates a basic CalDAV-compatible .ics (iCalendar) string for a TicketTask (VTODO).
    """
    ics_status = "NEEDS-ACTION"
    if task.status == "in_progress":
        ics_status = "IN-PROCESS"
    elif task.status == "done":
        ics_status = "COMPLETED"
    elif task.status == "blocked":
        ics_status = "NEEDS-ACTION"

    created_at = _calendar_change_timestamp_utc(
        task.created_at,
        field_name="created_at",
    )
    updated_at = _calendar_change_timestamp_utc(
        task.updated_at,
        field_name="updated_at",
    )

    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", "-//Naruon//AI Workspace//EN")

    action_item = Todo()
    action_item.add("UID", task.task_uid)
    action_item.add("CREATED", created_at)
    action_item.add("DTSTAMP", updated_at)
    action_item.add("SUMMARY", task.title)
    action_item.add("STATUS", ics_status)

    if task.due_date:
        action_item.add("DUE", task.due_date)

    cal.add_component(action_item)

    return cal.to_ical().decode("utf-8")
