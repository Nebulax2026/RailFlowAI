from app.domain.models import MaintenanceRequest


def from_json_rows(rows: list[dict]) -> list[MaintenanceRequest]:
    return [MaintenanceRequest.model_validate(row) for row in rows]
