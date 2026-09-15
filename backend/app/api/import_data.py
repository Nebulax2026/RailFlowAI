from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.adapters.csv_adapter import from_csv, preview_csv
from app.adapters.field_mapping import REQUIRED_FIELDS
from app.adapters.json_adapter import from_json_rows, preview_json_rows
from app.api.uploads import read_upload_text
from app.audit import record_audit_event
from app.domain.enums import ApprovalStatus
from app.domain.models import MaintenanceRequest, ScheduledWork
from app.repositories import unit_of_work
from app.storage import REQUESTS, SCHEDULED_WORK
from app.validation.business_validator import validate_business_rules
from app.validation.dependency_rules import validate_work_type_prerequisites

router = APIRouter()


@router.post("/preview")
async def import_preview(file: UploadFile = File(...)) -> dict:
    content = await _read_csv(file)
    preview = preview_csv(content)
    if preview["can_import"]:
        requests = from_csv(content)
        preview["errors"] = _validate_import_batch(requests)
        preview["can_import"] = not preview["errors"]
        preview["request_ids"] = [request.request_id for request in requests]
    return preview


@router.post("/confirm")
async def import_confirm(file: UploadFile = File(...)) -> dict:
    content = await _read_csv(file)
    try:
        requests = from_csv(content)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    return _store_import_batch(requests)


@router.post("/json/preview")
async def import_json_preview(file: UploadFile = File(...)) -> dict:
    rows = await _read_json_rows(file)
    requests, row_errors = preview_json_rows(rows)
    detected_columns = list(dict.fromkeys(key for row in rows for key in row))
    missing_required_fields = sorted(REQUIRED_FIELDS - set(detected_columns))
    empty_errors = ["Import file must include at least one data row."] if not rows else []
    errors = [*empty_errors, *row_errors, *_validate_import_batch(requests)]
    return {
        "can_import": not errors,
        "detected_columns": detected_columns,
        "missing_required_fields": missing_required_fields,
        "errors": errors,
        "sample_rows": rows[:5],
        "total_rows": len(rows),
        "request_ids": [request.request_id for request in requests],
    }


@router.post("/json/confirm")
async def import_json_confirm(file: UploadFile = File(...)) -> dict:
    rows = await _read_json_rows(file)
    try:
        requests = from_json_rows(rows)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    return _store_import_batch(requests)


async def _read_csv(file: UploadFile) -> str:
    return await read_upload_text(
        file,
        allowed_content_types={"text/csv", "application/csv", "application/vnd.ms-excel"},
        allowed_extensions={".csv"},
    )


async def _read_json_rows(file: UploadFile) -> list[dict]:
    content = await read_upload_text(
        file,
        allowed_content_types={"application/json", "text/json"},
        allowed_extensions={".json"},
    )
    try:
        rows = json.loads(content)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {error.msg}.") from error
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise HTTPException(status_code=422, detail="JSON import must be an array of request objects.")
    return rows


def _store_import_batch(requests: list[MaintenanceRequest]) -> dict:
    errors = _validate_import_batch(requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    scheduled_items = 0
    with unit_of_work() as work:
        for request in requests:
            work.requests.save(request)
            work.schedule.delete(request.request_id)
            scheduled = _scheduled_item_for_import(request)
            if scheduled:
                work.schedule.save(scheduled)
                scheduled_items += 1
            record_audit_event(
                "request_created",
                f"Imported request {request.request_id}.",
                actor=request.created_by,
                request_ids=[request.request_id],
                details={"source": request.source.value},
            )
    return {
        "imported": len(requests),
        "scheduled_items": scheduled_items,
        "request_ids": [request.request_id for request in requests],
    }


def _validate_import_batch(requests: list[MaintenanceRequest]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    candidate_requests = {**REQUESTS, **{request.request_id: request for request in requests}}
    candidate_schedule = dict(SCHEDULED_WORK)

    for request in requests:
        candidate_schedule.pop(request.request_id, None)
        scheduled = _scheduled_item_for_import(request)
        if scheduled:
            candidate_schedule[request.request_id] = scheduled

    for request in requests:
        if request.request_id in seen:
            errors.append(f"{request.request_id} appears more than once in the import file.")
        seen.add(request.request_id)
        request_errors = validate_business_rules(request)
        if request.approval_status == ApprovalStatus.SCHEDULED and not _scheduled_item_for_import(request):
            request_errors.append("Scheduled imports must include fixed start and fixed end.")
        request_errors.extend(validate_work_type_prerequisites(request, candidate_requests, candidate_schedule))
        errors.extend(f"{request.request_id}: {error}" for error in request_errors)
    return errors


def _scheduled_item_for_import(request: MaintenanceRequest) -> ScheduledWork | None:
    if request.approval_status not in {ApprovalStatus.SCHEDULED, ApprovalStatus.LOCKED}:
        return None
    if not request.fixed_start or not request.fixed_end:
        return None
    return ScheduledWork(
        schedule_id="data-import",
        request_id=request.request_id,
        start_time=request.fixed_start,
        end_time=request.fixed_end,
        assigned_crew=request.required_crew,
        assigned_equipment=request.required_equipment,
        track_sector=request.track_sector,
        status=ApprovalStatus.LOCKED if request.locked or request.approval_status == ApprovalStatus.LOCKED else ApprovalStatus.SCHEDULED,
    )
