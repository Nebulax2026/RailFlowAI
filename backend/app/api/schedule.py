from fastapi import APIRouter, HTTPException

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import ScheduleAlternative, ScheduledWork
from app.scheduler.alternative_generator import generate_alternatives
from app.scheduler.service import apply_alternative, apply_schedule, build_optimised_schedule, requests_with_locked_schedule
from app.storage import REQUESTS, SCHEDULED_WORK
from app.validation.schedule_validator import validate_scheduled_work

router = APIRouter()


@router.get("", response_model=list[ScheduledWork])
def active_schedule() -> list[ScheduledWork]:
    return list(SCHEDULED_WORK.values())


@router.post("/optimise", response_model=list[ScheduledWork])
def optimise(option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION) -> list[ScheduledWork]:
    scheduled, errors, conflicts = build_optimised_schedule(option)
    if errors or conflicts:
        conflict_errors = [conflict.explanation for conflict in conflicts]
        raise HTTPException(status_code=422, detail=errors or conflict_errors)
    apply_schedule(scheduled)
    return scheduled


@router.post("/apply", response_model=list[ScheduledWork])
def apply_schedule_option(option: ScheduleOption, role: str = "requester") -> list[ScheduledWork]:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can apply schedule alternatives.")
    scheduled, errors, conflicts = apply_alternative(option)
    if errors:
        raise HTTPException(status_code=422, detail=errors or ["No feasible schedule found for all requests."])
    if conflicts:
        raise HTTPException(status_code=422, detail=[conflict.explanation for conflict in conflicts])
    return scheduled


@router.post("/alternatives", response_model=list[ScheduleAlternative])
def alternatives() -> list[ScheduleAlternative]:
    return generate_alternatives(requests_with_locked_schedule())


@router.post("/approve")
def approve_schedule(role: str = "requester") -> dict:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can approve schedules.")
    requests = requests_with_locked_schedule()
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


@router.post("/reject/{request_id}")
def reject_request(request_id: str, role: str = "requester") -> dict:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can reject requests.")
    request = REQUESTS.get(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found.")
    REQUESTS[request_id] = request.model_copy(update={"approval_status": ApprovalStatus.CONFLICT, "locked": False})
    SCHEDULED_WORK.pop(request_id, None)
    return {"rejected": True, "request_id": request_id}


@router.post("/lock/{request_id}", response_model=ScheduledWork)
def lock_request(request_id: str, role: str = "requester") -> ScheduledWork:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can lock scheduled work.")
    scheduled = SCHEDULED_WORK.get(request_id)
    request = REQUESTS.get(request_id)
    if not scheduled or not request:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    locked = scheduled.model_copy(update={"status": ApprovalStatus.LOCKED})
    SCHEDULED_WORK[request_id] = locked
    REQUESTS[request_id] = request.model_copy(
        update={
            "approval_status": ApprovalStatus.LOCKED,
            "locked": True,
            "fixed_start": locked.start_time,
            "fixed_end": locked.end_time,
        }
    )
    return locked


@router.post("/unlock/{request_id}", response_model=ScheduledWork)
def unlock_request(request_id: str, role: str = "requester") -> ScheduledWork:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can unlock scheduled work.")
    scheduled = SCHEDULED_WORK.get(request_id)
    request = REQUESTS.get(request_id)
    if not scheduled or not request:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    unlocked = scheduled.model_copy(update={"status": ApprovalStatus.SCHEDULED})
    SCHEDULED_WORK[request_id] = unlocked
    REQUESTS[request_id] = request.model_copy(
        update={"approval_status": ApprovalStatus.SCHEDULED, "locked": False, "fixed_start": None, "fixed_end": None}
    )
    return unlocked


@router.patch("/modify/{request_id}", response_model=ScheduledWork)
def modify_scheduled_work(request_id: str, payload: dict, role: str = "requester") -> ScheduledWork:
    if role != "schedule_manager":
        raise HTTPException(status_code=403, detail="Only Schedule Managers can modify scheduled work.")
    scheduled = SCHEDULED_WORK.get(request_id)
    if not scheduled:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    updated = scheduled.model_copy(update=payload)
    proposed = [updated if item.request_id == request_id else item for item in SCHEDULED_WORK.values()]
    requests = requests_with_locked_schedule()
    errors = validate_scheduled_work(proposed, requests)
    conflicts = detect_conflicts(proposed, requests)
    if errors or conflicts:
        raise HTTPException(status_code=422, detail=errors or [conflict.explanation for conflict in conflicts])
    SCHEDULED_WORK[request_id] = updated
    return updated
