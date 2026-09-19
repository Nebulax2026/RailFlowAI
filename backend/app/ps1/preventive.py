from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time as clock_time, timedelta
from typing import Iterable

from ortools.sat.python import cp_model

from app.ps1.cpu_budget import resolve_workers
from app.ps1.exporter import _csv_bytes, scenario_csvs
from app.ps1.models import (
    MaintenanceAssignment,
    PreventiveMaintenanceOccurrence,
    PreventiveMaintenanceRule,
    PreventiveScenario,
    PreventiveSolution,
    ProjectAccessDetail,
    ValidationReport,
)
from app.ps1.parser import EXPECTED_FILES, InstanceValidationError, parse_instance
from app.ps1.solver import SolveFailure, build_scenario_model
from app.ps1.models import Scenario
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import validate_exported_csvs


MAINTENANCE_FILE = "09_PREVENTIVE_MAINTENANCE.csv"
MAINTENANCE_HEADERS = (
    "rule_id", "location_id", "weekday", "start_time", "end_time",
    "recurrence_start_date", "recurrence_end_date", "max_deferral_days",
)
WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def parse_preventive_instance(files: dict[str, bytes]):
    expected = {*EXPECTED_FILES, MAINTENANCE_FILE}
    missing = sorted(expected - set(files))
    extra = sorted(set(files) - expected)
    errors: list[str] = []
    if missing:
        errors.append(f"Missing files: {', '.join(missing)}")
    if extra:
        errors.append(f"Unexpected files: {', '.join(extra)}")
    if errors:
        raise InstanceValidationError(errors)
    instance = parse_instance({name: files[name] for name in EXPECTED_FILES})
    rules = _parse_maintenance_rules(files[MAINTENANCE_FILE], instance, errors)
    if errors:
        raise InstanceValidationError(errors)
    return instance, rules


def _parse_maintenance_rules(content: bytes, instance, errors: list[str]) -> list[PreventiveMaintenanceRule]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append(f"{MAINTENANCE_FILE}: file must be UTF-8 encoded.")
        return []
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != MAINTENANCE_HEADERS:
        errors.append(f"{MAINTENANCE_FILE}: expected headers {', '.join(MAINTENANCE_HEADERS)}.")
        return []
    try:
        rows = list(reader)
    except csv.Error as error:
        errors.append(f"{MAINTENANCE_FILE}: row {reader.line_num}: {error}")
        return []
    if not rows:
        errors.append(f"{MAINTENANCE_FILE}: must include at least one data row.")
        return []
    seen: set[str] = set()
    rules: list[PreventiveMaintenanceRule] = []
    horizon_end = instance.horizon_start + timedelta(days=instance.horizon_weeks * 7 - 1)
    for number, row in enumerate(rows, 2):
        try:
            if None in row or any(value is None or not value.strip() for value in row.values()):
                raise ValueError("missing value or wrong field count")
            rule_id = row["rule_id"].strip()
            if rule_id in seen:
                raise ValueError(f"duplicate rule_id {rule_id}")
            seen.add(rule_id)
            location_id = row["location_id"].strip()
            if location_id not in instance.supply:
                raise ValueError(f"unknown location_id {location_id}")
            weekday = row["weekday"].strip().upper()
            if weekday not in WEEKDAYS:
                raise ValueError("weekday must be MON, TUE, WED, THU, FRI, SAT, or SUN")
            start_time = _parse_time(row["start_time"].strip())
            end_time = _parse_time(row["end_time"].strip())
            if start_time >= end_time:
                raise ValueError("start_time must be earlier than end_time")
            recurrence_start = date.fromisoformat(row["recurrence_start_date"].strip())
            recurrence_end = date.fromisoformat(row["recurrence_end_date"].strip())
            if recurrence_start > recurrence_end:
                raise ValueError("recurrence dates must be ordered")
            if recurrence_start != instance.horizon_start or recurrence_end != horizon_end:
                raise ValueError("recurrence range must equal the planning horizon")
            max_deferral = int(row["max_deferral_days"])
            if max_deferral < 0:
                raise ValueError("max_deferral_days cannot be negative")
            rules.append(PreventiveMaintenanceRule(
                rule_id, location_id, weekday, row["start_time"].strip(), row["end_time"].strip(),
                recurrence_start, recurrence_end, max_deferral,
            ))
        except (KeyError, ValueError) as error:
            errors.append(f"{MAINTENANCE_FILE}: row {number}: {error}.")
    return rules


