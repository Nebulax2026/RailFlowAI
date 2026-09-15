from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


PLANNING_TIME_ZONE = ZoneInfo("Asia/Singapore")
ENGINEERING_START = time(9, 0)
ENGINEERING_END = time(18, 0)


def to_planning_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(PLANNING_TIME_ZONE)


def from_planning_time(value: datetime, original: datetime) -> datetime:
    if original.tzinfo is None:
        return value.replace(tzinfo=None)
    return value.replace(tzinfo=PLANNING_TIME_ZONE).astimezone(original.tzinfo)


def align_to_engineering_window(start_time: datetime, duration_minutes: int, deadline: datetime | None = None) -> datetime:
    local_start = to_planning_time(start_time)
    duration = timedelta(minutes=duration_minutes)

    window_start = datetime.combine(local_start.date(), ENGINEERING_START)
    window_end = datetime.combine(local_start.date(), ENGINEERING_END)
    if local_start.tzinfo is not None:
        window_start = window_start.replace(tzinfo=PLANNING_TIME_ZONE)
        window_end = window_end.replace(tzinfo=PLANNING_TIME_ZONE)

    if local_start < window_start:
        local_start = window_start
    elif local_start >= window_end or local_start + duration > window_end:
        local_start = datetime.combine(local_start.date() + timedelta(days=1), ENGINEERING_START)
        if start_time.tzinfo is not None:
            local_start = local_start.replace(tzinfo=PLANNING_TIME_ZONE)

    aligned = from_planning_time(local_start, start_time)
    if deadline and aligned + duration > deadline:
        return start_time
    return aligned
