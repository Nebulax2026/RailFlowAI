from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, InstanceValidationError, parse_instance
from app.ps1.solver import solve_scenario, SolveFailure
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import validate_exported_csvs

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "PS1" / "01_data"
SAMPLE = ROOT / "PS1" / "03_submission_sample"


@pytest.fixture(scope="module")
def instance():
    return parse_instance({name: (DATA / name).read_bytes() for name in EXPECTED_FILES})


def test_public_instance_counts(instance):
    assert len(instance.lines) == 2
    assert len(instance.stations) == 20
    assert len(instance.sectors) == 18
    assert len(instance.supply) == 76
    assert len(instance.contracts) == 14
    assert len(instance.activities) == 54
    assert sum(item.total_accesses for item in instance.activities.values()) == 192


def test_parser_rejects_missing_and_bad_headers():
    files = {name: (DATA / name).read_bytes() for name in EXPECTED_FILES}
    del files["01_LINES.csv"]
    with pytest.raises(InstanceValidationError, match="Missing files"):
        parse_instance(files)
    files = {name: (DATA / name).read_bytes() for name in EXPECTED_FILES}
    files["01_LINES.csv"] = b"wrong,header\nALP,Alpha\n"
    with pytest.raises(InstanceValidationError, match="expected headers"):
        parse_instance(files)


def test_parser_rejects_predecessor_cycles():
    files = {name: (DATA / name).read_bytes() for name in EXPECTED_FILES}
    activities = files["08_ACTIVITY_DETAILS.csv"]
    activities = activities.replace(b"2,2027-05-24,,2", b"2,2027-05-24,A002,2", 1)
    activities = activities.replace(b"1,2027-01-04,,3", b"1,2027-01-04,A001,3", 1)
    files["08_ACTIVITY_DETAILS.csv"] = activities
    with pytest.raises(InstanceValidationError, match="predecessor cycle"):
        parse_instance(files)


def test_topology_expands_sectors_and_platforms(instance):
    locations = activity_locations(instance, instance.activities["A001"])
    assert locations == [
        "PLAT:BET:S15:EB",
        "PLAT:BET:S16:EB",
        "PLAT:BET:S17:EB",
        "SEC:BET:S15_S16:EB",
        "SEC:BET:S16_S17:EB",
    ]


def test_live_interchange_reserves_opposite_bounds_and_both_lines(instance):
    reserved = closure_locations(instance, instance.activities["A074"])
    assert "SEC:ALP:H01_H02:WB" in reserved
    assert "SEC:BET:H01_H02:EB" in reserved
    assert "SEC:BET:H01_H02:WB" in reserved
    assert "PLAT:BET:H01:EB" in reserved


def test_organizer_sample_compatibility_is_explicit(instance):
    files = {name: (SAMPLE / name).read_bytes() for name in ("SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv")}
    report = validate_exported_csvs(instance, Scenario.A, files)
    # User-confirmed format-only sample, not a feasible golden schedule.
    assert not report.feasible
    assert all(v['rule'] == 'closure' for v in report.hard_violations)
    assert any(all(value in v['detail'] for value in ('A001', 'A007', '22', 'SEC:BET:H02_S15:EB')) for v in report.hard_violations)
    assert any('A023/A070' in v['detail'] for v in report.hard_violations)
    assert "objective_score" not in report.soft_scores


def test_export_validator_detects_workload_mutation(instance):
    files = {name: (SAMPLE / name).read_bytes() for name in ("SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv")}
    lines = files["SCHEDULE_ACCESS.csv"].decode().splitlines()
    files["SCHEDULE_ACCESS.csv"] = ("\n".join([lines[0], *lines[2:]]) + "\n").encode()
    report = validate_exported_csvs(instance, Scenario.A, files)
    assert not report.feasible
    assert "workload" in {item["rule"] for item in report.hard_violations}


@pytest.mark.parametrize("scenario", list(Scenario))
def test_solver_generates_complete_feasible_public_outputs(instance, scenario):
    # Match the production first-search + improvement budget. Thirty seconds
    # is a performance target, not a feasibility guarantee.
    try:
        solution = solve_scenario(instance, scenario, time_limit_seconds=30)
    except SolveFailure as error:
        if error.reason != "time_limit": raise
        solution = solve_scenario(instance, scenario, time_limit_seconds=90)
    assert solution.validation.feasible
    assert not solution.validation.hard_violations
    assert sum(1.5 if item.eclo else 1 for item in solution.accesses) >= 192
    if scenario == Scenario.A:
        assert not any(item.eclo for item in solution.accesses)
        assert solution.validation.soft_scores["excess_access_nights_total"] == 0
    if scenario == Scenario.B:
        assert solution.validation.soft_scores["overrun_days_total"] == 0


def test_api_health_and_upload_validation():
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.post("/api/ps1/jobs")
    assert response.status_code == 422
