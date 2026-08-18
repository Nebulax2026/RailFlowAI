from fastapi import APIRouter, HTTPException

from app.domain.models import MaintenanceRequest, ScheduledWork
from app.scheduler.cp_sat_scheduler import SchedulingInfeasibleError
from app.scheduler.emergency_rescheduler import reschedule_with_emergency
from app.storage import REQUESTS, SCHEDULED_WORK

router = APIRouter()


@router.post("/emergency", response_model=list[ScheduledWork])
def add_emergency_request(payload: MaintenanceRequest) -> list[ScheduledWork]:
    try:
        scheduled = reschedule_with_emergency(list(REQUESTS.values()), payload)
    except SchedulingInfeasibleError as error:
        raise HTTPException(status_code=422, detail=error.blockers) from error
    REQUESTS[payload.request_id] = payload
    SCHEDULED_WORK.clear()
    for item in scheduled:
        SCHEDULED_WORK[item.request_id] = item
    return scheduled
