"""Regressions from the user's official rejection of run 98b06b7e."""
from dataclasses import replace
import ast
import json
import re
from pathlib import Path

import pytest

from app.ps1.exporter import scenario_csvs
from app.ps1.models import AccessAssignment, OccupancyAssignment, Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.safety import weekly_closure_errors
from app.ps1.strategy import SearchConfig
from app.ps1.topology_audit import independent_footprints
from app.ps1.scenario_search import solve as solve_strategy
from app.ps1.solver import solve_scenario
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import validate_exported_csvs


@pytest.fixture
def public():
    source = Path(__file__).resolve().parents[2] / "PS1/01_data"
    return parse_instance({name: (source / name).read_bytes() for name in EXPECTED_FILES})


def conflicting_pair(public):
    # Both PC Consist jobs: the real official week-9 rejection, simplified
    # to one access each so every scenario can finish within two weeks.
    activities = {aid: replace(public.activities[aid], total_accesses=1,
                              planned_start_date=public.horizon_start)
                  for aid in ("A025", "A028")}
    contracts = {a.contract_number: public.contracts[a.contract_number] for a in activities.values()}
    return replace(public, activities=activities, contracts=contracts, horizon_weeks=2)


@pytest.mark.parametrize("scenario", list(Scenario))
def test_weekly_closure_cannot_be_waived_by_nights_or_supply(public, scenario):
    instance = conflicting_pair(public)
    solution = solve_scenario(instance, scenario, 3, workers=1)
    assert solution.validation.feasible
    assert len({row.week for row in solution.accesses}) == 2
    # Force the exact rejected pattern: two groups in the same week, with
    # distinct local night labels and abundant supply. Dates/results can also
    # fail after mutation; closure must independently fail and suppress score.
    solution.accesses = [replace(r, week=1, access_night=n) for n, r in enumerate(solution.accesses, 1)]
    solution.occupancy = [replace(r, week=1, co_share_group=r.activity_id) for r in solution.occupancy]
    roomy = replace(instance, supply={k: replace(v, supply_capacity=20) for k, v in instance.supply.items()})
    report = validate_exported_csvs(roomy, scenario, scenario_csvs(solution))
    assert any(v["rule"] == "closure" and "A025/A028" in v["detail"] for v in report.hard_violations)
    assert not report.feasible and "objective_score" not in report.soft_scores


@pytest.mark.parametrize("strategy", ["integrated", "random_lns", "alns"])
def test_a_strategies_use_same_closure_gate(public, strategy):
    instance = conflicting_pair(public)
    result = solve_strategy(instance, Scenario.A, SearchConfig(strategy=strategy, time_limit_seconds=3, workers=1))
    assert result.solution and result.solution.validation.feasible
    assert len({r.week for r in result.solution.accesses}) == 2
    assert result.diagnostics["policy"] == "observed-weekly-closures-v4"


@pytest.mark.parametrize("aid,line,stations,sectors", [
    ("A074", "BET", ["S13", "S14", "H01", "H02", "S15", "S16"],
     ["S13_S14", "S14_H01", "H01_H02", "H02_S15", "S15_S16"]),
    ("A075", "ALP", ["S03", "S04", "H01", "H02", "S05", "S06"],
     ["S03_S04", "S04_H01", "H01_H02", "H02_S05", "S05_S06"]),
])
def test_live_interchange_buffers_expand_on_receiving_line(public, aid, line, stations, sectors):
    actual = closure_locations(public, public.activities[aid])
    expected = {f"PLAT:{line}:{s}:{b}" for s in stations for b in ("EB", "WB")}
    expected |= {f"SEC:{line}:{s}:{b}" for s in sectors for b in ("EB", "WB")}
    assert {loc for loc in actual if f":{line}:" in loc} == expected


def test_direct_legal_sharing_remains_exempt(public):
    instance = conflicting_pair(public)
    cid = instance.activities["A028"].contract_number
    instance = replace(instance, contracts={**instance.contracts, cid: replace(instance.contracts[cid], access_type="C")})
    accesses = [AccessAssignment(aid, 1, 1, 0, 1) for aid in instance.activities]
    occupancy = [OccupancyAssignment(aid, 1, loc, "shared") for aid, a in instance.activities.items()
                 for loc in activity_locations(instance, a)]
    assert not weekly_closure_errors(instance, accesses, occupancy)


def test_every_reported_official_location_is_covered(public):
    audit_path = Path(__file__).resolve().parents[2] / "docs/official-validator-98b06b7e-audit.json"
    checks = json.loads(audit_path.read_text(encoding="utf-8"))["checks"]
    assert len(checks) == 64
    for check in checks:
        match = re.search(r" at (\[.*\])", check["official_message"])
        locations = set(ast.literal_eval(match[1]))
        footprint = set().union(*(set(activity_locations(public, public.activities[aid])) |
                                  closure_locations(public, public.activities[aid])
                                  for aid in check["closure_group_members"]))
        assert locations <= footprint
    # Cross-check the sequence-based expansion against the separate graph walk.
    for aid, activity in public.activities.items():
        work, reserve = independent_footprints(public, aid)
        assert work == set(activity_locations(public, activity))
        assert reserve == closure_locations(public, activity)


@pytest.mark.parametrize("scenario,expected", [(Scenario.A, 608.3), (Scenario.B, 50.0), (Scenario.C, 173.5)])
def test_replacement_scores_match_official_validator(public, scenario, expected):
    root = Path(__file__).resolve().parents[2] / "submission/official-closure-fix" / f"scenario_{scenario.value}"
    files = {name: (root / name).read_bytes() for name in ("SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv")}
    report = validate_exported_csvs(public, scenario, files)
    assert report.feasible
    assert report.soft_scores["objective_score"] == expected
