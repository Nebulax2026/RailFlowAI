import hashlib
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import ps1 as api
from app.ps1 import jobs
from app.ps1.jobs import JobManager
from app.ps1.models import PreventiveMaintenanceRule, PreventiveScenario
from app.ps1.parser import EXPECTED_FILES, InstanceValidationError
from app.ps1.preventive import (
    MAINTENANCE_FILE,
    parse_preventive_instance,
    preventive_solution_files,
    preventive_tradeoff,
    solve_preventive,
    validate_preventive_files,
)
from app.ps1.topology import activity_locations
from .test_regressions import tiny
from .test_ps1 import instance
from .test_platform_endpoints import tiny as topology_instance


ROOT = Path(__file__).resolve().parents[2]
STANDARD_DATA = ROOT / "PS1" / "01_data"
PREVENTIVE_DATA = ROOT / "PS1" / "01_data_preventive"
TRADEOFF_DATA = ROOT / "PS1" / "01_data_preventive_tradeoff"
ORIGINAL_HASHES = {
    "01_LINES.csv": "b6e60b0e7726e4266efd059bf5061b3b3a2c9825ae7dd85a6431f41b81b383e7",
    "02_STATIONS.csv": "4a27d6508defd03e8c833133b523390ac8850a1c1717f309033e40f364720e24",
    "03_SECTORS.csv": "643fdb2bd317126b42572fafcce8f8108008e8e9c7b71c08dfd31cec11c3ee34",
    "04_LOCATION_SUPPLY.csv": "9d8a92d6ffd340f40dae28302ed6f88958f8661e2b046bb6b4e0b79c385be1e6",
    "05_BUFFER_LOCATION.csv": "4b9fe7fd6a1f9128bd6e83405496dc64a8028f997bb1fcd28355582a6d554de0",
    "06_PARAMETERS.csv": "9400b7b082069c56b8cae85d56994cf06fe08ae54fcd116ff6edc890034cc8e6",
    "07_PROJECT_DETAILS.csv": "393f0dcc7e7b9a54f0eff12eb0dd0122dbd74f4b4b8b73b7676f9f232fb8a4c7",
    "08_ACTIVITY_DETAILS.csv": "6a1ef90cd3bed93a8970ef49454e9c02e0c1df93ce8e0f0f4b071563cfb43e30",
}


def public_files():
    return {name: (PREVENTIVE_DATA / name).read_bytes() for name in (*EXPECTED_FILES, MAINTENANCE_FILE)}


def rules_for(instance, weekdays=("FRI", "SAT", "SUN")):
    end = instance.horizon_start + timedelta(days=instance.horizon_weeks * 7 - 1)
    return [PreventiveMaintenanceRule(f"R-{index}-{weekday}", location, weekday, "01:00", "04:00",
                                      instance.horizon_start, end, 7)
            for index, location in enumerate(sorted(instance.supply), 1) for weekday in weekdays]


def test_original_public_dataset_is_byte_stable_and_copied():
    for name, expected in ORIGINAL_HASHES.items():
        original = (STANDARD_DATA / name).read_bytes()
        assert hashlib.sha256(original).hexdigest() == expected
        assert (PREVENTIVE_DATA / name).read_bytes() == original


def test_preventive_parser_and_diagnostics():
    instance, rules = parse_preventive_instance(public_files())
    assert len(rules) == len(instance.supply) * 3
    assert {rule.weekday for rule in rules} == {"FRI", "SAT", "SUN"}
    broken = public_files()
    broken[MAINTENANCE_FILE] = broken[MAINTENANCE_FILE].replace(b",FRI,01:00,", b",XXX,01:00,", 1)
    with pytest.raises(InstanceValidationError, match="weekday"):
        parse_preventive_instance(broken)


def test_tradeoff_dataset_adds_only_the_documented_demo_demand():
    files = {name: (TRADEOFF_DATA / name).read_bytes() for name in (*EXPECTED_FILES, MAINTENANCE_FILE)}
    instance, rules = parse_preventive_instance(files)
    assert len(instance.contracts) == 15
    assert len(instance.activities) == 59
    assert sum(item.total_accesses for item in instance.activities.values()) == 197
    assert set(instance.activities) >= {"PMD01", "PMD02", "PMD03", "PMD04", "PMD05"}
    assert len(rules) == len(instance.supply) * 3
    for name in ("01_LINES.csv", "02_STATIONS.csv", "03_SECTORS.csv", "04_LOCATION_SUPPLY.csv",
                 "05_BUFFER_LOCATION.csv", "06_PARAMETERS.csv", MAINTENANCE_FILE):
        assert (TRADEOFF_DATA / name).read_bytes() == (PREVENTIVE_DATA / name).read_bytes()


def test_standard_and_preventive_jobs_have_disjoint_scenario_sets(tiny, monkeypatch):
    manager = JobManager()
    manager._executor.shutdown()
    manager._executor = SimpleNamespace(submit=lambda *args: None)
    monkeypatch.setattr(jobs, "parse_instance", lambda _: tiny)
    standard = manager.create({}, "test")
    assert {scenario.value for scenario in standard.scenarios} == {"A", "B", "C"}
    preventive = manager.create_preventive_public(time_limit_seconds=5)
    assert preventive.job_kind.value == "preventive"
    assert preventive.source == "preventive_tradeoff_public"
    assert {scenario.value for scenario in preventive.scenarios} == {"D", "E"}
    assert preventive.solver_config["workers"] == 8