def _parse_time(value: str) -> clock_time:
    parsed = datetime.strptime(value, "%H:%M").time()
    if value != parsed.strftime("%H:%M"):
        raise ValueError("time must use HH:MM")
    return parsed


def expand_occurrences(rules: Iterable[PreventiveMaintenanceRule]) -> list[PreventiveMaintenanceOccurrence]:
    occurrences: list[PreventiveMaintenanceOccurrence] = []
    for rule in rules:
        cursor = rule.recurrence_start_date
        cursor += timedelta(days=(WEEKDAYS[rule.weekday] - cursor.weekday()) % 7)
        sequence = 1
        while cursor <= rule.recurrence_end_date:
            occurrences.append(PreventiveMaintenanceOccurrence(
                f"{rule.rule_id}-{sequence:03d}", rule.rule_id, rule.location_id, cursor,
                rule.start_time, rule.end_time, rule.max_deferral_days,
            ))
            sequence += 1
            cursor += timedelta(days=7)
    return sorted(occurrences, key=lambda item: (item.location_id, item.planned_date, item.occurrence_id))


def solve_preventive(instance, rules: list[PreventiveMaintenanceRule], scenario: PreventiveScenario,
                     time_limit_seconds: float = 120, *, workers="auto", seed: int = 42,
                     cancel_event=None) -> PreventiveSolution:
    started = time.monotonic()
    built = build_scenario_model(instance, Scenario.A, time_limit_seconds, started, cancel_event)
    model = built.model
    occurrences = expand_occurrences(rules)
    actual_vars: dict[str, cp_model.IntVar] = {}
    origin = instance.horizon_start

    access_days = {}
    blocked_weekdays = defaultdict(set)
    for rule in rules:
        blocked_weekdays[rule.location_id].add(WEEKDAYS[rule.weekday] + 1)
    for key, selected in built.x.items():
        aid, week = key
        absolute_day = model.NewIntVar((week - 1) * 7, week * 7 - 1, f"absolute_day_{aid}_{week}")
        model.Add(absolute_day == (week - 1) * 7 + built.physical[key] - 1)
        access_days[key] = absolute_day
        if scenario == PreventiveScenario.D:
            for physical_day in sorted({day for location in built.footprint[aid]
                                        for day in blocked_weekdays.get(location, set())}):
                model.Add(built.physical[key] != physical_day).OnlyEnforceIf(selected)

    total_deferral = 0
    max_deferral = 0
    if scenario == PreventiveScenario.E:
        by_location: dict[str, list[tuple[PreventiveMaintenanceOccurrence, cp_model.IntVar]]] = defaultdict(list)
        for occurrence in occurrences:
            planned = (occurrence.planned_date - origin).days
            actual = model.NewIntVar(planned, planned + occurrence.max_deferral_days,
                                     f"maintenance_{occurrence.occurrence_id}")
            actual_vars[occurrence.occurrence_id] = actual
            by_location[occurrence.location_id].append((occurrence, actual))
        for rows in by_location.values():
            for index, (left, left_var) in enumerate(rows):
                left_low = (left.planned_date - origin).days
                left_high = left_low + left.max_deferral_days
                for right, right_var in rows[index + 1:]:
                    right_low = (right.planned_date - origin).days
                    if right_low > left_high:
                        break
                    model.Add(left_var != right_var)
        occurrences_by_location = defaultdict(list)
        for occurrence in occurrences:
            occurrences_by_location[occurrence.location_id].append(occurrence)
        for (aid, week), selected in built.x.items():
            possible_low, possible_high = (week - 1) * 7, week * 7 - 1
            for location in built.footprint[aid]:
                for occurrence in occurrences_by_location.get(location, []):
                    planned = (occurrence.planned_date - origin).days
                    if planned > possible_high or planned + occurrence.max_deferral_days < possible_low:
                        continue
                    model.Add(actual_vars[occurrence.occurrence_id] != access_days[aid, week]).OnlyEnforceIf(selected)
        deferrals = [actual_vars[item.occurrence_id] - (item.planned_date - origin).days for item in occurrences]
        total_deferral = sum(deferrals)
        max_limit = max((item.max_deferral_days for item in occurrences), default=0)
        max_deferral = model.NewIntVar(0, max_limit, "maximum_maintenance_deferral")
        model.AddMaxEquality(max_deferral, deferrals)

    stages = [("project_objective", built.primary)]
    if scenario == PreventiveScenario.E:
        stages.extend([
            ("total_maintenance_deferral", total_deferral),
            ("maximum_maintenance_deferral", max_deferral),
            ("earliness", sum(week * selected for (aid, week), selected in built.x.items()) + sum(actual_vars.values())),
        ])
    solver = None
    stage_results = []
    completed_values = []
    for name, expression in stages:
        remaining = time_limit_seconds - (time.monotonic() - started)
        if remaining <= 0.02:
            break
        model.Minimize(expression)
        candidate = cp_model.CpSolver()
        candidate.parameters.max_time_in_seconds = remaining
        candidate.parameters.num_search_workers = resolve_workers(workers)
        candidate.parameters.random_seed = seed
        status = candidate.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if solver is None:
                reason = "infeasible" if status == cp_model.INFEASIBLE else "time_limit"
                raise SolveFailure(reason, f"Scenario {scenario.value}: {reason}; no complete preventive schedule available.")
            break
        solver = candidate
        value = candidate.Value(expression)
        completed_values.append(value)
        stage_results.append({"name": name, "value": value, "optimal": status == cp_model.OPTIMAL})
        if status != cp_model.OPTIMAL:
            break
        model.Add(expression == value)
    if solver is None:
        raise SolveFailure("time_limit", f"Scenario {scenario.value}: no complete preventive schedule available.")

    project = built.extract(solver)
    project_accesses = []
    for row in project.accesses:
        physical_day = solver.Value(built.physical[row.activity_id, row.week])
        project_accesses.append(ProjectAccessDetail(
            row.activity_id, row.access_seq, row.week, physical_day,
            origin + timedelta(days=(row.week - 1) * 7 + physical_day - 1),
        ))
    maintenance = []
    # ProjectAccessDetail stays location-independent; expand the safety footprint
    # here to identify which maintenance moves were caused by a project conflict.
    occupied = {(location, row.access_date) for row in project_accesses for location in built.footprint[row.activity_id]}
    for occurrence in occurrences:
        actual = occurrence.planned_date if scenario == PreventiveScenario.D else origin + timedelta(
            days=solver.Value(actual_vars[occurrence.occurrence_id]))
        delay = (actual - occurrence.planned_date).days
        maintenance.append(MaintenanceAssignment(
            occurrence.occurrence_id, occurrence.rule_id, occurrence.location_id,
            occurrence.planned_date, actual, occurrence.start_time, occurrence.end_time,
            delay, delay > 0, delay > 0 and (occurrence.location_id, occurrence.planned_date) in occupied,
        ))
    provisional = PreventiveSolution(scenario, project, project_accesses, maintenance,
                                     ValidationReport(scenario.value, False, [], {}, {}))
    files = preventive_solution_files(provisional, include_validation=False)
    validation = validate_preventive_files(instance, rules, scenario, files, stage_results)
    if not validation.feasible:
        raise SolveFailure("validation_failed", str(validation.hard_violations[:3]))
    provisional.validation = validation
    provisional.solver_stats = {
        "elapsed_seconds": time.monotonic() - started,
        "optimal": bool(stage_results) and all(item["optimal"] for item in stage_results),
        "termination_reason": "optimal" if stage_results and all(item["optimal"] for item in stage_results) else "time_limit",
        "objective_hierarchy": stage_results,
        "lexicographic_stages_completed": len(stage_results),
        "search_workers": resolve_workers(workers),
    }
    return provisional


