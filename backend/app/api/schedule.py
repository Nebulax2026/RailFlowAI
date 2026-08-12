from fastapi import APIRouter, HTTPException

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest
from app.domain.models import ScheduleAlternative, ScheduledWork
from app.scheduler.alternative_generator import generate_alternatives
from app.scheduler.cp_sat_scheduler import optimise_schedule
from app.storage import REQUESTS, SCHEDULED_WORK
from app.validation.schedule_validator import validate_scheduled_work

router = APIRouter()


def _requests_with_locked_schedule() -> list[MaintenanceRequest]:
    prepared: list[MaintenanceRequest] = []
    for request in REQUESTS.values():
        scheduled = SCHEDULED_WORK.get(request.request_id)
        if scheduled and scheduled.status == ApprovalStatus.LOCKED:
            prepared.append(
                request.model_copy(
                    update={
                        "approval_status": ApprovalStatus.LOCKED,
                        "locked": True,
                        "fixed_start": scheduled.start_time,
                        "fixed_end": scheduled.end_time,
                    }
                )
            )
        else:
            prepared.append(request.model_copy(update={"locked": False, "fixed_start": None, "fixed_end": None}))
    return prepared


@router.get("", response_model=list[ScheduledWork])
def active_schedule() -> list[ScheduledWork]:
    return list(SCHEDULED_WORK.values())


@router.post("/optimise", response_model=list[ScheduledWork])
def optimise(option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION) -> list[ScheduledWork]:
    requests = _requests_with_locked_schedule()
    scheduled = optimise_schedule(requests, option)
    errors = validate_scheduled_work(scheduled, requests)
    if len(scheduled) != len(requests) or errors:
        raise HTTPException(status_code=422, detail=errors or ["No feasible schedule found for all requests."])
    SCHEDULED_WORK.clear()
    for item in scheduled:
        SCHEDULED_WORK[item.request_id] = item
    return scheduled


@router.post("/alternatives", response_model=list[ScheduleAlternative])
def alternatives() -> list[ScheduleAlternative]:
    return generate_alternatives(_requests_with_locked_schedule())


@router.post("/approve")
def approve_schedule(role: str = "requester") -> dict:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can approve schedules.")
    requests = _requests_with_locked_schedule()
    schedule = list(SCHEDULED_WORK.values())
    errors = validate_scheduled_work(schedule, requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    conflicts = detect_conflicts(schedule, requests)
    if conflicts:
        return {"approved": False, "unresolved_conflicts": len(conflicts)}
    for item in schedule:
        locked_item = item.model_copy(update={"status": ApprovalStatus.LOCKED})
        SCHEDULED_WORK[item.request_id] = locked_item
        request = REQUESTS.get(item.request_id)
        if request:
            REQUESTS[item.request_id] = request.model_copy(
                update={
                    "approval_status": ApprovalStatus.LOCKED,
                    "locked": True,
                    "fixed_start": item.start_time,
                    "fixed_end": item.end_time,
                }
            )
    return {"approved": True, "unresolved_conflicts": 0, "locked_items": len(schedule)}