def test_d_is_fixed_and_e_is_validated_with_lexicographic_metadata(tiny):
    aid = next(iter(tiny.activities))
    instance = replace(tiny, activities={aid: replace(tiny.activities[aid], total_accesses=1)})
    rules = rules_for(instance)
    d = solve_preventive(instance, rules, PreventiveScenario.D, 5, workers=1)
    e = solve_preventive(instance, rules, PreventiveScenario.E, 5, workers=1)
    assert d.validation.feasible and e.validation.feasible
    assert preventive_solution_files(d)["RESULTS.csv"].decode().splitlines()[1].startswith("D,")
    assert preventive_solution_files(e)["RESULTS.csv"].decode().splitlines()[1].startswith("E,")
    assert all(not row.deferred and row.actual_date == row.planned_date for row in d.maintenance)
    assert e.solver_stats["objective_hierarchy"][0]["name"] == "project_objective"
    assert all(0 <= row.deferral_days <= 7 for row in e.maintenance)
    assert e.validation.soft_scores["deferred_maintenance_count"] == 0
    horizon_end = instance.horizon_start + timedelta(days=instance.horizon_weeks * 7 - 1)
    assert max(row.planned_date for row in e.maintenance) == horizon_end
    assert max(row.actual_date for row in e.maintenance) <= horizon_end + timedelta(days=7)
    assert not ({(loc, access.access_date) for access in d.project_accesses
                 for loc in activity_locations(instance, instance.activities[access.activity_id])}
                & {(row.location_id, row.actual_date) for row in d.maintenance})
    comparison = preventive_tradeoff(d, e)
    assert comparison["title"] == "Scenario D vs E Trade-off"
    assert "project_objective_score" in comparison["metrics"]


def test_independent_validator_rejects_missing_and_excessive_deferral(tiny):
    aid = next(iter(tiny.activities))
    instance = replace(tiny, activities={aid: replace(tiny.activities[aid], total_accesses=1)})
    rules = rules_for(instance)
    solution = solve_preventive(instance, rules, PreventiveScenario.E, 5, workers=1)
    files = preventive_solution_files(solution, include_validation=False)
    lines = files["MAINTENANCE_SCHEDULE.csv"].decode().splitlines()
    files["MAINTENANCE_SCHEDULE.csv"] = ("\n".join([lines[0], *lines[2:]]) + "\n").encode()
    report = validate_preventive_files(instance, rules, PreventiveScenario.E, files,
                                       solution.solver_stats["objective_hierarchy"])
    assert not report.feasible
    assert "maintenance" in {item["rule"] for item in report.hard_violations}


def test_forced_weekend_conflict_moves_project_in_d_and_maintenance_in_e():
    base = topology_instance(types=("C",), capacity=5, weeks=2, sectors=9)
    template = base.activities["A0"]
    activities = {}
    for index, sector in enumerate((0, 2, 4, 6, 8)):
        activity_id = f"A{index}"
        location = f"SEC:L:S{sector}_S{sector + 1}:EB"
        activities[activity_id] = replace(template, activity_id=activity_id,
                                          start_location_id=location, end_location_id=location)
    contract = replace(base.contracts["C0"], number_of_workfronts=1,
                       number_of_maximum_access_per_week=5,
                       planned_completion_date=base.horizon_start + timedelta(days=6))
    forced = replace(base, contracts={"C0": contract}, activities=activities)
    rules = rules_for(forced)
    d = solve_preventive(forced, rules, PreventiveScenario.D, 10, workers=1)
    e = solve_preventive(forced, rules, PreventiveScenario.E, 10, workers=1)
    assert d.validation.soft_scores["total_project_overrun_days"] > e.validation.soft_scores["total_project_overrun_days"]
    assert d.validation.soft_scores["deferred_maintenance_count"] == 0
    assert e.validation.soft_scores["deferred_maintenance_count"] >= 1
    assert e.validation.soft_scores["conflict_driven_deferrals"] >= 1
    comparison = preventive_tradeoff(d, e)
    assert comparison["schedule_difference_summary"]["project_accesses_changed"] >= 1
    assert comparison["schedule_difference_summary"]["maintenance_occurrences_changed"] >= 1
    assert comparison["project_schedule_differences"][0]["D"]["access_date"] != comparison["project_schedule_differences"][0]["E"]["access_date"]


def test_preventive_api_rejects_tradeoff_until_both_scenarios_are_valid(tiny, monkeypatch):
    manager = JobManager()
    manager._executor.shutdown()
    manager._executor = SimpleNamespace(submit=lambda *args: None)
    monkeypatch.setattr(api, "job_manager", manager)
    client = TestClient(app)
    created = client.post("/api/ps1/preventive/jobs?public=true&time_limit_seconds=5").json()
    assert created["job_kind"] == "preventive"
    assert set(created["scenarios"]) == {"D", "E"}
    assert client.get(f"/api/ps1/jobs/{created['job_id']}/preventive-tradeoff").status_code == 409