def preventive_solution_files(solution: PreventiveSolution, *, include_validation: bool = True) -> dict[str, bytes]:
    project = solution.project_solution
    files = {
        "SCHEDULE_ACCESS.csv": scenario_csvs(project)["SCHEDULE_ACCESS.csv"],
        "SCHEDULE_OCCUPANCY.csv": scenario_csvs(project)["SCHEDULE_OCCUPANCY.csv"],
        "RESULTS.csv": _csv_bytes(
            ("scenario", "contract_number", "simulated_completion_date", "overrun_days"),
            ([solution.scenario.value, row.contract_number, row.simulated_completion_date.isoformat(), row.overrun_days]
             for row in project.results),
        ),
        "PROJECT_ACCESS_DETAIL.csv": _csv_bytes(
            ("activity_id", "access_seq", "week", "physical_day", "access_date", "start_time", "end_time"),
            ([row.activity_id, row.access_seq, row.week, row.physical_day, row.access_date.isoformat(), row.start_time, row.end_time]
             for row in solution.project_accesses),
        ),
        "MAINTENANCE_SCHEDULE.csv": _csv_bytes(
            ("occurrence_id", "rule_id", "location_id", "planned_date", "actual_date", "start_time", "end_time",
             "deferral_days", "deferred", "conflict_driven"),
            ([row.occurrence_id, row.rule_id, row.location_id, row.planned_date.isoformat(), row.actual_date.isoformat(),
              row.start_time, row.end_time, row.deferral_days, int(row.deferred), int(row.conflict_driven)]
             for row in solution.maintenance),
        ),
    }
    if include_validation:
        files["VALIDATION.json"] = json.dumps(asdict(solution.validation), indent=2, default=str).encode()
    return files


