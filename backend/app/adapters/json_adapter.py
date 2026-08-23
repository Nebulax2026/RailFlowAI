from pydantic import ValidationError

from app.domain.enums import RequestSource
from app.domain.models import MaintenanceRequest


def from_json_rows(rows: list[dict]) -> list[MaintenanceRequest]:
    return [MaintenanceRequest.model_validate({"source": RequestSource.JSON, **row}) for row in rows]


def preview_json_rows(rows: list[dict]) -> tuple[list[MaintenanceRequest], list[str]]:
    requests: list[MaintenanceRequest] = []
    errors: list[str] = []

    for row_number, row in enumerate(rows, start=1):
        try:
            requests.append(MaintenanceRequest.model_validate({"source": RequestSource.JSON, **row}))
        except ValidationError as error:
            for item in error.errors():
                field = ".".join(str(part) for part in item["loc"])
                errors.append(f"Row {row_number}, {field}: {item['msg']}")

    return requests, errors
