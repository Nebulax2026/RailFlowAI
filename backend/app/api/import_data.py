import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.adapters.csv_adapter import from_csv, preview_csv
from app.adapters.json_adapter import from_json_rows
from app.api.uploads import read_upload_text
from app.audit import record_audit_event
from app.domain.models import MaintenanceRequest
from app.repositories import unit_of_work
from app.scheduler.service import validate_request_for_queue

router = APIRouter()


@router.post("/preview")
async def import_preview(file: UploadFile = File(...)) -> dict:
    content = await _read_csv(file)
    return preview_csv(content)


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
    try:
        requests = from_json_rows(rows)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    errors = _validate_import_batch(requests)
    return {
        "can_import": not errors,
        "errors": errors,
        "sample_rows": rows[:5],
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
    with unit_of_work() as work:
        for request in requests:
            work.requests.save(request)
            record_audit_event(
                "request_created",
                f"Imported request {request.request_id}.",
                actor=request.created_by,
                request_ids=[request.request_id],
                details={"source": request.source.value},
            )
    return {"imported": len(requests), "request_ids": [request.request_id for request in requests]}


def _validate_import_batch(requests: list[MaintenanceRequest]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for request in requests:
        if request.request_id in seen:
            errors.append(f"{request.request_id} appears more than once in the import file.")
        seen.add(request.request_id)
        errors.extend(f"{request.request_id}: {error}" for error in validate_request_for_queue(request))
    return errors
