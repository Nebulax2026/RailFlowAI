from fastapi import APIRouter

from app.conflict.detector import detect_conflicts
from app.domain.models import Conflict
from app.repositories import requests_repository, schedule_repository

router = APIRouter()


@router.post("/detect", response_model=list[Conflict])
def detect_current_conflicts() -> list[Conflict]:
    return detect_conflicts(schedule_repository.list(), requests_repository.list())
