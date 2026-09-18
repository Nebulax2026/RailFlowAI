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
                               _nonnegative_int(row["supply_capacity"], "supply_capacity"))
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
        if len(parameters) != len(tables["06_PARAMETERS.csv"]):
            errors.append("06_PARAMETERS.csv: field key: duplicate parameter.")
        for key in ("horizon_start", "horizon_weeks"):
            if key not in parameters: errors.append(f"06_PARAMETERS.csv: field key: missing {key}.")
        if errors: raise InstanceValidationError(errors)
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
    _validate_topology(instance, errors)
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
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    actual = tuple(reader.fieldnames or ())
    expected = EXPECTED_FILES[name]
    if actual != expected:
        errors.append(f"{name}: expected headers {', '.join(expected)}; received {', '.join(actual)}.")
        return []
    try:
        rows = list(reader)
    except csv.Error as error:
        errors.append(f"{name}: row {reader.line_num}: {error}")
        return []
    integer_fields = {"seq", "supply_capacity", "up_to_buffer_sectors", "contract_priority", "activity_priority", "number_of_workfronts", "number_of_maximum_access_per_week", "total_accesses"}
    enums = {"bound": {"EB", "WB"}, "access_type": {"PM", "PC", "C"},
             "location_kind": {"tunnel sector", "platform sector"},
             "nature_of_works": {"Live", "Non-live (Consist)", "Non-live (Others)"},
             "nature_of_activity": {"Live", "Non-live (Consist)", "Non-live (Others)"}}
    for number, row in enumerate(rows, 2):
        if None in row or any(v is None for v in row.values()):
            errors.append(f"{name}: row {number}: field count differs from header.")
            continue
        for field, value in row.items():
            try:
                if not value.strip() and field != "predecessor_activity_id":
                    raise ValueError("required value is empty")
                if field in integer_fields:
                    (_nonnegative_int if field in {"supply_capacity", "up_to_buffer_sectors"} else _positive_int)(value, field)
                if field in {"contract_priority", "activity_priority"}:
                    _priority(value)
                if field.endswith("_date"):
                    _date(value)
                if field in {"is_interchange", "is_shared", "opposite_bound_required"}:
                    _yes_no(value)
                if field in enums and value not in enums[field]:
                    raise ValueError("unrecognised value")
                if name == "06_PARAMETERS.csv" and field == "value":
                    if row["key"] == "horizon_start": _date(value)
                    elif row["key"] == "horizon_weeks": _positive_int(value, field)
            except ValueError as error:
                errors.append(f"{name}: row {number}: field {field}: {error}")
    if not rows:
        errors.append(f"{name}: must include at least one data row.")
    return rows


def _unique(name, items, key, errors):
    result = {}
    for number, item in enumerate(items, 2):
        item_key = key(item)
        if item_key in result:
            errors.append(f"{name}: row {number}: field identifier: duplicate {item_key}.")
        result[item_key] = item
    return result


def _validate_references(instance: Instance, errors: list[str]) -> None:
    def error(file, row, field, detail):
        errors.append(f"{file}: row {row}: field {field}: {detail}")

    for number, station in enumerate(instance.stations.values(), 2):
        if station.line_code not in instance.lines:
            error("02_STATIONS.csv", number, "line_code", f"unknown line for {station.station_id}.")
    for number, sector in enumerate(instance.sectors.values(), 2):
        for field, station_id in (("from_station_id", sector.from_station_id), ("to_station_id", sector.to_station_id)):
            if (sector.line_code, station_id) not in instance.stations:
                error("03_SECTORS.csv", number, field, f"unknown station {station_id}.")
    for number, location in enumerate(instance.supply.values(), 2):
        if location.line_code not in instance.lines or location.bound not in {"EB", "WB"}:
            error("04_LOCATION_SUPPLY.csv", number, "line_code/bound", f"invalid location {location.location_id}.")
    active_contracts = {a.contract_number for a in instance.activities.values()}
    for number, contract in enumerate(instance.contracts.values(), 2):
        if contract.access_type not in {"PM", "PC", "C"}:
            error("07_PROJECT_DETAILS.csv", number, "access_type", "expected PM, PC or C.")
        if contract.nature_of_activity not in instance.buffer_rules:
            error("07_PROJECT_DETAILS.csv", number, "nature_of_activity", "no matching buffer rule.")
        if contract.contract_number not in active_contracts:
            error("07_PROJECT_DETAILS.csv", number, "contract_number", "no activities to compute completion from.")
    for number, activity in enumerate(instance.activities.values(), 2):
        contract = instance.contracts.get(activity.contract_number)
        if not contract:
            error("08_ACTIVITY_DETAILS.csv", number, "contract_number", "unknown contract.")
            continue
        if activity.activity_type != contract.activity_type:
            error("08_ACTIVITY_DETAILS.csv", number, "activity_type", "differs from its contract.")
        for field, location in (("start_location_id", activity.start_location_id), ("end_location_id", activity.end_location_id)):
            if location not in instance.supply:
                error("08_ACTIVITY_DETAILS.csv", number, field, "unknown location.")
        if activity.predecessor_activity_id and activity.predecessor_activity_id not in instance.activities:
            error("08_ACTIVITY_DETAILS.csv", number, "predecessor_activity_id", "unknown predecessor.")
        if activity.planned_start_date < instance.horizon_start:
            error("08_ACTIVITY_DETAILS.csv", number, "planned_start_date", "starts before the horizon.")