def validate_preventive_files(instance, rules, scenario: PreventiveScenario, files: dict[str, bytes],
                              objective_hierarchy: list[dict] | None = None) -> ValidationReport:
    violations = []
    def fail(rule, detail):
        violations.append({"rule": rule, "severity": "hard", "detail": detail})
    required = {"SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv",
                "PROJECT_ACCESS_DETAIL.csv", "MAINTENANCE_SCHEDULE.csv"}
    if set(files) != required:
        return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": "Expected exactly five preventive result CSV files."}], {}, {})
    try:
        results_reader = csv.DictReader(io.StringIO(files["RESULTS.csv"].decode("utf-8-sig")), strict=True)
        if tuple(results_reader.fieldnames or ()) != ("scenario", "contract_number", "simulated_completion_date", "overrun_days"):
            raise ValueError("Invalid headers in RESULTS.csv.")
        result_rows = list(results_reader)
        if any(row["scenario"] != scenario.value for row in result_rows):
            fail("scenario", f"RESULTS.csv must identify Scenario {scenario.value}.")
        normalized_results = _csv_bytes(
            ("scenario", "contract_number", "simulated_completion_date", "overrun_days"),
            ([Scenario.A.value, row["contract_number"], row["simulated_completion_date"], row["overrun_days"]]
             for row in result_rows),
        )
    except (UnicodeError, csv.Error, ValueError, KeyError) as error:
        return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": str(error)}], {}, {})
    project_report = validate_exported_csvs(instance, Scenario.A, {
        "SCHEDULE_ACCESS.csv": files["SCHEDULE_ACCESS.csv"],
        "SCHEDULE_OCCUPANCY.csv": files["SCHEDULE_OCCUPANCY.csv"],
        "RESULTS.csv": normalized_results,
    })
    if not project_report.feasible:
        violations.extend(project_report.hard_violations)
    try:
        detail_reader = csv.DictReader(io.StringIO(files["PROJECT_ACCESS_DETAIL.csv"].decode("utf-8-sig")), strict=True)
        expected_detail = ("activity_id", "access_seq", "week", "physical_day", "access_date", "start_time", "end_time")
        if tuple(detail_reader.fieldnames or ()) != expected_detail:
            raise ValueError("Invalid headers in PROJECT_ACCESS_DETAIL.csv.")
        details = list(detail_reader)
        maintenance_reader = csv.DictReader(io.StringIO(files["MAINTENANCE_SCHEDULE.csv"].decode("utf-8-sig")), strict=True)
        expected_maintenance = ("occurrence_id", "rule_id", "location_id", "planned_date", "actual_date", "start_time", "end_time",
                                "deferral_days", "deferred", "conflict_driven")
        if tuple(maintenance_reader.fieldnames or ()) != expected_maintenance:
            raise ValueError("Invalid headers in MAINTENANCE_SCHEDULE.csv.")
        maintenance_rows = list(maintenance_reader)
    except (UnicodeError, csv.Error, ValueError) as error:
        return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": str(error)}], {}, {})

    official_access_reader = csv.DictReader(io.StringIO(files["SCHEDULE_ACCESS.csv"].decode("utf-8-sig")))
    official_rows = list(official_access_reader)
    official_keys = {(row["activity_id"], int(row["access_seq"]), int(row["week"])) for row in official_rows}
    official_by_key = {(row["activity_id"], int(row["access_seq"]), int(row["week"])): int(row["access_night"])
                       for row in official_rows}
    access_keys = set()
    occupied = set()
    local_to_physical = defaultdict(set)
    mapping_groups = defaultdict(dict)
    for number, row in enumerate(details, 2):
        try:
            aid, seq, week = row["activity_id"], int(row["access_seq"]), int(row["week"])
            physical = int(row["physical_day"])
            actual_date = date.fromisoformat(row["access_date"])
            key = (aid, seq, week)
            if key in access_keys:
                fail("project_access", f"Duplicate project detail {key}.")
            access_keys.add(key)
            if aid not in instance.activities or not 1 <= physical <= 7:
                fail("project_access", f"Row {number}: invalid activity or physical day.")
                continue
            expected_date = instance.horizon_start + timedelta(days=(week - 1) * 7 + physical - 1)
            if actual_date != expected_date:
                fail("project_access", f"{aid} week {week}: physical day/date mismatch.")
            if row["start_time"] != "01:00" or row["end_time"] != "04:00":
                fail("project_time", f"{aid}: project window must be 01:00-04:00.")
            if key not in official_by_key:
                fail("project_access", f"{aid}: detail row is absent from SCHEDULE_ACCESS.csv.")
            else:
                activity = instance.activities[aid]
                contract = instance.contracts[activity.contract_number]
                local_night = official_by_key[key]
                mapping_key = (activity.contract_number, activity.activity_type, week, local_night)
                local_to_physical[mapping_key].add(physical)
                mapping_groups[(activity.contract_number, activity.activity_type, week)][local_night] = physical
            footprint = set(activity_locations(instance, instance.activities[aid])) | closure_locations(instance, instance.activities[aid])
            occupied.update((location, actual_date) for location in footprint)
        except (KeyError, ValueError) as error:
            fail("project_access", f"Row {number}: {error}.")
    if access_keys != official_keys:
        fail("project_access", "Project access detail does not match SCHEDULE_ACCESS.csv.")
    for key, values in local_to_physical.items():
        if len(values) != 1:
            fail("physical_night", f"Local access night {key} maps to multiple physical days.")
    for key, values in mapping_groups.items():
        if len(set(values.values())) != len(values):
            fail("physical_night", f"Distinct local access nights for {key} map to the same physical day.")

    expected_occurrences = {item.occurrence_id: item for item in expand_occurrences(rules)}
    seen = set()
    by_location_date = set()
    total_delay = 0
    max_delay = 0
    on_time = 0
    conflict_driven = 0
    for number, row in enumerate(maintenance_rows, 2):
        try:
            occurrence_id = row["occurrence_id"]
            if occurrence_id in seen:
                fail("maintenance", f"Duplicate occurrence {occurrence_id}.")
                continue
            seen.add(occurrence_id)
            expected = expected_occurrences.get(occurrence_id)
            if not expected:
                fail("maintenance", f"Unknown occurrence {occurrence_id}.")
                continue
            planned, actual = date.fromisoformat(row["planned_date"]), date.fromisoformat(row["actual_date"])
            delay = int(row["deferral_days"])
            if (row["rule_id"], row["location_id"], planned, row["start_time"], row["end_time"]) != (
                    expected.rule_id, expected.location_id, expected.planned_date, expected.start_time, expected.end_time):
                fail("maintenance", f"{occurrence_id}: rule fields differ from the dataset.")
            if row["start_time"] != "01:00" or row["end_time"] != "04:00":
                fail("maintenance_time", f"{occurrence_id}: maintenance window must be 01:00-04:00.")
            if delay != (actual - planned).days or delay < 0 or delay > expected.max_deferral_days:
                fail("maintenance_deferral", f"{occurrence_id}: invalid deferral {delay}.")
            deferred_flag = int(row["deferred"])
            conflict_flag = int(row["conflict_driven"])
            if deferred_flag not in (0, 1) or deferred_flag != int(delay > 0):
                fail("maintenance_deferral", f"{occurrence_id}: deferred flag disagrees with the dates.")
            expected_conflict = int(delay > 0 and (expected.location_id, planned) in occupied)
            if conflict_flag not in (0, 1) or conflict_flag != expected_conflict:
                fail("maintenance_deferral", f"{occurrence_id}: conflict_driven flag is not supported by project evidence.")
            if scenario == PreventiveScenario.D and delay != 0:
                fail("maintenance_priority", f"{occurrence_id}: D requires the planned date.")
            if (expected.location_id, actual) in by_location_date:
                fail("maintenance_overlap", f"{expected.location_id} {actual}: maintenance occurrences overlap.")
            by_location_date.add((expected.location_id, actual))
            if (expected.location_id, actual) in occupied:
                fail("project_maintenance_overlap", f"{expected.location_id} {actual}: project and maintenance overlap.")
            total_delay += delay
            max_delay = max(max_delay, delay)
            on_time += delay == 0
            conflict_driven += conflict_flag
        except (KeyError, ValueError) as error:
            fail("maintenance", f"Row {number}: {error}.")
    for occurrence_id in sorted(set(expected_occurrences) - seen):
        fail("maintenance", f"Missing occurrence {occurrence_id}.")
    if scenario == PreventiveScenario.E:
        hierarchy = objective_hierarchy or []
        if not hierarchy or hierarchy[0].get("name") != "project_objective":
            fail("objective_hierarchy", "E must optimize the project objective before maintenance deferral.")

    project_scores = project_report.soft_scores
    scores = {
        "project_objective_score": project_scores.get("objective_score"),
        "priority_weighted_project_delay": project_scores.get("priority_weighted_score"),
        "total_project_overrun_days": project_scores.get("overrun_days_total"),
        "contracts_overrunning": project_scores.get("contracts_overrunning"),
        "maintenance_occurrence_count": len(maintenance_rows),
        "on_time_maintenance_count": on_time,
        "deferred_maintenance_count": len(maintenance_rows) - on_time,
        "total_maintenance_deferral_days": total_delay,
        "average_maintenance_deferral_days": round(total_delay / max(1, len(maintenance_rows)), 3),
        "maximum_maintenance_deferral_days": max_delay,
        "conflict_driven_deferrals": conflict_driven,
    }
    return ValidationReport(scenario.value, not violations, violations, scores, {
        "safety_status": project_report.detail.get("safety_status"),
        "objective_hierarchy": objective_hierarchy or [],
        "experimental": True,
    })


