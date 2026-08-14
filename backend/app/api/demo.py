from pathlib import Path

from fastapi import APIRouter

from app.adapters.csv_adapter import from_csv
from app.domain.enums import ApprovalStatus
from app.domain.models import ScheduledWork
from app.storage import REQUESTS, SCHEDULED_WORK

router = APIRouter()

SAMPLE_REQUESTS_PATH = Path(__file__).resolve().parents[3] / "data" / "sample_requests.csv"


@router.post("/seed")
def seed_demo_data() -> dict:
    requests = from_csv(SAMPLE_REQUESTS_PATH.read_text(encoding="utf-8-sig"))
    REQUESTS.clear()
    SCHEDULED_WORK.clear()

    for request in requests:
        REQUESTS[request.request_id] = request
        should_seed_schedule = request.approval_status in {ApprovalStatus.LOCKED, ApprovalStatus.SCHEDULED}
        if should_seed_schedule and request.fixed_start and request.fixed_end:
            SCHEDULED_WORK[request.request_id] = ScheduledWork(
                schedule_id="demo-seed",
                request_id=request.request_id,
                start_time=request.fixed_start,
                end_time=request.fixed_end,
                assigned_crew=request.required_crew,
                assigned_equipment=request.required_equipment,
                track_sector=request.track_sector,
                status=ApprovalStatus.LOCKED if request.locked else ApprovalStatus.SCHEDULED,
            )

    return {
        "seeded": True,
        "requests": len(REQUESTS),
        "locked_schedule_items": len(SCHEDULED_WORK),
        "tentative_schedule_items": sum(1 for item in SCHEDULED_WORK.values() if item.status == ApprovalStatus.SCHEDULED),
    }


@router.post("/reset")
def reset_demo_data() -> dict:
    REQUESTS.clear()
    SCHEDULED_WORK.clear()
    return {"reset": True, "requests": 0, "scheduled_work": 0}
