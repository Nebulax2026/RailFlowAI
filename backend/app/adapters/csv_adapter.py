import csv
from io import StringIO

from app.adapters.field_mapping import DEFAULT_FIELD_MAPPING, REQUIRED_FIELDS
from app.adapters.normalizers import parse_bool, parse_list
from app.domain.enums import RequestSource
from app.domain.models import MaintenanceRequest


def preview_csv(content: str) -> dict:
    reader = csv.DictReader(StringIO(content))
    detected_columns = reader.fieldnames or []
    suggested_mapping = {
        column: DEFAULT_FIELD_MAPPING[column]
        for column in detected_columns
        if column in DEFAULT_FIELD_MAPPING
    }
    mapped_fields = set(suggested_mapping.values())
    missing_required_fields = sorted(REQUIRED_FIELDS - mapped_fields)

    return {
        "detected_columns": detected_columns,
        "suggested_mapping": suggested_mapping,
        "missing_required_fields": missing_required_fields,
        "sample_rows": list(reader)[:5],
        "can_import": not missing_required_fields,
    }


def from_csv(content: str, field_mapping: dict[str, str] | None = None) -> list[MaintenanceRequest]:
    mapping = field_mapping or DEFAULT_FIELD_MAPPING
    rows = csv.DictReader(StringIO(content))
    requests: list[MaintenanceRequest] = []

    for row in rows:
        normalized: dict = {"source": RequestSource.CSV}
        for external_key, value in row.items():
            internal_key = mapping.get(external_key)
            if not internal_key:
                continue
            if value == "":
                continue
            if internal_key in {"required_crew", "required_equipment", "dependencies", "incompatible_work_types"}:
                normalized[internal_key] = parse_list(value)
            elif internal_key == "locked":
                normalized[internal_key] = parse_bool(value)
            else:
                normalized[internal_key] = value

        requests.append(MaintenanceRequest.model_validate(normalized))

    return requests