def preventive_tradeoff(d: PreventiveSolution, e: PreventiveSolution) -> dict:
    if not d.validation.feasible or not e.validation.feasible:
        raise ValueError("Both preventive scenarios must be independently validated.")
    ds, es = d.validation.soft_scores, e.validation.soft_scores
    metrics = {}
    names = (
        "project_objective_score", "total_project_overrun_days", "priority_weighted_project_delay",
        "contracts_overrunning", "maintenance_occurrence_count", "on_time_maintenance_count",
        "deferred_maintenance_count", "total_maintenance_deferral_days",
        "average_maintenance_deferral_days", "maximum_maintenance_deferral_days",
    )
    for name in names:
        metrics[name] = {"D": ds.get(name), "E": es.get(name),
                         "delta_E_minus_D": None if ds.get(name) is None or es.get(name) is None else es[name] - ds[name]}
    d_access = {(row.activity_id, row.week, row.physical_day) for row in d.project_accesses}
    e_access = {(row.activity_id, row.week, row.physical_day) for row in e.project_accesses}
    moved = len(d_access ^ e_access) // 2
    metrics["project_accesses_moved"] = {"D": 0, "E": moved, "delta_E_minus_D": moved}
    metrics["solver_elapsed_seconds"] = {"D": d.solver_stats.get("elapsed_seconds"), "E": e.solver_stats.get("elapsed_seconds"),
                                         "delta_E_minus_D": (e.solver_stats.get("elapsed_seconds", 0) - d.solver_stats.get("elapsed_seconds", 0))}
    project_delta = metrics["project_objective_score"]["delta_E_minus_D"]
    delay_delta = metrics["total_maintenance_deferral_days"]["delta_E_minus_D"]
    project_summary = ("The validated project objective is unchanged." if project_delta == 0 else
                       f"Scenario E changes the project objective by {project_delta:+g} versus D.")
    maintenance_summary = ("Both policies keep every maintenance occurrence on time." if delay_delta == 0 else
                           f"Scenario E adds {delay_delta:g} total maintenance deferral days versus D.")
    d_project_rows = {(row.activity_id, row.access_seq): row for row in d.project_accesses}
    e_project_rows = {(row.activity_id, row.access_seq): row for row in e.project_accesses}
    project_differences = []
    for key in sorted(d_project_rows.keys() & e_project_rows.keys()):
        left, right = d_project_rows[key], e_project_rows[key]
        if (left.week, left.physical_day, left.access_date) == (right.week, right.physical_day, right.access_date):
            continue
        project_differences.append({
            "activity_id": key[0], "access_seq": key[1],
            "D": {"week": left.week, "physical_day": left.physical_day, "access_date": left.access_date.isoformat()},
            "E": {"week": right.week, "physical_day": right.physical_day, "access_date": right.access_date.isoformat()},
            "moved_days_E_minus_D": (right.access_date - left.access_date).days,
        })
    d_maintenance_rows = {row.occurrence_id: row for row in d.maintenance}
    e_maintenance_rows = {row.occurrence_id: row for row in e.maintenance}
    maintenance_differences = []
    for occurrence_id in sorted(d_maintenance_rows.keys() & e_maintenance_rows.keys()):
        left, right = d_maintenance_rows[occurrence_id], e_maintenance_rows[occurrence_id]
        if left.actual_date == right.actual_date:
            continue
        maintenance_differences.append({
            "occurrence_id": occurrence_id, "location_id": left.location_id,
            "planned_date": left.planned_date.isoformat(),
            "D": {"actual_date": left.actual_date.isoformat(), "deferral_days": left.deferral_days},
            "E": {"actual_date": right.actual_date.isoformat(), "deferral_days": right.deferral_days},
            "moved_days_E_minus_D": (right.actual_date - left.actual_date).days,
        })
    return {
        "title": "Scenario D vs E Trade-off",
        "metrics": metrics,
        "project_schedule_impact": project_summary,
        "preventive_maintenance_impact": maintenance_summary,
        "summary": f"{project_summary} {maintenance_summary} D protects planned maintenance windows; E protects the project objective first.",
        "optimality_proved": {"D": bool(d.solver_stats.get("optimal")), "E": bool(e.solver_stats.get("optimal"))},
        "schedule_difference_summary": {
            "project_accesses_changed": len(project_differences),
            "maintenance_occurrences_changed": len(maintenance_differences),
        },
        "project_schedule_differences": project_differences,
        "maintenance_schedule_differences": maintenance_differences,
    }


def preventive_zip(solutions: list[PreventiveSolution]) -> bytes:
    stream = io.BytesIO()
    by_scenario = {item.scenario: item for item in solutions}
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for solution in solutions:
            for filename, content in preventive_solution_files(solution).items():
                archive.writestr(f"scenario_{solution.scenario.value}/{filename}", content)
        if PreventiveScenario.D in by_scenario and PreventiveScenario.E in by_scenario:
            archive.writestr("TRADEOFF.json", json.dumps(preventive_tradeoff(
                by_scenario[PreventiveScenario.D], by_scenario[PreventiveScenario.E]), indent=2).encode())
        archive.writestr("manifest.json", json.dumps({"job_kind": "preventive", "experimental": True,
            "included_scenarios": [item.scenario.value for item in solutions]}, indent=2).encode())
    return stream.getvalue()
