from fastapi import APIRouter

from app.conflict.detector import detect_conflicts
from app.domain.models import Conflict
from app.storage import SCHEDULED_WORK

router = APIRouter()


@router.post("/detect", response_model=list[Conflict])
def detect_current_conflicts() -> list[Conflict]:
    return detect_conflicts(list(SCHEDULED_WORK.values()))
