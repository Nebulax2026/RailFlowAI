from datetime import datetime

from app.domain.enums import ApprovalStatus, ScheduleHorizon
from app.domain.models import ScheduledWork

FROZEN_HORIZON_HOURS = 24
FIRM_HORIZON_HOURS = 7 * 24


def classify_horizon(item: ScheduledWork, anchor: datetime | None = None) -> ScheduleHorizon:
    now = anchor or datetime.now(tz=item.start_time.tzinfo)
    hours_until_start = (item.start_time - now).total_seconds() / 3600
    if hours_until_start <= FROZEN_HORIZON_HOURS:
        return ScheduleHorizon.FROZEN
    if hours_until_start <= FIRM_HORIZON_HOURS:
        return ScheduleHorizon.FIRM
    return ScheduleHorizon.FLUID


def move_penalty(item: ScheduledWork, anchor: datetime | None = None) -> int:
    horizon = classify_horizon(item, anchor)
    if item.status == ApprovalStatus.LOCKED or horizon == ScheduleHorizon.FROZEN:
        return 100
    if horizon == ScheduleHorizon.FIRM:
        return 40
    return 10
