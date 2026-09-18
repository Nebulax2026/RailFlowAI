from __future__ import annotations

import itertools
import json
import time
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ps1.exporter import scenario_csvs
from app.ps1.models import Activity, BufferRule, Contract, Instance, Line, LocationSupply, Sector, Station
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.policy import prepare
from app.ps1.scenario_a.search import SearchConfig, neighborhood, solve
from app.ps1.scenario_a.validation import HEADERS, independent_footprints, validate_csvs

ROOT = Path(__file__).resolve().parents[2]


def tiny(types=("C", "C"), capacity=1, weeks=3, sectors=1):
    start = date(2027, 1, 4)
    station = {("L", f"S{i}"): Station(f"S{i}", "L", i + 1, False) for i in range(sectors + 1)}
    edges = {f"SEC:L:S{i}_S{i+1}": Sector(f"SEC:L:S{i}_S{i+1}", "L", f"S{i}", f"S{i+1}", i + 1, False) for i in range(sectors)}
    supply = {}
    for bound in ("EB", "WB"):
        for eid in edges:
            lid = f"{eid}:{bound}"
            supply[lid] = LocationSupply(lid, "tunnel sector", "L", bound, capacity)
        for _, sid in station:
            lid = f"PLAT:L:{sid}:{bound}"
            supply[lid] = LocationSupply(lid, "platform sector", "L", bound, capacity)
    contracts, activities = {}, {}
    for n, typ in enumerate(types):
        cid, aid = f"C{n}", f"A{n}"
        contracts[cid] = Contract(cid, cid, start, "Renewal", "Non-live (Others)", 3, start + timedelta(days=365), start + timedelta(days=6), 1, typ, 1)
        activities[aid] = Activity(aid, cid, "Renewal", "SEC:L:S0_S1:EB", "SEC:L:S0_S1:EB", 1, start, None, 3)
    return Instance({"L": Line("L", "Line")}, station, edges, supply,
                    {"Non-live (Others)": BufferRule("Non-live (Others)", 0, False),
                     "Non-live (Consist)": BufferRule("Non-live (Consist)", 1, False),
                     "Live": BufferRule("Live", 2, True)}, start, weeks, contracts, activities)


def run(instance, **kwargs):
    return solve(instance, SearchConfig(time_limit_seconds=3, initialization="direct", **kwargs))


