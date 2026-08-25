from datetime import datetime

from app.domain.enums import ApprovalStatus, ScheduleHorizon
from app.domain.models import ScheduledWork
from app.repositories import scheduling_settings_repository
from app.scheduler.policy import comparable_time, frozen_date_cutoff

FROZEN_HORIZON_DAYS = 3
FIRM_HORIZON_DAYS = 7


def classify_horizon(item: ScheduledWork, anchor: datetime | None = None) -> ScheduleHorizon:
    settings = scheduling_settings_repository.get()
    now = anchor or datetime.now(tz=item.start_time.tzinfo)
    start = comparable_time(item.start_time)
    current = comparable_time(now)
    if start.date() <= frozen_date_cutoff(settings, current):
        return ScheduleHorizon.FROZEN
    if (start - current).total_seconds() / 86400 <= FIRM_HORIZON_DAYS:
        return ScheduleHorizon.FIRM
    return ScheduleHorizon.FLUID


def move_penalty(item: ScheduledWork, anchor: datetime | None = None) -> int:
    horizon = classify_horizon(item, anchor)
    if item.status == ApprovalStatus.LOCKED or horizon == ScheduleHorizon.FROZEN:
        return 100
    if horizon == ScheduleHorizon.FIRM:
        return 40
    return 10
