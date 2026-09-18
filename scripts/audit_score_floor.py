"""Audit public score floors without treating a failed heuristic as a proof."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import threading
import time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ortools.sat.python import cp_model
import ortools
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.solver import build_scenario_model
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import OUTPUT_HEADERS, validate_exported_csvs
from app.ps1.exporter import scenario_csvs
from app.ps1.scenario_a.model import build_model
from app.ps1.scenario_a.policy import prepare
from app.ps1.scenario_a.validation import validate_csvs


def isolated_lower_bound(instance, scenario):
    """Drop every shared-resource/space/precedence constraint.

    At most one access per week. Enumerate access and ECLO counts; assume all
    accesses take place consecutively from release. This can only improve the
    finish date. C permits at most two ECLO accesses per activity; dropping its
    cross-activity window coupling can only enlarge the feasible set.
    """
    rows = []
    for aid, a in instance.activities.items():
        c = instance.contracts[a.contract_number]
        release = max(1, (a.planned_start_date-instance.horizon_start).days//7+1)
        weight = {1: 100, 2: 10, 3: 1}[c.contract_priority] * {1: 13, 2: 12, 3: 10}[a.activity_priority]
        candidates = []
        for n in range(1, instance.horizon_weeks-release+2):
            end = instance.horizon_start + timedelta(days=7*(release+n-1)-1)
            late = max(0, (end-c.planned_completion_date).days)
            if scenario == Scenario.B and late: continue
            maximum = 0 if scenario == Scenario.A else min(n, 2) if scenario == Scenario.C else n
            for e in range(maximum+1):
                if 2*n+e < 2*a.total_accesses: continue
                cost = (0 if scenario == Scenario.B else late*weight) + 50*e
                candidates.append((cost, n, e, late))
        if not candidates: raise ValueError(f"Isolated infeasible activity: {aid}")
        cost, n, e, late = min(candidates)
        rows.append(dict(activity=aid, release_week=release, workload=a.total_accesses,
                         planned_completion_date=str(c.planned_completion_date),
                         cost_lower_bound=cost/10, relaxed_access_count=n,
                         relaxed_eclo_count=e, relaxed_late_days=late))
    return dict(lower_bound=sum(round(r["cost_lower_bound"]*10) for r in rows)/10,
                positive_contributions=[r for r in rows if r["cost_lower_bound"]], activities=rows)


def relaxed_a(instance):
    """Location-local legal work mixes plus unshareable PM protection only.

    No coherent global cohorts, non-PM buffers, predecessors or contract
    resources. Relaxation solutions are *not* publishable schedules.
    """
    model = cp_model.CpModel()
    x, costs, work, footprint = {}, [], {}, {}
    for aid, a in instance.activities.items():
        c = instance.contracts[a.contract_number]
        lo = max(1, (a.planned_start_date-instance.horizon_start).days//7+1)
        for w in range(lo, instance.horizon_weeks+1):
            x[aid, w] = model.new_bool_var(f"x_{aid}_{w}")
        terms = [(w, v) for (b, w), v in x.items() if b == aid]
        model.add(sum(v for _, v in terms) == a.total_accesses)
        finish = model.new_int_var(lo, instance.horizon_weeks, f"end_{aid}")
        model.add_max_equality(finish, [w*v for w, v in terms])
        late = model.new_int_var(0, max(0, 7*instance.horizon_weeks-1-(c.planned_completion_date-instance.horizon_start).days), f"late_{aid}")
        model.add_max_equality(late, [0, 7*finish-1-(c.planned_completion_date-instance.horizon_start).days])
        costs.append(late * {1: 100, 2: 10, 3: 1}[c.contract_priority] * {1: 13, 2: 12, 3: 10}[a.activity_priority])
        work[aid] = set(activity_locations(instance, a))
        footprint[aid] = work[aid] | closure_locations(instance, a)
    for loc, supply in instance.supply.items():
        for w in range(1, instance.horizon_weeks+1):
            types = defaultdict(list)
            for aid, a in instance.activities.items():
                if (aid, w) in x and loc in work[aid]:
                    types[instance.contracts[a.contract_number].access_type].append(x[aid, w])
            pm, pc, c = (sum(types[t]) for t in ("PM", "PC", "C"))
            model.add(pm+pc <= supply.supply_capacity)
            model.add(4*pm+pc+c <= 4*supply.supply_capacity)
    for aid, a in instance.activities.items():
        if instance.contracts[a.contract_number].access_type != "PM": continue
        for bid in instance.activities:
            if bid == aid: continue
            if any(instance.supply[loc].supply_capacity == 1 for loc in footprint[aid] & footprint[bid]):
                for w in range(1, instance.horizon_weeks+1):
                    if (aid, w) in x and (bid, w) in x:
                        model.add(x[aid, w]+x[bid, w] <= 1)
    model.minimize(sum(costs))
    return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = {n: (ROOT / "PS1/01_data" / n).read_bytes() for n in EXPECTED_FILES}
    instance = parse_instance(files)
    targets = {Scenario.A: 406, Scenario.B: 300, Scenario.C: 252}
    report = dict(input_sha256={n: hashlib.sha256(v).hexdigest() for n, v in files.items()},
                  ortools_version=ortools.__version__, workers=1, seconds_per_probe=args.seconds,
                  official_validator_available=False, incumbent_checks={}, isolated_bounds={}, strict_improvement_probes=[])
    def save():
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    for scenario in Scenario:
        csvs = {n: (ROOT / "submission/public-results" / f"scenario_{scenario.value}" / n).read_bytes() for n in OUTPUT_HEADERS}
        validation = validate_exported_csvs(instance, scenario, csvs)
        assert validation.feasible and round(validation.soft_scores["objective_score"]*10) == targets[scenario]
        report["incumbent_checks"][scenario.value] = dict(feasible=validation.feasible, violations=len(validation.hard_violations), score=validation.soft_scores["objective_score"])
        report["isolated_bounds"][scenario.value] = isolated_lower_bound(instance, scenario)
    save()
    for name, scenario in [("main_A", Scenario.A), ("main_B", Scenario.B), ("main_C", Scenario.C), ("local_witness_A", Scenario.A)]:
        started = time.monotonic()
        if name == "local_witness_A":
            built = build_model(instance, prepare(instance), started+args.seconds)
            model, cost = built.model, built.cost
        else:
            built = build_scenario_model(instance, scenario, args.seconds, started, threading.Event())
            model, cost = built.model, built.primary
        ceiling = targets[scenario]-1
        model.add(cost <= ceiling)
        model.clear_objective()
        model_path = args.output / f"{name}_strict_improvement.pbtxt"
        model.export_to_file(str(model_path))
        model_bytes = model_path.read_bytes()
        model_path.with_suffix(".pbtxt.gz").write_bytes(gzip.compress(model_bytes, mtime=0))
        model_path.unlink()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(.001, args.seconds-(time.monotonic()-started))
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        result = solver.solve(model)
        row = dict(model=name, scenario=scenario.value, score_ceiling=ceiling/10,
                   status=solver.status_name(result), elapsed_seconds=time.monotonic()-started,
                   model_sha256=hashlib.sha256(model_bytes).hexdigest(),
                   response_stats=solver.response_stats())
        if result in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            candidate = built.extract(solver.value) if name == "local_witness_A" else built.extract(solver)
            csvs = scenario_csvs(candidate)
            validation = validate_csvs(instance, csvs) if name == "local_witness_A" else validate_exported_csvs(instance, scenario, csvs)
            row["candidate_valid"] = validation.feasible
            row["candidate_score"] = validation.soft_scores.get("objective_score")
            if validation.feasible:
                output = args.output / name
                output.mkdir()
                for filename, data in csvs.items(): (output / filename).write_bytes(data)
        report["strict_improvement_probes"].append(row)
        save()
        print(json.dumps(row), flush=True)
    relaxed = relaxed_a(instance)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.seconds
    solver.parameters.num_search_workers = 1
    result = solver.solve(relaxed)
    report["relaxed_A"] = dict(status=solver.status_name(result), lower_bound=solver.best_objective_bound/10,
                               objective=solver.objective_value/10,
                               publishable=False, omitted="non-PM protection, contract resources, precedence and coherent cohorts")
    save()
    print(json.dumps(report["relaxed_A"]), flush=True)


if __name__ == "__main__":
    main()
