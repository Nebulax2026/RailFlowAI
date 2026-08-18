from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.auth import require_schedule_manager
from app.audit import record_audit_event
from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import ApproveRequest, ProposalRequest, ProposalSnapshot, ScheduleAlternative, ScheduledWork
from app.proposals import mark_proposal_applied
from app.repositories import proposal_snapshot_repository, requests_repository, schedule_repository, unit_of_work
from app.scheduler.service import apply_alternative, apply_schedule, build_optimised_schedule, generate_reschedule_proposals, requests_with_locked_schedule
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
    return schedule_repository.list()


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
    mark_proposal_applied(payload.proposal_id if payload else None, payload.request_ids if payload else [], option, role)
    return scheduled


@router.post("/alternatives", response_model=list[ScheduleAlternative])
def alternatives(payload: ProposalRequest | None = None) -> list[ScheduleAlternative]:
    return generate_reschedule_proposals(payload.request_ids if payload else [])


@router.get("/proposals", response_model=list[ProposalSnapshot])
def proposal_snapshots() -> list[ProposalSnapshot]:
    return proposal_snapshot_repository.list()


@router.get("/proposals/{proposal_id}", response_model=ProposalSnapshot)
def proposal_snapshot(proposal_id: str) -> ProposalSnapshot:
    snapshot = proposal_snapshot_repository.get(proposal_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Proposal snapshot not found.")
    return snapshot


@router.post("/approve")
def approve_schedule(role: str = "requester") -> dict:
    require_schedule_manager(role, "approve schedules")
    requests = requests_with_locked_schedule()
    schedule = schedule_repository.list()
    errors = validate_scheduled_work(schedule, requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    conflicts = detect_conflicts(schedule, requests)
    if conflicts:
        return {"approved": False, "unresolved_conflicts": len(conflicts)}
    locked_count = 0
    with unit_of_work() as work:
        for item in schedule:
            if item.status == ApprovalStatus.LOCKED:
                continue
            locked_item = item.model_copy(update={"status": ApprovalStatus.LOCKED})
            work.schedule.save(locked_item)
            request = work.requests.get(item.request_id)
            if request:
                work.requests.save(
                    request.model_copy(
                        update={
                            "approval_status": ApprovalStatus.LOCKED,
                            "locked": True,
                            "fixed_start": item.start_time,
                            "fixed_end": item.end_time,
                        }
                    )
                )
            locked_count += 1
        record_audit_event(
            "schedule_approved",
            f"Approved {locked_count} tentative schedule item{'' if locked_count == 1 else 's'}.",
            actor=role,
            request_ids=[item.request_id for item in schedule if item.status != ApprovalStatus.LOCKED],
            details={"locked_items": locked_count, "approval_scope": "all"},
        )
    return {"approved": True, "unresolved_conflicts": 0, "locked_items": locked_count}


@router.post("/approve-selected")
def approve_selected(payload: ApproveRequest, role: str = "requester") -> dict:
    require_schedule_manager(role, "approve schedules")
    if not payload.request_ids:
        raise HTTPException(status_code=422, detail=["Select at least one scheduled task to approve."])

    missing = [request_id for request_id in payload.request_ids if not schedule_repository.get(request_id)]
    if missing:
        raise HTTPException(status_code=422, detail=[f"{request_id} is not currently scheduled." for request_id in missing])

    requests = requests_with_locked_schedule()
    schedule = schedule_repository.list()
    errors = validate_scheduled_work(schedule, requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    conflicts = detect_conflicts(schedule, requests)
    if conflicts:
        raise HTTPException(status_code=422, detail=[conflict.explanation for conflict in conflicts])

    approved = 0
    with unit_of_work() as work:
        approved_request_ids: list[str] = []
        for request_id in payload.request_ids:
            item = work.schedule.get(request_id)
            if not item or item.status == ApprovalStatus.LOCKED:
                continue
            locked_item = item.model_copy(update={"status": ApprovalStatus.LOCKED})
            work.schedule.save(locked_item)
            request = work.requests.get(request_id)
            if request:
                work.requests.save(
                    request.model_copy(
                        update={
                            "approval_status": ApprovalStatus.LOCKED,
                            "locked": True,
                            "fixed_start": locked_item.start_time,
                            "fixed_end": locked_item.end_time,
                        }
                    )
                )
            approved += 1
            approved_request_ids.append(request_id)
        record_audit_event(
            "schedule_approved",
            f"Approved {approved} selected schedule item{'' if approved == 1 else 's'}.",
            actor=role,
            request_ids=approved_request_ids,
            details={"locked_items": approved, "approval_scope": "selected"},
        )

    return {"approved": True, "locked_items": approved, "request_ids": payload.request_ids}


@router.post("/reject/{request_id}")
def reject_request(request_id: str, role: str = "requester") -> dict:
    require_schedule_manager(role, "reject requests")
    request = requests_repository.get(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found.")
    with unit_of_work() as work:
        work.requests.save(request.model_copy(update={"approval_status": ApprovalStatus.CONFLICT, "locked": False}))
        work.schedule.delete(request_id)
        record_audit_event(
            "request_rejected",
            f"Request {request_id} was rejected.",
            actor=role,
            request_ids=[request_id],
        )
    return {"rejected": True, "request_id": request_id}


@router.post("/lock/{request_id}", response_model=ScheduledWork)
def lock_request(request_id: str, role: str = "requester") -> ScheduledWork:
    require_schedule_manager(role, "lock scheduled work")
    scheduled = schedule_repository.get(request_id)
    request = requests_repository.get(request_id)
    if not scheduled or not request:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    locked = scheduled.model_copy(update={"status": ApprovalStatus.LOCKED})
    with unit_of_work() as work:
        work.schedule.save(locked)
        work.requests.save(
            request.model_copy(
                update={
                    "approval_status": ApprovalStatus.LOCKED,
                    "locked": True,
                    "fixed_start": locked.start_time,
                    "fixed_end": locked.end_time,
                }
            )
        )
        record_audit_event(
            "schedule_approved",
            f"Schedule item {request_id} was locked.",
            actor=role,
            request_ids=[request_id],
            details={"approval_scope": "single_lock"},
        )
    return locked


@router.post("/unlock/{request_id}", response_model=ScheduledWork)
def unlock_request(request_id: str, role: str = "requester") -> ScheduledWork:
    require_schedule_manager(role, "unlock scheduled work")
    scheduled = schedule_repository.get(request_id)
    request = requests_repository.get(request_id)
    if not scheduled or not request:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    unlocked = scheduled.model_copy(update={"status": ApprovalStatus.SCHEDULED})
    with unit_of_work() as work:
        work.schedule.save(unlocked)
        work.requests.save(
            request.model_copy(
                update={"approval_status": ApprovalStatus.SCHEDULED, "locked": False, "fixed_start": None, "fixed_end": None}
            )
        )
        record_audit_event(
            "schedule_modified",
            f"Schedule item {request_id} was unlocked.",
            actor=role,
            request_ids=[request_id],
            details={"change_type": "unlock"},
        )
    return unlocked


@router.patch("/modify/{request_id}", response_model=ScheduledWork)
def modify_scheduled_work(request_id: str, payload: dict, role: str = "requester") -> ScheduledWork:
    require_schedule_manager(role, "modify scheduled work")
    scheduled = schedule_repository.get(request_id)
    if not scheduled:
        raise HTTPException(status_code=404, detail="Scheduled work not found.")
    unsupported = sorted(set(payload) - SCHEDULE_MODIFY_FIELDS)
    if unsupported:
        raise HTTPException(status_code=422, detail=[f"{field} cannot be modified." for field in unsupported])
    try:
        updated = ScheduledWork.model_validate({**scheduled.model_dump(), **payload, "request_id": request_id})
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    proposed = [updated if item.request_id == request_id else item for item in schedule_repository.list()]
    requests = requests_with_locked_schedule()
    errors = validate_scheduled_work(proposed, requests)
    conflicts = detect_conflicts(proposed, requests)
    if errors or conflicts:
        raise HTTPException(status_code=422, detail=errors or [conflict.explanation for conflict in conflicts])
    with unit_of_work() as work:
        saved = work.schedule.save(updated)
        record_audit_event(
            "schedule_modified",
            f"Schedule item {request_id} was modified.",
            actor=role,
            request_ids=[request_id],
            details={
                "changed_fields": sorted(payload.keys()),
                "previous_start": scheduled.start_time.isoformat(),
                "previous_end": scheduled.end_time.isoformat(),
                "new_start": saved.start_time.isoformat(),
                "new_end": saved.end_time.isoformat(),
            },
        )
    return saved
