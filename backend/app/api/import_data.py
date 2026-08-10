from fastapi import APIRouter, File, UploadFile

from app.adapters.csv_adapter import from_csv, preview_csv
from app.storage import REQUESTS

router = APIRouter()


@router.post("/preview")
async def import_preview(file: UploadFile = File(...)) -> dict:
    content = (await file.read()).decode("utf-8-sig")
    return preview_csv(content)


@router.post("/confirm")
async def import_confirm(file: UploadFile = File(...)) -> dict:
    content = (await file.read()).decode("utf-8-sig")
    requests = from_csv(content)
    for request in requests:
        REQUESTS[request.request_id] = request
    return {"imported": len(requests), "request_ids": [request.request_id for request in requests]}
