from fastapi import APIRouter

from app.repositories import requests_repository, schedule_repository
from app.stress.stress_tester import stress_test_duration_increase

router = APIRouter()


@router.post("")
def run_stress_test(increase_percent: int = 20) -> dict:
    return stress_test_duration_increase(schedule_repository.list(), increase_percent, requests_repository.list())
