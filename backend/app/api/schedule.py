from fastapi import APIRouter

from app.conflict.detector import detect_conflicts
from app.domain.enums import ScheduleOption
from app.domain.models import ScheduleAlternative, ScheduledWork
from app.scheduler.alternative_generator import generate_alternatives
from app.scheduler.cp_sat_scheduler import optimise_schedule
from app.storage import REQUESTS, SCHEDULED_WORK

router = APIRouter()


@router.post("/optimise", response_model=list[ScheduledWork])
def optimise(option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION) -> list[ScheduledWork]:
    scheduled = optimise_schedule(list(REQUESTS.values()), option)
    SCHEDULED_WORK.clear()
    for item in scheduled:
        SCHEDULED_WORK[item.request_id] = item
    return scheduled


@router.post("/alternatives", response_model=list[ScheduleAlternative])
def alternatives() -> list[ScheduleAlternative]:
    return generate_alternatives(list(REQUESTS.values()))


@router.post("/approve")
def approve_schedule() -> dict:
    conflicts = detect_conflicts(list(SCHEDULED_WORK.values()))
    return {"approved": len(conflicts) == 0, "unresolved_conflicts": len(conflicts)}
