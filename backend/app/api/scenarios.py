from fastapi import APIRouter

from app.domain.models import MaintenanceRequest, ScheduledWork
from app.scheduler.emergency_rescheduler import reschedule_with_emergency
from app.storage import REQUESTS, SCHEDULED_WORK

router = APIRouter()


@router.post("/emergency", response_model=list[ScheduledWork])
def add_emergency_request(payload: MaintenanceRequest) -> list[ScheduledWork]:
    scheduled = reschedule_with_emergency(list(REQUESTS.values()), payload)
    REQUESTS[payload.request_id] = payload
    SCHEDULED_WORK.clear()
    for item in scheduled:
        SCHEDULED_WORK[item.request_id] = item
    return scheduled
