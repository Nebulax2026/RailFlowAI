from __future__ import annotations

import itertools
import math
import threading
import time
from collections import defaultdict
from ortools.sat.python import cp_model
from app.ps1.models import AccessAssignment, ContractResult, OccupancyAssignment, Scenario, ScenarioSolution
from app.ps1.scoring import delay_coefficient, week_end
from app.ps1.topology import activity_locations, closure_locations, affected_lines
from app.ps1.safety import legal_mix
from app.ps1.validator import validate_exported_csvs
from app.ps1.telemetry import peak_memory_mb


class SolveFailure(ValueError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def build_scenario_model(instance, scenario, time_limit_seconds, started, cancel_event, incumbent=None):
    def check_budget():
        if cancel_event.is_set(): raise SolveFailure("cancelled", "Cancelled while building the model.")
        if time.monotonic() - started >= time_limit_seconds:
            raise SolveFailure("time_limit", "Model construction used the search time budget; no infeasibility is implied.")
    check_budget()
    model = cp_model.CpModel()
    horizon = instance.horizon_weeks
    work = {a: set(activity_locations(instance, item)) for a, item in instance.activities.items()}
    footprint = {a: work[a] | closure_locations(instance, item) for a, item in instance.activities.items()}
    windows = {}
    for aid, activity in instance.activities.items():
        check_budget()
        contract = instance.contracts[activity.contract_number]
        earliest = max(1, (activity.planned_start_date - instance.horizon_start).days // 7 + 1)
        latest = horizon if scenario != Scenario.B else min(horizon, ((contract.planned_completion_date - instance.horizon_start).days + 1) // 7)
        windows[aid] = (earliest, latest)
    # Safe precedence propagation using the best possible yield; never fixes ECLO.
    for _ in instance.activities:
        changed = False
        for aid, activity in instance.activities.items():
            pred = activity.predecessor_activity_id
            if pred:
                p = instance.activities[pred]
                duration = p.total_accesses if scenario == Scenario.A else math.ceil(2 * p.total_accesses / 3)
                low, high = windows[aid]; new = max(low, windows[pred][0] + duration)
                if low != new: windows[aid] = (new, high); changed = True
        if not changed: break
    x = {}; eclo = {}; local_nights = {}; starts = {}; finishes = {}; objective = []; by_contract_night = defaultdict(list)
    line_windows = {line: model.NewIntVar(1, horizon, f"ECLO_window_{line}") for line in instance.lines} if scenario == Scenario.C else {}
    for aid, activity in instance.activities.items():
        low, high = windows[aid]; contract = instance.contracts[activity.contract_number]
        minimum = activity.total_accesses if scenario == Scenario.A else math.ceil(2 * activity.total_accesses / 3)
        if high - low + 1 < minimum:
            raise SolveFailure("infeasible", f"{aid}: workload and precedence cannot fit weeks {low}..{high} under Scenario {scenario.value}.")
        end_terms = []; start_terms = []; workload = []
        for week in range(low, high + 1):
            selected = x[aid, week] = model.NewBoolVar(f"access_{aid}_{week}")
            extra = eclo[aid, week] = model.NewBoolVar(f"eclo_{aid}_{week}")
            model.Add(extra <= selected)
            if scenario == Scenario.A: model.Add(extra == 0)
            if scenario == Scenario.C:
                for line in affected_lines(instance, activity):
                    model.Add(line_windows[line] <= week).OnlyEnforceIf(extra)
                    model.Add(line_windows[line] >= week - 1).OnlyEnforceIf(extra)
            workload.append(2 * selected + extra)
            choices = []
            for night in range(1, contract.number_of_maximum_access_per_week + 1):
                choice = local_nights[aid, week, night] = model.NewBoolVar(f"night_{aid}_{week}_{night}")
                choices.append(choice); by_contract_night[activity.contract_number, week, night].append(choice)
            model.Add(sum(choices) == selected)
            end_terms.append(week * selected)
            start_terms.append(week * selected + (horizon + 1) * (1 - selected))
            if scenario != Scenario.A: objective.append(50 * extra)
        model.Add(sum(workload) >= 2 * activity.total_accesses)
        # Dominated extra work is unnecessary: ECLO can always be downgraded.
        model.Add(sum(workload) <= 2 * activity.total_accesses + int(scenario != Scenario.A))
        starts[aid] = model.NewIntVar(low, high, f"start_{aid}")
        finishes[aid] = model.NewIntVar(low, high, f"finish_{aid}")
        model.AddMinEquality(starts[aid], start_terms); model.AddMaxEquality(finishes[aid], end_terms)
        if scenario != Scenario.B:
            late = model.NewIntVar(0, max(0, (week_end(instance, horizon) - contract.planned_completion_date).days), f"late_{aid}")
            model.AddMaxEquality(late, [0, finishes[aid] * 7 - 1 + (instance.horizon_start - contract.planned_completion_date).days])
            objective.append(late * delay_coefficient(contract, activity))
    for aid, activity in instance.activities.items():
        if activity.predecessor_activity_id: model.Add(finishes[activity.predecessor_activity_id] < starts[aid])
    for (cid, week, night), terms in by_contract_night.items():
        model.Add(sum(terms) <= instance.contracts[cid].number_of_workfronts)

    # Explicit legal possession patterns, with a common work location. A pattern
    # reserves the union of its work and protection, once, at every affected site.
    # This deliberately generates a coherent subset of the location-local format.
    patterns = set((aid,) for aid in instance.activities)
    at_location = defaultdict(list)
    for aid, locations in work.items():
        for loc in locations: at_location[loc].append(aid)
    combinations_seen = 0
    for ids in at_location.values():
        for size in range(2, min(4, len(ids)) + 1):
            for members in itertools.combinations(sorted(ids), size):
                combinations_seen += 1
                if combinations_seen % 1024 == 0: check_budget()
                if legal_mix(instance, members): patterns.add(members)
        if cancel_event.is_set(): raise SolveFailure("cancelled", "Cancelled while building possessions.")
    patterns = sorted(patterns)
    group_vars = {}; covers = defaultdict(list); usage = defaultdict(list); work_usage = defaultdict(list)
    for index, members in enumerate(patterns):
        if index % 64 == 0: check_budget()
        locations = set.union(*(footprint[a] for a in members))
        work_locations = set.union(*(work[a] for a in members))
        low = max(windows[a][0] for a in members); high = min(windows[a][1] for a in members)
        for week in range(low, high + 1):
            selected = group_vars[index, week] = model.NewBoolVar(f"possession_{index}_{week}")
            for aid in members: covers[aid, week].append(selected)
            for loc in locations: usage[loc, week].append(selected)
            for loc in work_locations: work_usage[loc, week].append(selected)
    for key, selected in x.items(): model.Add(sum(covers[key]) == selected)
    for (loc, week), terms in usage.items():
        nominal = instance.supply[loc].supply_capacity
        if scenario != Scenario.B: model.Add(sum(terms) <= nominal + int(scenario == Scenario.C))
        if scenario != Scenario.A:
            excess = model.NewIntVar(0, len(terms), f"excess_{loc}_{week}")
            model.AddMaxEquality(excess, [0, sum(work_usage[loc, week]) - nominal]); objective.append(70 * excess)
    primary = sum(objective)
    model.Minimize(primary)
    if incumbent:
        old = {(r.activity_id, r.week): r for r in incumbent.accesses}
        for key, var in x.items(): model.AddHint(var, int(key in old))
        for key, var in eclo.items(): model.AddHint(var, old[key].eclo if key in old else 0)
        for (aid, week, night), var in local_nights.items(): model.AddHint(var, int((aid, week) in old and old[aid, week].access_night == night))
        old_groups = defaultdict(set)
        for row in incumbent.occupancy: old_groups[row.week, row.co_share_group].add(row.activity_id)
        old_patterns = {(tuple(sorted(ids)), week) for (week, _label), ids in old_groups.items()}
        for (index, week), var in group_vars.items(): model.AddHint(var, int((patterns[index], week) in old_patterns))

    def extract(reader):
        accesses = []; occupancy = []
        for aid in sorted(instance.activities):
            rows = [(w, var) for (a, w), var in x.items() if a == aid and reader.Value(var)]
            contract = instance.contracts[instance.activities[aid].contract_number]
            for seq, (week, _) in enumerate(rows, 1):
                night = next(n for n in range(1, contract.number_of_maximum_access_per_week + 1) if reader.Value(local_nights[aid, week, n]))
                accesses.append(AccessAssignment(aid, seq, week, reader.Value(eclo[aid, week]), night))
        for (index, week), var in group_vars.items():
            if reader.Value(var):
                for aid in patterns[index]:
                    for loc in sorted(work[aid]): occupancy.append(OccupancyAssignment(aid, week, loc, f"p{index}"))
        results = []
        for cid, contract in instance.contracts.items():
            end = week_end(instance, max(reader.Value(finishes[a]) for a, item in instance.activities.items() if item.contract_number == cid))
            results.append(ContractResult(scenario.value, cid, end, max(0, (end - contract.planned_completion_date).days)))
        solution = ScenarioSolution(scenario, accesses, occupancy, results, None)
        from app.ps1.exporter import scenario_csvs
        solution.validation = validate_exported_csvs(instance, scenario, scenario_csvs(solution))
        if not solution.validation.feasible:
            raise SolveFailure("validation_failed", str(solution.validation.hard_violations[:3]))
        score = solution.validation.soft_scores['objective_score']
        if abs(score - reader.Value(primary) / 10) > 1e-6:
            raise SolveFailure("validation_failed", f"Objective mismatch: CSV {score}, model {reader.Value(primary) / 10}.")
        solution.explanations = [f"All {len(instance.activities)} activities meet their required workload.",
                                 f"{solution.validation.soft_scores['contracts_overrunning']} contracts finish after their planned date.",
                                 "Protection reservations use the documented conservative local-slot policy; official-validator parity is not claimed."]
        return solution

    from types import SimpleNamespace
    return SimpleNamespace(model=model, x=x, eclo=eclo, local_nights=local_nights,
                           group_vars=group_vars, patterns=patterns, primary=primary,
                           work=work, footprint=footprint, extract=extract)


def solve_scenario(instance, scenario, time_limit_seconds=30.0, *, incumbent=None, on_solution=None, cancel_event=None, workers=8, seed=42):
    started = time.monotonic()
    cancel_event = cancel_event or threading.Event()
    built = build_scenario_model(instance, scenario, time_limit_seconds, started, cancel_event, incumbent)
    model, primary, x, extract = built.model, built.primary, built.x, built.extract
    best = [incumbent]; first_time = [None]; callback_error = [None]
    class Publish(cp_model.CpSolverSolutionCallback):
        def __init__(self): super().__init__(); self.last = -math.inf
        def on_solution_callback(self):
            if cancel_event.is_set(): self.StopSearch(); return
            if time.monotonic() - self.last < 2: return
            if best[0] and self.Value(primary) / 10 >= best[0].validation.soft_scores['objective_score']: return
            try:
                solution = extract(self)
                if first_time[0] is None: first_time[0] = time.monotonic() - started
                solution.solver_stats = {"elapsed_seconds": time.monotonic() - started, "best_score": solution.validation.soft_scores['objective_score'], "best_bound": self.BestObjectiveBound() / 10, "optimal": False, "first_feasible_seconds": first_time[0]}
                best[0] = solution
                if on_solution: on_solution(solution)
            except Exception as error:
                callback_error[0] = error; self.StopSearch()
            self.last = time.monotonic()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.01, time_limit_seconds - (time.monotonic() - started))
    solver.parameters.num_search_workers = workers; solver.parameters.random_seed = seed
    done = threading.Event()
    def monitor():
        while not done.wait(0.1):
            if cancel_event.is_set(): solver.StopSearch(); return
    watcher = threading.Thread(target=monitor, daemon=True); watcher.start()
    try:
        status = solver.Solve(model, Publish())
    finally:
        done.set(); watcher.join()
    if callback_error[0]: raise callback_error[0]
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        candidate = extract(solver)
        if best[0] is None or candidate.validation.soft_scores['objective_score'] <= best[0].validation.soft_scores['objective_score']: best[0] = candidate
        if first_time[0] is None: first_time[0] = time.monotonic() - started
    # Lexicographic second pass only after proving the primary optimum.
    remaining = time_limit_seconds - (time.monotonic() - started)
    if status == cp_model.OPTIMAL and remaining > 0.1 and not cancel_event.is_set():
        model.Add(primary == round(solver.ObjectiveValue()))
        model.Minimize(sum(week * var for (aid, week), var in x.items()))
        early_solver = cp_model.CpSolver()
        early_solver.parameters.max_time_in_seconds = remaining
        early_solver.parameters.num_search_workers = workers
        early_solver.parameters.random_seed = seed
        early_done = threading.Event()
        def early_monitor():
            while not early_done.wait(0.1):
                if cancel_event.is_set(): early_solver.StopSearch(); return
        early_watcher = threading.Thread(target=early_monitor, daemon=True); early_watcher.start()
        try:
            early_status = early_solver.Solve(model)
            if early_status in (cp_model.OPTIMAL, cp_model.FEASIBLE): best[0] = extract(early_solver)
        finally:
            early_done.set(); early_watcher.join()
    reason = "cancelled" if cancel_event.is_set() else "optimal" if status == cp_model.OPTIMAL else "infeasible" if status == cp_model.INFEASIBLE else "time_limit"
    if best[0] is None: raise SolveFailure(reason, f"Scenario {scenario.value}: {reason}; no complete validated schedule available.")
    solution = best[0]
    bound = solver.BestObjectiveBound() / 10 if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    score = solution.validation.soft_scores['objective_score']
    solution.solver_stats = {"elapsed_seconds": time.monotonic() - started, "first_feasible_seconds": first_time[0], "best_score": score,
                             "best_bound": bound, "relative_gap": None if bound is None else max(0, score - bound) / max(1, abs(score)),
                             "optimal": status == cp_model.OPTIMAL, "termination_reason": reason,
                             "model_variables": len(model.Proto().variables), "search_workers": workers,
                             "process_peak_memory_mb": peak_memory_mb()}
    return solution
