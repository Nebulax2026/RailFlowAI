from __future__ import annotations

import csv
import io
from datetime import date

from app.ps1.models import Activity, BufferRule, Contract, Instance, Line, LocationSupply, Sector, Station

EXPECTED_FILES: dict[str, tuple[str, ...]] = {
    "01_LINES.csv": ("line_code", "line_name"),
    "02_STATIONS.csv": ("station_id", "line_code", "seq", "is_interchange"),
    "03_SECTORS.csv": ("sector_id", "line_code", "from_station_id", "to_station_id", "seq", "is_shared"),
    "04_LOCATION_SUPPLY.csv": ("location_id", "location_kind", "line_code", "bound", "supply_capacity"),
    "05_BUFFER_LOCATION.csv": ("nature_of_works", "up_to_buffer_sectors", "opposite_bound_required"),
    "06_PARAMETERS.csv": ("key", "value"),
    "07_PROJECT_DETAILS.csv": (
        "contract_number", "contract_description", "contract_award_date", "activity_type",
        "nature_of_activity", "contract_priority", "contract_completion_date", "planned_completion_date",
        "number_of_workfronts", "access_type", "number_of_maximum_access_per_week",
    ),
    "08_ACTIVITY_DETAILS.csv": (
        "activity_id", "contract_number", "activity_type", "start_location_id", "end_location_id",
        "total_accesses", "planned_start_date", "predecessor_activity_id", "activity_priority",
    ),
}


class InstanceValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def parse_instance(files: dict[str, bytes]) -> Instance:
    errors: list[str] = []
    missing = sorted(set(EXPECTED_FILES) - set(files))
    extra = sorted(set(files) - set(EXPECTED_FILES))
    if missing:
        errors.append(f"Missing files: {', '.join(missing)}")
    if extra:
        errors.append(f"Unexpected files: {', '.join(extra)}")
    if errors:
        raise InstanceValidationError(errors)

    tables = {name: _read_csv(name, files[name], errors) for name in EXPECTED_FILES}
    if errors:
        raise InstanceValidationError(errors)

    try:
        lines = _unique(
            "01_LINES.csv", (Line(row["line_code"], row["line_name"]) for row in tables["01_LINES.csv"]),
            lambda item: item.code, errors,
        )
        stations = _unique(
            "02_STATIONS.csv",
            (
                Station(row["station_id"], row["line_code"], _positive_int(row["seq"], "seq"), _flag(row["is_interchange"]))
                for row in tables["02_STATIONS.csv"]
            ),
            lambda item: (item.line_code, item.station_id), errors,
        )
        sectors = _unique(
            "03_SECTORS.csv",
            (
                Sector(row["sector_id"], row["line_code"], row["from_station_id"], row["to_station_id"],
                       _positive_int(row["seq"], "seq"), _flag(row["is_shared"]))
                for row in tables["03_SECTORS.csv"]
            ),
            lambda item: item.sector_id, errors,
        )
        supply = _unique(
            "04_LOCATION_SUPPLY.csv",
            (
                LocationSupply(row["location_id"], row["location_kind"], row["line_code"], row["bound"],
                               _positive_int(row["supply_capacity"], "supply_capacity"))
                for row in tables["04_LOCATION_SUPPLY.csv"]
            ),
            lambda item: item.location_id, errors,
        )
        buffers = _unique(
            "05_BUFFER_LOCATION.csv",
            (
                BufferRule(row["nature_of_works"], _nonnegative_int(row["up_to_buffer_sectors"], "up_to_buffer_sectors"),
                           _yes_no(row["opposite_bound_required"]))
                for row in tables["05_BUFFER_LOCATION.csv"]
            ),
            lambda item: item.nature_of_works, errors,
        )
        parameters = {row["key"]: row["value"] for row in tables["06_PARAMETERS.csv"]}
        contracts = _unique(
            "07_PROJECT_DETAILS.csv",
            (
                Contract(
                    row["contract_number"], row["contract_description"], _date(row["contract_award_date"]),
                    row["activity_type"], row["nature_of_activity"], _priority(row["contract_priority"]),
                    _date(row["contract_completion_date"]), _date(row["planned_completion_date"]),
                    _positive_int(row["number_of_workfronts"], "number_of_workfronts"), row["access_type"],
                    _positive_int(row["number_of_maximum_access_per_week"], "number_of_maximum_access_per_week"),
                )
                for row in tables["07_PROJECT_DETAILS.csv"]
            ),
            lambda item: item.contract_number, errors,
        )
        activities = _unique(
            "08_ACTIVITY_DETAILS.csv",
            (
                Activity(
                    row["activity_id"], row["contract_number"], row["activity_type"], row["start_location_id"],
                    row["end_location_id"], _positive_int(row["total_accesses"], "total_accesses"),
                    _date(row["planned_start_date"]), row["predecessor_activity_id"].strip() or None,
                    _priority(row["activity_priority"]),
                )
                for row in tables["08_ACTIVITY_DETAILS.csv"]
            ),
            lambda item: item.activity_id, errors,
        )
        horizon_start = _date(parameters["horizon_start"])
        horizon_weeks = _positive_int(parameters["horizon_weeks"], "horizon_weeks")
    except (KeyError, ValueError) as error:
        errors.append(str(error))
        raise InstanceValidationError(errors) from error

    instance = Instance(lines, stations, sectors, supply, buffers, horizon_start, horizon_weeks, contracts, activities)
    _validate_references(instance, errors)
    _validate_predecessor_graph(instance, errors)
    if errors:
        raise InstanceValidationError(errors)
    return instance


