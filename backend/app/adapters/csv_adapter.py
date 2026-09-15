from __future__ import annotations

import csv
from io import StringIO

from pydantic import ValidationError

from app.adapters.field_mapping import DEFAULT_FIELD_MAPPING, REQUIRED_FIELDS
from app.adapters.normalizers import parse_bool, parse_list
from app.domain.enums import RequestSource
from app.domain.models import MaintenanceRequest


def preview_csv(content: str) -> dict:
    reader = csv.DictReader(StringIO(content))
    if reader.fieldnames:
        reader.fieldnames = [_clean_header(column) for column in reader.fieldnames]
    detected_columns = reader.fieldnames or []
    rows = list(reader)
    suggested_mapping = {
        column: _mapped_field(column, DEFAULT_FIELD_MAPPING)
        for column in detected_columns
        if _mapped_field(column, DEFAULT_FIELD_MAPPING)
    }
    mapped_fields = set(suggested_mapping.values())
    missing_required_fields = sorted(REQUIRED_FIELDS - mapped_fields)
    errors: list[str] = []

    if not rows:
        errors.append("Import file must include at least one data row.")
    elif not missing_required_fields:
        for row_number, row in enumerate(rows, start=2):
            try:
                MaintenanceRequest.model_validate(_normalise_row(row, suggested_mapping))
            except ValidationError as error:
                errors.extend(_format_row_errors(row_number, error))

    return {
        "detected_columns": detected_columns,
        "suggested_mapping": suggested_mapping,
        "missing_required_fields": missing_required_fields,
        "errors": errors,
        "sample_rows": rows[:5],
        "total_rows": len(rows),
        "can_import": not missing_required_fields and not errors,
    }


def from_csv(content: str, field_mapping: dict[str, str] | None = None) -> list[MaintenanceRequest]:
    mapping = field_mapping or DEFAULT_FIELD_MAPPING
    rows = csv.DictReader(StringIO(content))
    if rows.fieldnames:
        rows.fieldnames = [_clean_header(column) for column in rows.fieldnames]
    requests: list[MaintenanceRequest] = []

    for row in rows:
        requests.append(MaintenanceRequest.model_validate(_normalise_row(row, mapping)))

    return requests


def _normalise_row(row: dict[str, str], mapping: dict[str, str]) -> dict:
    normalized: dict = {"source": RequestSource.CSV}
    for external_key, value in row.items():
        internal_key = _mapped_field(external_key, mapping)
        clean_value = value.strip() if isinstance(value, str) else value
        if not internal_key or clean_value == "":
            continue
        if internal_key in {"required_crew", "required_equipment", "dependencies", "incompatible_work_types"}:
            normalized[internal_key] = parse_list(clean_value)
        elif internal_key == "locked":
            normalized[internal_key] = parse_bool(clean_value)
        else:
            normalized[internal_key] = clean_value
    return normalized


def _clean_header(value: str) -> str:
    return value.strip().removeprefix("\ufeff").strip()


def _field_key(value: str) -> str:
    return _clean_header(value).casefold()


def _mapped_field(external_key: str | None, mapping: dict[str, str]) -> str | None:
    if external_key is None:
        return None
    if external_key in mapping:
        return mapping[external_key]
    normalized_mapping = {_field_key(key): value for key, value in mapping.items()}
    return normalized_mapping.get(_field_key(external_key))


def _format_row_errors(row_number: int, error: ValidationError) -> list[str]:
    messages: list[str] = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"])
        messages.append(f"Row {row_number}, {field}: {item['msg']}")
    return messages
