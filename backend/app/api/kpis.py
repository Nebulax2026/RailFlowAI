from fastapi import APIRouter

from app.conflict.detector import detect_conflicts
from app.domain.models import KpiSnapshot
from app.kpi.calculator import calculate_kpis
from app.repositories import requests_repository, schedule_repository

router = APIRouter()


@router.get("", response_model=KpiSnapshot)
def get_kpis() -> KpiSnapshot:
    schedule = schedule_repository.list()
    requests = requests_repository.list()
    conflicts = detect_conflicts(schedule, requests)
    return calculate_kpis(requests, schedule, conflicts)
