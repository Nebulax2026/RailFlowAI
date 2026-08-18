from pathlib import Path

from fastapi import APIRouter

from app.adapters.csv_adapter import from_csv
from app.audit import record_audit_event
from app.domain.enums import ApprovalStatus
from app.domain.models import ScheduledWork
from app.repositories import requests_repository, schedule_repository, unit_of_work

router = APIRouter()

SAMPLE_REQUESTS_PATH = Path(__file__).resolve().parents[3] / "data" / "sample_requests.csv"


@router.post("/seed")
def seed_demo_data() -> dict:
    requests = from_csv(SAMPLE_REQUESTS_PATH.read_text(encoding="utf-8-sig"))
    with unit_of_work() as work:
        work.requests.clear()
        work.schedule.clear()
        work.proposals.clear()
        work.audit.clear()

        for request in requests:
            work.requests.save(request)
            should_seed_schedule = request.approval_status in {ApprovalStatus.LOCKED, ApprovalStatus.SCHEDULED}
            if should_seed_schedule and request.fixed_start and request.fixed_end:
                work.schedule.save(
                    ScheduledWork(
                        schedule_id="demo-seed",
                        request_id=request.request_id,
                        start_time=request.fixed_start,
                        end_time=request.fixed_end,
                        assigned_crew=request.required_crew,
                        assigned_equipment=request.required_equipment,
                        track_sector=request.track_sector,
                        status=ApprovalStatus.LOCKED if request.locked else ApprovalStatus.SCHEDULED,
                    )
                )

        record_audit_event(
            "demo_seed",
            "Demo data was loaded.",
            actor="system",
            request_ids=[request.request_id for request in requests],
            details={
                "requests": len(requests_repository.list()),
                "scheduled_work": len(schedule_repository.list()),
            },
        )

    return {
        "seeded": True,
        "requests": len(requests_repository.list()),
        "locked_schedule_items": len(schedule_repository.list()),
        "tentative_schedule_items": sum(1 for item in schedule_repository.list() if item.status == ApprovalStatus.SCHEDULED),
    }


@router.post("/reset")
def reset_demo_data() -> dict:
    with unit_of_work() as work:
        work.requests.clear()
        work.schedule.clear()
        work.proposals.clear()
        work.audit.clear()
        record_audit_event(
            "demo_reset",
            "Demo state was reset.",
            actor="system",
        )
    return {"reset": True, "requests": 0, "scheduled_work": 0}
