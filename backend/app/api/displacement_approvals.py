from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, DisplacementApprovalStatus
from app.domain.models import DisplacementApproval
from app.repositories import displacement_approval_repository, requests_repository, schedule_repository, unit_of_work
from app.scheduler.service import create_notification, requests_with_locked_schedule, validate_schedule_against_blocks
from app.validation.schedule_validator import validate_scheduled_work

router = APIRouter()


@router.get("", response_model=list[DisplacementApproval])
def list_displacement_approvals(
    owner: str | None = None,
    status: DisplacementApprovalStatus | None = None,
) -> list[DisplacementApproval]:
    return displacement_approval_repository.list(owner=owner, status=status)


@router.post("/{approval_id}/approve", response_model=DisplacementApproval)
def approve_displacement(approval_id: str, owner: str) -> DisplacementApproval:
    approval = displacement_approval_repository.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Displacement approval not found.")
    if approval.status != DisplacementApprovalStatus.PENDING:
        raise HTTPException(status_code=422, detail="Displacement approval has already been decided.")
    if owner != approval.owner:
        raise HTTPException(status_code=403, detail="Only the affected requester can approve this displacement.")

    proposed_schedule = [
        item
        for item in schedule_repository.list()
        if item.request_id not in {approval.urgent_request_id, approval.displaced_request_id}
    ]
    proposed_schedule.extend(
        [
            approval.urgent_work.model_copy(update={"status": ApprovalStatus.SCHEDULED}),
            approval.displaced_work.model_copy(update={"status": ApprovalStatus.SCHEDULED}),
        ]
    )
    requests = requests_with_locked_schedule()
    errors = validate_scheduled_work(proposed_schedule, requests)
    errors.extend(validate_schedule_against_blocks(proposed_schedule))
    conflicts = detect_conflicts(proposed_schedule, requests_repository.list())
    if errors or conflicts:
        raise HTTPException(status_code=422, detail=errors or [conflict.explanation for conflict in conflicts])

    decided = approval.model_copy(update={"status": DisplacementApprovalStatus.APPROVED, "decided_at": datetime.now(timezone.utc)})
    urgent_request = requests_repository.get(approval.urgent_request_id)
    with unit_of_work() as work:
        work.schedule.save(approval.urgent_work.model_copy(update={"status": ApprovalStatus.SCHEDULED}))
        work.schedule.save(approval.displaced_work.model_copy(update={"status": ApprovalStatus.SCHEDULED}))
        for request_id in [approval.urgent_request_id, approval.displaced_request_id]:
            request = work.requests.get(request_id)
            if request:
                work.requests.save(
                    request.model_copy(
                        update={
                            "approval_status": ApprovalStatus.SCHEDULED,
                            "locked": False,
                            "fixed_start": None,
                            "fixed_end": None,
                        }
                    )
                )
        saved = work.displacement_approvals.save(decided)
        create_notification(
            owner=urgent_request.created_by if urgent_request else "field",
            message=f"Displacement for urgent request {approval.urgent_request_id} was approved.",
            notification_type="displacement_approved",
            request_ids=[approval.urgent_request_id, approval.displaced_request_id],
            approval_id=approval.approval_id,
        )
        return saved


@router.post("/{approval_id}/reject", response_model=DisplacementApproval)
def reject_displacement(approval_id: str, owner: str) -> DisplacementApproval:
    approval = displacement_approval_repository.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Displacement approval not found.")
    if approval.status != DisplacementApprovalStatus.PENDING:
        raise HTTPException(status_code=422, detail="Displacement approval has already been decided.")
    if owner != approval.owner:
        raise HTTPException(status_code=403, detail="Only the affected requester can reject this displacement.")
    decided = approval.model_copy(update={"status": DisplacementApprovalStatus.REJECTED, "decided_at": datetime.now(timezone.utc)})
    urgent_request = requests_repository.get(approval.urgent_request_id)
    with unit_of_work() as work:
        saved = work.displacement_approvals.save(decided)
        create_notification(
            owner=urgent_request.created_by if urgent_request else "field",
            message=f"Displacement for urgent request {approval.urgent_request_id} was rejected.",
            notification_type="displacement_rejected",
            request_ids=[approval.urgent_request_id, approval.displaced_request_id],
            approval_id=approval.approval_id,
        )
        return saved
