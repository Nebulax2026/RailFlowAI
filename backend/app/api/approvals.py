from fastapi import APIRouter, HTTPException

from app.api.auth import require_schedule_manager
from app.domain.models import MaintenanceRequest, RejectRequest, ScheduledWork
from app.scheduler.service import approve_pending_request, reject_pending_request

router = APIRouter()


@router.post("/{request_id}/approve", response_model=ScheduledWork)
def approve_request(request_id: str, role: str = "requester") -> ScheduledWork:
    require_schedule_manager(role, "approve requests")
    try:
        return approve_pending_request(request_id, role)
    except ValueError as error:
        raise HTTPException(status_code=422 if str(error) != "Request not found." else 404, detail=str(error)) from error


@router.post("/{request_id}/reject", response_model=MaintenanceRequest)
def reject_request_approval(request_id: str, payload: RejectRequest, role: str = "requester") -> MaintenanceRequest:
    require_schedule_manager(role, "reject requests")
    try:
        return reject_pending_request(request_id, payload.reason, role)
    except ValueError as error:
        raise HTTPException(status_code=422 if str(error) != "Request not found." else 404, detail=str(error)) from error