def exhaustive_same_site(instance):
    """Enumeration oracle for small, buffer-free, one-site problems.

    Enumerates week choices and derives the minimum number of legal PC/C/PM
    groups by counting; it never calls CP-SAT or optimizer packing code.
    """
    ids = sorted(instance.activities)
    choices = [list(itertools.combinations(range(max(1, (instance.activities[a].planned_start_date - instance.horizon_start).days // 7 + 1), instance.horizon_weeks + 1), instance.activities[a].total_accesses)) for a in ids]
    best = None
    for selected in itertools.product(*choices):
        schedule = dict(zip(ids, selected))
        if any(item.predecessor_activity_id and min(schedule[a]) <= max(schedule[item.predecessor_activity_id]) for a, item in instance.activities.items()):
            continue
        feasible = True
        for w in range(1, instance.horizon_weeks + 1):
            members = [a for a in ids if w in schedule[a]]
            counts = Counter(instance.contracts[instance.activities[a].contract_number].access_type for a in members)
            slots = counts["PM"] + counts["PC"] + (max(0, counts["C"] - 3 * counts["PC"]) + 3) // 4
            resources = Counter(instance.activities[a].contract_number for a in members)
            # At this single site, separate groups intersect each other's
            # weekly closure even when extra supply is available.
            if slots > min(1, min(s.supply_capacity for s in instance.supply.values())) or any(n > instance.contracts[c].number_of_workfronts * instance.contracts[c].number_of_maximum_access_per_week for c, n in resources.items()):
                feasible = False; break
        if feasible:
            score = 0
            for cid, c in instance.contracts.items():
                contract_ids = [a for a in ids if instance.activities[a].contract_number == cid]
                finish = instance.horizon_start + timedelta(days=max(max(schedule[a]) for a in contract_ids) * 7 - 1)
                multiplier_tenths = sum({1: 13, 2: 12, 3: 10}[instance.activities[a].activity_priority]
                                        for a in contract_ids)
                score += max(0, (finish - c.planned_completion_date).days) * {1: 100, 2: 10, 3: 1}[c.contract_priority] * multiplier_tenths
            best = score if best is None else min(best, score)
    return None if best is None else best / 10


@pytest.mark.parametrize("types,capacity,weeks", [(('PC','PC'),1,1), (('PM','C'),1,2), (('PC','C','C','C'),1,1), (('C','C','C','C','C'),1,2), (('PC','PC','C'),2,2)])
def test_integrated_matches_exhaustive_oracle(types, capacity, weeks):
    instance = tiny(types, capacity, weeks)
    oracle = exhaustive_same_site(instance)
    result = run(instance)
    assert result.diagnostics["objective"] == oracle
    assert result.diagnostics["status"] == ("infeasible_for_policy" if oracle is None else "optimal_for_policy")


def test_dates_priorities_and_predecessors_match_oracle():
    instance = tiny(("PM", "PC", "C"), weeks=4)
    instance.contracts["C0"] = replace(instance.contracts["C0"], contract_priority=1, planned_completion_date=date(2027, 1, 6))
    instance.activities["A0"] = replace(instance.activities["A0"], activity_priority=1)
    instance.activities["A2"] = replace(instance.activities["A2"], predecessor_activity_id="A1", activity_priority=2)
    expected = exhaustive_same_site(instance)
    result = run(instance)
    assert result.diagnostics["objective"] == expected
    assert expected >= 4 * 100 * 1.3  # Wednesday target -> Sunday completion: four days, not seven.
    dates = {r.activity_id: r.week for r in result.solution.accesses}
    assert dates["A2"] > dates["A1"]


def test_contract_resources_are_independent_of_location_slots():
    instance = tiny(("C", "C"), capacity=4, weeks=2)
    instance.activities["A1"] = replace(instance.activities["A1"], contract_number="C0")
    del instance.contracts["C1"]
    result = run(instance)
    # Both activities belong to the late contract, so both multipliers are
    # charged for its seven-day overrun: 7 * (1.0 + 1.0) = 14.
    assert result.diagnostics["objective"] == exhaustive_same_site(instance) == 14
    assert len({a.week for a in result.solution.accesses}) == 2
    instance.contracts["C0"] = replace(instance.contracts["C0"], number_of_workfronts=2)
    assert run(instance).diagnostics["objective"] == 0


@pytest.mark.parametrize("capacity,feasible", [(1, False), (2, False)])
def test_weekly_work_buffer_conflicts_ignore_extra_supply(capacity, feasible):
    instance = tiny(("C", "C"), capacity=capacity, weeks=1, sectors=4)
    for cid in instance.contracts:
        instance.contracts[cid] = replace(instance.contracts[cid], nature_of_activity="Non-live (Consist)")
    instance.activities["A1"] = replace(instance.activities["A1"], start_location_id="SEC:L:S2_S3:EB", end_location_id="SEC:L:S2_S3:EB")
    assert bool(run(instance).solution) is feasible


def test_direct_sharing_exempts_partners_but_not_external_buffers():
    instance = tiny(("PC", "C"), capacity=1, weeks=1, sectors=3)
    for cid in instance.contracts:
        instance.contracts[cid] = replace(instance.contracts[cid], nature_of_activity="Non-live (Consist)")
    result = run(instance)
    assert result.solution and result.solution.validation.feasible
    files = scenario_csvs(result.solution)
    rows = files["SCHEDULE_OCCUPANCY.csv"].decode().splitlines()
    files["SCHEDULE_OCCUPANCY.csv"] = ("\n".join(r.rsplit(",", 1)[0] + ",external" if r.startswith("A1,") else r for r in rows) + "\n").encode()
    assert not validate_csvs(instance, files).feasible


def test_live_mirrors_and_closes_interchange():
    data = ROOT / "PS1/01_data"
    instance = parse_instance({n: (data / n).read_bytes() for n in EXPECTED_FILES})
    prepared = prepare(instance)
    work, reserve = independent_footprints(instance, "A074")
    assert work == prepared.work["A074"] and reserve == prepared.reserve["A074"]
    assert {"SEC:ALP:H01_H02:WB", "SEC:BET:H01_H02:EB", "PLAT:BET:H01:WB"} <= reserve
    a = replace(instance.activities["A074"], planned_start_date=instance.horizon_start)
    b = replace(instance.activities["A055"], start_location_id="SEC:BET:H01_H02:EB", end_location_id="SEC:BET:H01_H02:EB", planned_start_date=instance.horizon_start, predecessor_activity_id=None)
    instance.activities = {a.activity_id: a, b.activity_id: b}
    instance.contracts = {c: instance.contracts[c] for c in (a.contract_number, b.contract_number)}
    instance.horizon_weeks = 1
    assert run(instance).diagnostics["status"] == "infeasible_for_policy"


@pytest.mark.parametrize("mutation,rule", [("missing", "workload"), ("duplicate", "weekly_activity"), ("eclo", "eclo"), ("unknown", "activity"), ("result", "results"), ("occupancy", "occupancy"), ("night", "weekly_allocation")])
def test_csv_mutations_are_rejected(mutation, rule):
    instance = tiny(("C",), weeks=1)
    files = scenario_csvs(run(instance).solution)
    access = files["SCHEDULE_ACCESS.csv"].decode().splitlines()
    if mutation == "missing": access = access[:1]
    if mutation == "duplicate": access.append(access[1])
    if mutation == "eclo": access[1] = "A0,1,1,1,1"
    if mutation == "unknown": access[1] = "X,1,1,0,1"
    if mutation == "night": access[1] = "A0,1,1,0,2"
    files["SCHEDULE_ACCESS.csv"] = ("\n".join(access) + "\n").encode()
    if mutation == "result": files["RESULTS.csv"] = files["RESULTS.csv"].replace(b"2027-01-10", b"2027-01-09")
    if mutation == "occupancy": files["SCHEDULE_OCCUPANCY.csv"] = (files["SCHEDULE_OCCUPANCY.csv"].decode().splitlines()[0] + "\n").encode()
    report = validate_csvs(instance, files)
    assert not report.feasible and rule in {v["rule"] for v in report.hard_violations}
    assert "objective_score" not in report.soft_scores


def test_no_horizon_extension_or_clamping():
    instance = tiny(("C",), weeks=2)
    instance.activities["A0"] = replace(instance.activities["A0"], planned_start_date=instance.horizon_start + timedelta(days=21))
    assert run(instance).diagnostics["status"] == "infeasible_for_policy"


@pytest.mark.parametrize("types", [("PC", "PC"), ("PM", "C")])
def test_validator_rejects_illegal_sharing(types):
    instance = tiny(("C", "C"), capacity=2, weeks=1)
    files = scenario_csvs(run(instance).solution)
    for cid, typ in zip(sorted(instance.contracts), types):
        instance.contracts[cid] = replace(instance.contracts[cid], access_type=typ)
    report = validate_csvs(instance, files)
    assert "legal_mix" in {v["rule"] for v in report.hard_violations}


def test_validator_checks_optimizer_cost_and_extra_columns():
    instance = tiny(("C",), weeks=1)
    files = scenario_csvs(run(instance).solution)
    assert not validate_csvs(instance, files, expected_cost=1).feasible
    files["SCHEDULE_ACCESS.csv"] = files["SCHEDULE_ACCESS.csv"].replace(b"A0,1,1,0,1", b"A0,1,1,0,1,debug")
    assert validate_csvs(instance, files).hard_violations[0]["rule"] == "schema"


@pytest.mark.parametrize("operator", ["delay", "bottleneck", "sharing", "precedence", "contract", "diversify"])
def test_neighborhood_releases_shared_partners(operator):
    import random
    instance = tiny(("PC", "C", "C"), weeks=1)
    solution = run(instance).solution
    assert neighborhood(instance, prepare(instance), solution, operator, .1, random.Random(42)) == set(instance.activities)


def test_cancel_retains_validated_greedy_incumbent():
    instance = tiny(("PM", "C"), weeks=2)
    checkpoints = []
    result = solve(instance, SearchConfig(strategy="alns", time_limit_seconds=3), cancelled=lambda: bool(checkpoints), checkpoint=lambda s, d: checkpoints.append(d))
    assert result.solution.validation.feasible
    assert result.diagnostics["status"] == "cancelled_with_feasible"
    assert checkpoints


def test_api_selection_is_validated_and_a_only(monkeypatch):
    from app.ps1.jobs import job_manager
    # Prevent starting expensive legacy runs; inspect the actual created job.
    monkeypatch.setattr(job_manager._executor, "submit", lambda *args: None)
    client = TestClient(app)
    assert client.post("/api/ps1/jobs?public=true&algorithm=unknown").status_code == 422
    assert client.post("/api/ps1/jobs?public=true&algorithm=strategies&strategy=greedy").status_code == 422
    assert client.post("/api/ps1/jobs?public=true&algorithm=scenario_a&time_limit_seconds=9999").status_code == 422
    legacy = client.post("/api/ps1/jobs?public=true").json()
    assert set(legacy["scenarios"]) == {"A", "B", "C"}
    new = client.post("/api/ps1/jobs?public=true&algorithm=scenario_a&strategy=alns&seed=9").json()
    assert set(new["scenarios"]) == {"A"}
    assert new["solver_config"]["strategy"] == "alns"
    assert new["solver_config"]["seed"] == 9
    assert client.get(f"/api/ps1/jobs/{new['job_id']}/scenarios/B").status_code == 404
    assert client.get(f"/api/ps1/jobs/{new['job_id']}/download").status_code == 409
    cancelled = client.delete(f"/api/ps1/jobs/{new['job_id']}").json()
    assert cancelled["status"] == cancelled["scenarios"]["A"]["status"] == "cancelled"


def test_job_without_incumbent_retains_search_outcome(monkeypatch):
    from app.ps1.jobs import JobManager
    from app.ps1.models import JobStatus, Scenario
    from app.ps1.scenario_a.search import SearchResult
    from app.ps1.scenario_a import worker
    manager = JobManager()
    monkeypatch.setattr(manager._executor, "submit", lambda *args: None)
    monkeypatch.setattr(worker, "run_worker", lambda *args: SearchResult(None, {
        "status": "infeasible_for_policy", "objective": None, "elapsed_seconds": 0.1,
    }))
    try:
        job = manager.create_public("scenario_a", {"time_limit_seconds": 5})
        manager._run(job.job_id)
        run_state = job.scenarios[Scenario.A]
        assert job.status == JobStatus.FAILED
        assert run_state.termination_reason == "infeasible_for_policy"
        assert run_state.phase == "finished"
        assert run_state.solution is None
        assert not job.input_files
    finally:
        manager._executor.shutdown()
