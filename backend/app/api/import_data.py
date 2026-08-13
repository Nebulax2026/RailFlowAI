import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.adapters.csv_adapter import from_csv, preview_csv
from app.adapters.json_adapter import from_json_rows
from app.domain.models import MaintenanceRequest
from app.scheduler.service import validate_request_for_queue
from app.storage import REQUESTS

router = APIRouter()


@router.post("/preview")
async def import_preview(file: UploadFile = File(...)) -> dict:
    content = (await file.read()).decode("utf-8-sig")
    return preview_csv(content)


@router.post("/confirm")
async def import_confirm(file: UploadFile = File(...)) -> dict:
    content = (await file.read()).decode("utf-8-sig")
    try:
        requests = from_csv(content)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    errors = _validate_import_batch(requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    for request in requests:
        REQUESTS[request.request_id] = request
    return {"imported": len(requests), "request_ids": [request.request_id for request in requests]}


@router.post("/json/preview")
async def import_json_preview(file: UploadFile = File(...)) -> dict:
    content = (await file.read()).decode("utf-8-sig")
    try:
        rows = json.loads(content)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {error.msg}.") from error
    if not isinstance(rows, list):
        raise HTTPException(status_code=422, detail="JSON import must be an array of request objects.")
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
    content = (await file.read()).decode("utf-8-sig")
    try:
        rows = json.loads(content)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {error.msg}.") from error
    if not isinstance(rows, list):
        raise HTTPException(status_code=422, detail="JSON import must be an array of request objects.")
    try:
        requests = from_json_rows(rows)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    errors = _validate_import_batch(requests)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    for request in requests:
        REQUESTS[request.request_id] = request
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
