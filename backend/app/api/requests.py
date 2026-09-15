from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.adapters.manual_adapter import from_manual_payload
from app.audit import record_audit_event
from app.domain.enums import ApprovalStatus
from app.domain.models import MaintenanceRequest, RequestFitResponse, SlotRecommendation, UrgentConfirmRequest
from app.repositories import requests_repository, unit_of_work
from app.scheduler.service import confirm_urgent_request, evaluate_fit, recommend_slot, validate_request_for_queue

router = APIRouter()


@router.post("/recommend-slot", response_model=SlotRecommendation)
def recommend_request_slot(payload: dict) -> SlotRecommendation:
    try:
        request = from_manual_payload(payload)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    errors = validate_request_for_queue(request)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return recommend_slot(request)


@router.post("", response_model=RequestFitResponse)
def create_request(payload: dict) -> RequestFitResponse:
    try:
        request = from_manual_payload(payload)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    errors = validate_request_for_queue(request)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    with unit_of_work() as work:
        work.requests.save(request)
        response = evaluate_fit(request)
        if response.request != request:
            work.requests.save(response.request)
        if response.fits_current_schedule and response.scheduled_work:
            scheduled_request = request.model_copy(
                update={
                    "approval_status": ApprovalStatus.SCHEDULED,
                    "locked": False,
                    "fixed_start": None,
                    "fixed_end": None,
                }
            )
            work.schedule.save(response.scheduled_work)
            work.requests.save(scheduled_request)
            response = response.model_copy(update={"request": scheduled_request})
        record_audit_event(
            "request_created",
            f"Request {request.request_id} was created.",
            actor=request.created_by,
            request_ids=[request.request_id],
            details={"fits_current_schedule": response.fits_current_schedule},
        )
        return response


@router.get("", response_model=list[MaintenanceRequest])
def list_requests() -> list[MaintenanceRequest]:
    return requests_repository.list()


@router.post("/{request_id}/confirm-urgent", response_model=MaintenanceRequest)
def confirm_urgent(request_id: str, payload: UrgentConfirmRequest | None = None) -> MaintenanceRequest:
    try:
        return confirm_urgent_request(request_id, payload.requester_message if payload else None)
    except ValueError as error:
        raise HTTPException(status_code=404 if str(error) == "Request not found." else 422, detail=str(error)) from error


@router.patch("/{request_id}", response_model=MaintenanceRequest)
def update_request(request_id: str, payload: dict) -> MaintenanceRequest:
    existing = requests_repository.get(request_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Request not found.")
    if "request_id" in payload and payload["request_id"] != request_id:
        raise HTTPException(status_code=422, detail="Request ID cannot be changed.")
    try:
        updated = MaintenanceRequest.model_validate({**existing.model_dump(), **payload, "request_id": request_id})
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    errors = validate_request_for_queue(updated)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    with unit_of_work() as work:
        saved = work.requests.save(updated)
        record_audit_event(
            "request_updated",
            f"Request {request_id} was updated.",
            actor=updated.created_by,
            request_ids=[request_id],
            details={"changed_fields": sorted(payload.keys())},
        )
    return saved