def _read_csv(name: str, content: bytes, errors: list[str]) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append(f"{name}: file must be UTF-8 encoded.")
        return []
    reader = csv.DictReader(io.StringIO(text, newline=""))
    actual = tuple(reader.fieldnames or ())
    expected = EXPECTED_FILES[name]
    if actual != expected:
        errors.append(f"{name}: expected headers {', '.join(expected)}; received {', '.join(actual)}.")
        return []
    rows = list(reader)
    if not rows:
        errors.append(f"{name}: must include at least one data row.")
    return rows


def _unique(name, items, key, errors):
    result = {}
    for item in items:
        item_key = key(item)
        if item_key in result:
            errors.append(f"{name}: duplicate identifier {item_key}.")
        result[item_key] = item
    return result


def _validate_references(instance: Instance, errors: list[str]) -> None:
    for station in instance.stations.values():
        if station.line_code not in instance.lines:
            errors.append(f"02_STATIONS.csv: {station.station_id} references unknown line {station.line_code}.")
    for sector in instance.sectors.values():
        for station_id in (sector.from_station_id, sector.to_station_id):
            if (sector.line_code, station_id) not in instance.stations:
                errors.append(f"03_SECTORS.csv: {sector.sector_id} references unknown station {station_id}.")
    for location in instance.supply.values():
        if location.line_code not in instance.lines or location.bound not in {"EB", "WB"}:
            errors.append(f"04_LOCATION_SUPPLY.csv: invalid location {location.location_id}.")
    for contract in instance.contracts.values():
        if contract.access_type not in {"PM", "PC", "C"}:
            errors.append(f"07_PROJECT_DETAILS.csv: {contract.contract_number} has invalid access_type.")
        if contract.nature_of_activity not in instance.buffer_rules:
            errors.append(f"07_PROJECT_DETAILS.csv: {contract.contract_number} has no matching buffer rule.")
    for activity in instance.activities.values():
        contract = instance.contracts.get(activity.contract_number)
        if not contract:
            errors.append(f"08_ACTIVITY_DETAILS.csv: {activity.activity_id} references unknown contract.")
            continue
        if activity.activity_type != contract.activity_type:
            errors.append(f"08_ACTIVITY_DETAILS.csv: {activity.activity_id} activity_type differs from its contract.")
        if activity.start_location_id not in instance.supply or activity.end_location_id not in instance.supply:
            errors.append(f"08_ACTIVITY_DETAILS.csv: {activity.activity_id} references an unknown location.")
        if activity.predecessor_activity_id and activity.predecessor_activity_id not in instance.activities:
            errors.append(f"08_ACTIVITY_DETAILS.csv: {activity.activity_id} references an unknown predecessor.")
        if activity.planned_start_date < instance.horizon_start:
            errors.append(f"08_ACTIVITY_DETAILS.csv: {activity.activity_id} starts before the horizon.")


def _validate_predecessor_graph(instance: Instance, errors: list[str]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(activity_id: str, path: list[str]) -> None:
        if activity_id in visited:
            return
        if activity_id in visiting:
            cycle_start = path.index(activity_id)
            cycle = [*path[cycle_start:], activity_id]
            errors.append(f"08_ACTIVITY_DETAILS.csv: predecessor cycle {' -> '.join(cycle)}.")
            return

        visiting.add(activity_id)
        path.append(activity_id)
        predecessor_id = instance.activities[activity_id].predecessor_activity_id
        if predecessor_id in instance.activities:
            visit(predecessor_id, path)
        path.pop()
        visiting.remove(activity_id)
        visited.add(activity_id)

    for activity_id in instance.activities:
        visit(activity_id, [])


def _date(value: str) -> date:
    return date.fromisoformat(value.strip())


def _positive_int(value: str, field: str) -> int:
    result = int(value)
    if result <= 0:
        raise ValueError(f"{field} must be greater than zero.")
    return result


def _nonnegative_int(value: str, field: str) -> int:
    result = int(value)
    if result < 0:
        raise ValueError(f"{field} cannot be negative.")
    return result


def _priority(value: str) -> int:
    result = int(value)
    if result not in {1, 2, 3}:
        raise ValueError("priority must be 1, 2, or 3.")
    return result


def _flag(value: str) -> bool:
    return value.strip() in {"1", "true", "True", "yes", "Yes"}


def _yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"yes", "no", "1", "0", "true", "false"}:
        raise ValueError("opposite_bound_required must be Yes/No or 1/0.")
    return normalized in {"yes", "1", "true"}
