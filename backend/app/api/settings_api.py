from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.auth import require_schedule_manager
from app.domain.models import SchedulingSettings
from app.repositories import scheduling_settings_repository, unit_of_work

router = APIRouter()


@router.get("/scheduling", response_model=SchedulingSettings)
def scheduling_settings() -> SchedulingSettings:
    return scheduling_settings_repository.get()


@router.patch("/scheduling", response_model=SchedulingSettings)
def update_scheduling_settings(payload: dict, role: str = "requester") -> SchedulingSettings:
    require_schedule_manager(role, "update scheduling settings")
    current = scheduling_settings_repository.get()
    try:
        updated = SchedulingSettings.model_validate({**current.model_dump(), **payload})
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    with unit_of_work() as work:
        return work.settings.save(updated)
