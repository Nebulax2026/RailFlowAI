from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, timedelta

from app.ps1.models import AccessAssignment, ContractResult, Instance, OccupancyAssignment, Scenario, ValidationReport
from app.ps1.topology import activity_locations

OUTPUT_HEADERS = {
    "SCHEDULE_ACCESS.csv": ("activity_id", "access_seq", "week", "eclo", "access_night"),
    "SCHEDULE_OCCUPANCY.csv": ("activity_id", "week", "location_id", "co_share_group"),
    "RESULTS.csv": ("scenario", "contract_number", "simulated_completion_date", "overrun_days"),
}


def validate_exported_csvs(instance: Instance, scenario: Scenario, files: dict[str, bytes]) -> ValidationReport:
    rows = {}
    for filename, headers in OUTPUT_HEADERS.items():
        if filename not in files:
            return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": f"Missing {filename}."}], {}, {})
        reader = csv.DictReader(io.StringIO(files[filename].decode("utf-8-sig")))
        if tuple(reader.fieldnames or ()) != headers:
            return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": f"Invalid headers in {filename}."}], {}, {})
        rows[filename] = list(reader)
    try:
        accesses = [AccessAssignment(row["activity_id"], int(row["access_seq"]), int(row["week"]), int(row["eclo"]), int(row["access_night"])) for row in rows["SCHEDULE_ACCESS.csv"]]
        occupancy = [OccupancyAssignment(row["activity_id"], int(row["week"]), row["location_id"], row["co_share_group"]) for row in rows["SCHEDULE_OCCUPANCY.csv"]]
        results = [ContractResult(row["scenario"], row["contract_number"], date.fromisoformat(row["simulated_completion_date"]), int(row["overrun_days"])) for row in rows["RESULTS.csv"]]
    except (KeyError, ValueError) as error:
        return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": f"Output parse error: {error}."}], {}, {})
    mixed = sorted({item.scenario for item in results})
    if mixed != [scenario.value]:
        return ValidationReport(scenario.value, False, [{"rule": "scenario", "severity": "hard", "detail": "RESULTS.csv must contain exactly one matching scenario."}], {}, {})
    return validate_solution(instance, scenario, accesses, occupancy, results)


