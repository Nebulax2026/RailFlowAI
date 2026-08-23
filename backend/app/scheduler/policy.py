from datetime import datetime, timedelta, timezone

from app.domain.enums import BlockStatus
from app.domain.models import BlockedTimeSlot, MaintenanceRequest, ScheduledWork, SchedulingSettings


def planning_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def comparable_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def is_urgent(request: MaintenanceRequest, settings: SchedulingSettings, now: datetime | None = None) -> bool:
    anchor = comparable_time(now or planning_now())
    return comparable_time(request.deadline) <= anchor + timedelta(days=settings.urgent_lead_days)


def is_planning_eligible(request: MaintenanceRequest, settings: SchedulingSettings, now: datetime | None = None) -> bool:
    anchor = comparable_time(now or planning_now())
    return comparable_time(request.earliest_start).date() <= (anchor + timedelta(days=settings.urgent_lead_days)).date()


def overlaps(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return comparable_time(left_start) < comparable_time(right_end) and comparable_time(right_start) < comparable_time(left_end)


def block_overlaps_work(block: BlockedTimeSlot, item: ScheduledWork) -> bool:
    return (
        block.status == BlockStatus.ACTIVE
        and item.track_sector in block.track_sectors
        and overlaps(block.start_time, block.end_time, item.start_time, item.end_time)
    )


def work_overlaps_any_block(item: ScheduledWork, blocks: list[BlockedTimeSlot]) -> bool:
    return any(block_overlaps_work(block, item) for block in blocks)
