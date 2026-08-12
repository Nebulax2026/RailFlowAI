from fastapi import APIRouter

from app.conflict.detector import detect_conflicts
from app.domain.models import KpiSnapshot
from app.kpi.calculator import calculate_kpis
from app.storage import REQUESTS, SCHEDULED_WORK

router = APIRouter()


@router.get("", response_model=KpiSnapshot)
def get_kpis() -> KpiSnapshot:
    schedule = list(SCHEDULED_WORK.values())
    requests = list(REQUESTS.values())
    conflicts = detect_conflicts(schedule, requests)
    return calculate_kpis(requests, schedule, conflicts)