def _validate_predecessor_graph(instance: Instance, errors: list[str]) -> None:
    visited = set()
    for first in instance.activities:
        path = []
        position = {}
        current = first
        while current in instance.activities and current not in visited:
            if current in position:
                cycle = path[position[current]:] + [current]
                errors.append(f"08_ACTIVITY_DETAILS.csv: field predecessor_activity_id: predecessor cycle {' -> '.join(cycle)}.")
                break
            position[current] = len(path)
            path.append(current)
            current = instance.activities[current].predecessor_activity_id
        visited.update(path)


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
    return _yes_no(value)


def _validate_topology(instance: Instance, errors: list[str]) -> None:
    from app.ps1.topology import activity_locations
    for line in instance.lines:
        stations = sorted((s for s in instance.stations.values() if s.line_code == line), key=lambda s: s.seq)
        sectors = sorted((s for s in instance.sectors.values() if s.line_code == line), key=lambda s: s.seq)
        if not stations or [s.seq for s in stations] != list(range(1, len(stations) + 1)):
            errors.append(f"02_STATIONS.csv: field seq: {line} must have contiguous unique station order.")
        if len(sectors) != len(stations) - 1 or (sectors and [s.seq for s in sectors] != list(range(sectors[0].seq, sectors[0].seq + len(sectors)))):
            errors.append(f"03_SECTORS.csv: field seq: {line} must connect consecutive stations.")
        for n, sector in enumerate(sectors):
            if n + 1 >= len(stations) or (sector.from_station_id, sector.to_station_id) != (stations[n].station_id, stations[n + 1].station_id):
                errors.append(f"03_SECTORS.csv: field from_station_id/to_station_id: disconnected sector {sector.sector_id}.")
        expected = {f"PLAT:{line}:{s.station_id}:{bound}": "platform sector" for s in stations for bound in ("EB", "WB")}
        expected.update({f"{s.sector_id}:{bound}": "tunnel sector" for s in sectors for bound in ("EB", "WB")})
        for location, kind in expected.items():
            entry = instance.supply.get(location)
            if not entry or entry.location_kind != kind or entry.line_code != line or entry.bound != location.rsplit(":", 1)[1]:
                errors.append(f"04_LOCATION_SUPPLY.csv: field location_id/location_kind: invalid or missing {location}.")
        for entry in instance.supply.values():
            if entry.line_code == line and entry.location_id not in expected:
                errors.append(f"04_LOCATION_SUPPLY.csv: field location_id: unknown topology location {entry.location_id}.")
    for number, activity in enumerate(instance.activities.values(), 2):
        try:
            activity_locations(instance, activity)
        except (KeyError, ValueError) as error:
            errors.append(f"08_ACTIVITY_DETAILS.csv: row {number}: field start_location_id/end_location_id: {error}")


def _yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"yes", "no", "1", "0", "true", "false"}:
        raise ValueError("opposite_bound_required must be Yes/No or 1/0.")
    return normalized in {"yes", "1", "true"}
