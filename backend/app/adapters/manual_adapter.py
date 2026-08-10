from app.domain.models import MaintenanceRequest


def from_manual_payload(payload: dict) -> MaintenanceRequest:
    return MaintenanceRequest.model_validate(payload)
