from datetime import datetime


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def overlap_window(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> tuple[datetime, datetime]:
    return max(a_start, b_start), min(a_end, b_end)
