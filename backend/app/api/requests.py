from fastapi import APIRouter, HTTPException

from app.adapters.manual_adapter import from_manual_payload
from app.domain.models import MaintenanceRequest
from app.storage import REQUESTS
from app.validation.business_validator import validate_business_rules

router = APIRouter()


@router.post("", response_model=MaintenanceRequest)
def create_request(payload: dict) -> MaintenanceRequest:
    request = from_manual_payload(payload)
    errors = validate_business_rules(request)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    REQUESTS[request.request_id] = request
    return request


@router.get("", response_model=list[MaintenanceRequest])
def list_requests() -> list[MaintenanceRequest]:
    return list(REQUESTS.values())


@router.patch("/{request_id}", response_model=MaintenanceRequest)
def update_request(request_id: str, payload: dict) -> MaintenanceRequest:
    existing = REQUESTS.get(request_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Request not found.")
    updated = existing.model_copy(update=payload)
    REQUESTS[request_id] = updated
    return updated
