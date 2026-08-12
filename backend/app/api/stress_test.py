from fastapi import APIRouter

from app.storage import REQUESTS, SCHEDULED_WORK
from app.stress.stress_tester import stress_test_duration_increase

router = APIRouter()


@router.post("")
def run_stress_test(increase_percent: int = 20) -> dict:
    return stress_test_duration_increase(list(SCHEDULED_WORK.values()), increase_percent, list(REQUESTS.values()))
