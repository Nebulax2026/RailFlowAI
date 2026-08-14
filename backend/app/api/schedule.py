from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.auth import require_schedule_manager
from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import ApproveRequest, ProposalRequest, ScheduleAlternative, ScheduledWork
from app.scheduler.service import apply_alternative, apply_schedule, build_optimised_schedule, generate_reschedule_proposals, requests_with_locked_schedule
from app.storage import REQUESTS, SCHEDULED_WORK
from app.validation.schedule_validator import validate_scheduled_work

router = APIRouter()

SCHEDULE_MODIFY_FIELDS = {
    "start_time",
    "end_time",
    "assigned_crew",
    "assigned_equipment",
    "track_sector",
    "changed_from_original",
    "change_reason",
}


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
def apply_schedule_option(payload: ProposalRequest | None = None, option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION, role: str = "requester") -> list[ScheduledWork]:
    require_schedule_manager(role, "apply schedule alternatives")
    scheduled, errors, conflicts = apply_alternative(option, payload.request_ids if payload else [])
    if errors:
        raise HTTPException(status_code=422, detail=errors or ["No feasible schedule found for all requests."])
    if conflicts:
        raise HTTPException(status_code=422, detail=[conflict.explanation for conflict in conflicts])
    return scheduled


@router.post("/alternatives", response_model=list[ScheduleAlternative])
def alternatives(payload: ProposalRequest | None = None) -> list[ScheduleAlternative]:
    return generate_reschedule_proposals(payload.request_ids if payload else [])


@router.post("/approve")
def approve_schedule(role: str = "requester") -> dict:
    require_schedule_manager(role, "approve schedules")
    requests = requests_with_locked_schedule()
    schedule = list(SCHEDULED_WORK.values())
    errors = validate_scheduled_work(schedule, requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    conflicts = detect_conflicts(schedule, requests)
    if conflicts:
        return {"approved": False, "unresolved_conflicts": len(conflicts)}
    locked_count = 0
    for item in schedule:
        if item.status == ApprovalStatus.LOCKED:
            continue
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
        locked_count += 1
    return {"approved": True, "unresolved_conflicts": 0, "locked_items": locked_count}


@router.post("/approve-selected")
def approve_selected(payload: ApproveRequest, role: str = "requester") -> dict:
    require_schedule_manager(role, "approve schedules")
    if not payload.request_ids:
        raise HTTPException(status_code=422, detail=["Select at least one scheduled task to approve."])

    missing = [request_id for request_id in payload.request_ids if request_id not in SCHEDULED_WORK]
    if missing:
        raise HTTPException(status_code=422, detail=[f"{request_id} is not currently scheduled." for request_id in missing])

    requests = requests_with_locked_schedule()
    schedule = list(SCHEDULED_WORK.values())
    errors = validate_scheduled_work(schedule, requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    conflicts = detect_conflicts(schedule, requests)
    if conflicts:
        raise HTTPException(status_code=422, detail=[conflict.explanation for conflict in conflicts])

    approved = 0
    for request_id in payload.request_ids:
        item = SCHEDULED_WORK[request_id]
        if item.status == ApprovalStatus.LOCKED:
            continue
        locked_item = item.model_copy(update={"status": ApprovalStatus.LOCKED})
        SCHEDULED_WORK[request_id] = locked_item
        request = REQUESTS.get(request_id)
        if request:
            REQUESTS[request_id] = request.model_copy(
                update={
                    "approval_status": ApprovalStatus.LOCKED,
                    "locked": True,
                    "fixed_start": locked_item.start_time,
                    "fixed_end": locked_item.end_time,
                }
            )
        approved += 1

    return {"approved": True, "locked_items": approved, "request_ids": payload.request_ids}


@router.post("/reject/{request_id}")
def reject_request(request_id: str, role: str = "requester") -> dict:
    require_schedule_manager(role, "reject requests")
    request = REQUESTS.get(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found.")
    REQUESTS[request_id] = request.model_copy(update={"approval_status": ApprovalStatus.CONFLICT, "locked": False})
    SCHEDULED_WORK.pop(request_id, None)
    return {"rejected": True, "request_id": request_id}


@router.post("/lock/{request_id}", response_model=ScheduledWork)
def lock_request(request_id: str, role: str = "requester") -> ScheduledWork:
    require_schedule_manager(role, "lock scheduled work")
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
    require_schedule_manager(role, "unlock scheduled work")
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
    require_schedule_manager(role, "modify scheduled work")
    scheduled = SCHEDULED_WORK.get(request_id)
    if not scheduled:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    unsupported = sorted(set(payload) - SCHEDULE_MODIFY_FIELDS)
    if unsupported:
        raise HTTPException(status_code=422, detail=[f"{field} cannot be modified." for field in unsupported])
    try:
        updated = ScheduledWork.model_validate({**scheduled.model_dump(), **payload, "request_id": request_id})
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    proposed = [updated if item.request_id == request_id else item for item in SCHEDULED_WORK.values()]
    requests = requests_with_locked_schedule()
    errors = validate_scheduled_work(proposed, requests)
    conflicts = detect_conflicts(proposed, requests)
    if errors or conflicts:
        raise HTTPException(status_code=422, detail=errors or [conflict.explanation for conflict in conflicts])
    SCHEDULED_WORK[request_id] = updated
    return updated
