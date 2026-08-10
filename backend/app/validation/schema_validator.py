from pydantic import ValidationError

from app.domain.models import MaintenanceRequest


def validate_request_payload(payload: dict) -> tuple[MaintenanceRequest | None, list[str]]:
    try:
        return MaintenanceRequest.model_validate(payload), []
    except ValidationError as exc:
        return None, [error["msg"] for error in exc.errors()]