def validate_solution(
    instance: Instance,
    scenario: Scenario,
    accesses: list[AccessAssignment],
    occupancy: list[OccupancyAssignment],
    results: list[ContractResult],
) -> ValidationReport:
    violations: list[dict[str, str]] = []
    by_activity = defaultdict(list)
    for access in accesses:
        by_activity[access.activity_id].append(access)
        if access.week < 1 or access.week > instance.horizon_weeks:
            _violate(violations, "horizon", f"{access.activity_id} uses invalid week {access.week}.")
        if scenario == Scenario.A and access.eclo:
            _violate(violations, "eclo", f"{access.activity_id} uses ECLO in Scenario A.")

    for activity in instance.activities.values():
        rows = by_activity[activity.activity_id]
        workload = sum(1.5 if row.eclo else 1 for row in rows)
        if workload != activity.total_accesses:
            _violate(violations, "workload", f"{activity.activity_id} has {workload} of {activity.total_accesses} accesses.")
        weeks = [row.week for row in rows]
        if len(weeks) != len(set(weeks)):
            _violate(violations, "weekly_activity", f"{activity.activity_id} has multiple accesses in one week.")
        earliest_week = max(1, ((activity.planned_start_date - instance.horizon_start).days // 7) + 1)
        if weeks and min(weeks) < earliest_week:
            _violate(violations, "planned_start", f"{activity.activity_id} starts before week {earliest_week}.")
        if activity.predecessor_activity_id and by_activity[activity.predecessor_activity_id] and rows:
            if max(item.week for item in by_activity[activity.predecessor_activity_id]) >= min(item.week for item in rows):
                _violate(violations, "predecessor", f"{activity.activity_id} overlaps predecessor {activity.predecessor_activity_id}.")

    contract_nights = defaultdict(set)
    workfronts = Counter()
    for access in accesses:
        activity = instance.activities.get(access.activity_id)
        if not activity:
            _violate(violations, "activity", f"Unknown activity {access.activity_id}.")
            continue
        contract = instance.contracts[activity.contract_number]
        if not 1 <= access.access_night <= contract.number_of_maximum_access_per_week:
            _violate(violations, "weekly_allocation", f"{activity.activity_id} uses invalid access night {access.access_night}.")
        contract_nights[(contract.contract_number, activity.activity_type, access.week)].add(access.access_night)
        workfronts[(contract.contract_number, activity.activity_type, access.week, access.access_night)] += 1
    for key, nights in contract_nights.items():
        contract = instance.contracts[key[0]]
        if len(nights) > contract.number_of_maximum_access_per_week:
            _violate(violations, "weekly_allocation", f"{key} exceeds weekly night allocation.")
    for key, count in workfronts.items():
        contract = instance.contracts[key[0]]
        if count > contract.number_of_workfronts:
            _violate(violations, "workfront", f"{key} uses {count} workfronts, maximum {contract.number_of_workfronts}.")

    expected_occupancy = {
        (access.activity_id, access.week, location)
        for access in accesses
        for location in activity_locations(instance, instance.activities[access.activity_id])
    }
    actual_occupancy = {(row.activity_id, row.week, row.location_id) for row in occupancy}
    for missing in sorted(expected_occupancy - actual_occupancy):
        _violate(violations, "occupancy", f"Missing occupancy {missing}.")
    for extra in sorted(actual_occupancy - expected_occupancy):
        _violate(violations, "occupancy", f"Unexpected occupancy {extra}.")

    group_slots = defaultdict(set)
    for row in occupancy:
        group_slots[(row.location_id, row.week)].add(row.co_share_group)
    excess_total = 0
    hotspots = []
    for (location, week), groups in sorted(group_slots.items()):
        nominal = instance.supply[location].supply_capacity
        excess = max(0, len(groups) - nominal)
        excess_total += excess
        if len(groups) >= nominal:
            hotspots.append({"location_id": location, "week": week, "used": len(groups), "capacity": nominal})
        if scenario == Scenario.A and excess:
            _violate(violations, "capacity", f"{location} week {week} exceeds capacity by {excess}.")
        if scenario == Scenario.C and excess > 1:
            _violate(violations, "capacity", f"{location} week {week} exceeds Scenario C allowance.")

    result_by_contract = {item.contract_number: item for item in results}
    for contract in instance.contracts.values():
        result = result_by_contract.get(contract.contract_number)
        if not result:
            _violate(violations, "results", f"Missing result for {contract.contract_number}.")
        elif scenario == Scenario.B and result.overrun_days > 0:
            _violate(violations, "planned_date", f"{contract.contract_number} overruns by {result.overrun_days} days.")

    eclo_total = sum(row.eclo for row in accesses)
    if scenario == Scenario.C and eclo_total:
        for line_code in instance.lines:
            eclo_weeks = []
            for access in accesses:
                if not access.eclo:
                    continue
                activity = instance.activities[access.activity_id]
                work_line = instance.supply[activity.start_location_id].line_code
                contract = instance.contracts[activity.contract_number]
                cross_line_live = contract.nature_of_activity == "Live" and any("H01_H02" in location for location in activity_locations(instance, activity))
                if work_line == line_code or cross_line_live:
                    eclo_weeks.append(access.week)
            if eclo_weeks and max(eclo_weeks) - min(eclo_weeks) + 1 > 2:
                _violate(violations, "eclo_continuity", f"{line_code} ECLO use spans more than two calendar weeks.")
    overrun_total = sum(item.overrun_days for item in results)
    priority_overrun = {str(priority): 0 for priority in (1, 2, 3)}
    weighted = 0.0
    for result in results:
        contract = instance.contracts[result.contract_number]
        priority_overrun[str(contract.contract_priority)] += result.overrun_days
    activity_nudges = {1: 1.3, 2: 1.2, 3: 1.0}
    for activity in instance.activities.values():
        rows = by_activity[activity.activity_id]
        if not rows:
            continue
        completion_date = instance.horizon_start + timedelta(days=max(item.week for item in rows) * 7 - 1)
        contract = instance.contracts[activity.contract_number]
        activity_overrun = max(0, (completion_date - contract.planned_completion_date).days)
        weight = {1: 100, 2: 10, 3: 1}[contract.contract_priority]
        weighted += weight * activity_nudges[activity.activity_priority] * activity_overrun
    objective = (0 if scenario == Scenario.B else weighted) + (0 if scenario == Scenario.A else 7 * excess_total + 5 * eclo_total)
    scores = {
        "objective_score": objective,
        "overrun_days_total": overrun_total,
        "contracts_overrunning": sum(item.overrun_days > 0 for item in results),
        "excess_access_nights_total": excess_total,
        "eclo_nights_total": eclo_total,
        "priority_overrun": priority_overrun,
        "priority_weighted_score": weighted,
        "formula_version": "ps1-2026-v1",
    }
    return ValidationReport(
        scenario.value,
        not violations,
        violations,
        scores,
        {"capacity_hotspots": hotspots[:100], "nights_scheduled": len(accesses), "eclo_nights": eclo_total},
    )


def _violate(violations: list[dict[str, str]], rule: str, detail: str) -> None:
    violations.append({"rule": rule, "severity": "hard", "detail": detail})
