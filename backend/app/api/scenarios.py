from fastapi import APIRouter

from app.domain.models import MaintenanceRequest, ScheduledWork
from app.repositories import requests_repository, schedule_repository, unit_of_work
from app.scheduler.emergency_rescheduler import reschedule_with_emergency

router = APIRouter()


@router.post("/emergency", response_model=list[ScheduledWork])
def add_emergency_request(payload: MaintenanceRequest) -> list[ScheduledWork]:
    scheduled = reschedule_with_emergency(requests_repository.list(), payload)
    with unit_of_work() as work:
        work.requests.save(payload)
        work.schedule.replace_all(scheduled)
    return scheduled
