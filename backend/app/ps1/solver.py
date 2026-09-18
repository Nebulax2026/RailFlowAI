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


def solve_scenario(instance, scenario, time_limit_seconds=30.0, *, incumbent=None, on_solution=None,
                   cancel_event=None, disruption=None):
    started = time.monotonic()
    if incumbent:
        from app.ps1.exporter import scenario_csvs
        report = validate_exported_csvs(instance, scenario, scenario_csvs(incumbent))
        if not report.feasible:
            if disruption: raise SolveFailure("validation_failed", "Replanning baseline fails current CSV validation.")
            incumbent = None
        else:
            incumbent.validation = report
    cancel_event = cancel_event or threading.Event()
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
                choices.append(choice); by_contract_night[activity.contract_number, activity.activity_type, week, night].append(choice)
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
    for (cid, activity_type, week, night), terms in by_contract_night.items():
        model.Add(sum(terms) <= instance.contracts[cid].number_of_workfronts)

    # Groups are independent at each location/week, as in the official CSV.
    patterns = []
    at_location = defaultdict(list)
    for aid, locations in work.items():
        for loc in locations: at_location[loc].append(aid)
    for loc, ids in sorted(at_location.items()):
        for size in range(1, min(4, len(ids)) + 1):
            for members in itertools.combinations(sorted(ids), size):
                check_budget()
                if legal_mix(instance, members): patterns.append((loc, members))
    group_vars = {}; covers = defaultdict(list); usage = defaultdict(list)
    shared_terms = defaultdict(list)
    for index, (loc, members) in enumerate(patterns):
        check_budget()
        low = max(windows[a][0] for a in members); high = min(windows[a][1] for a in members)
        for week in range(low, high + 1):
            selected = group_vars[index, week] = model.NewBoolVar(f"possession_{index}_{week}")
            for aid in members: covers[aid, week, loc].append(selected)
            for pair in itertools.combinations(members, 2): shared_terms[*pair, week, loc].append(selected)
            usage[loc, week].append(selected)
    for (aid, week), selected in x.items():
        for loc in work[aid]: model.Add(sum(covers[aid, week, loc]) == selected)
    for (loc, week), terms in usage.items():
        nominal = instance.supply[loc].supply_capacity
        if scenario != Scenario.B: model.Add(sum(terms) <= nominal + int(scenario == Scenario.C))
        if (disruption and loc == disruption.location_id
                and disruption.start_week <= week <= disruption.end_week):
            model.Add(sum(terms) <= disruption.capacity)
        if scenario != Scenario.A:
            excess = model.NewIntVar(0, len(terms), f"excess_{loc}_{week}")
            model.AddMaxEquality(excess, [0, sum(terms) - nominal]); objective.append(70 * excess)
    # One physical night per access, consistently across the whole work span.
    # Local indices remain local: an injective mapping links each contract/type's
    # granted nights to the seven nights of a calendar week.
    physical = {key: model.NewIntVar(1, 7, f"physical_{key[0]}_{key[1]}") for key in x}
    mappings = {}
    for cid, kind, week, night in by_contract_night:
        mappings[cid, kind, week, night] = model.NewIntVar(1, 7, f"map_{cid}_{kind}_{week}_{night}")
    mapping_sets = defaultdict(list)
    for (cid, kind, week, night), var in mappings.items(): mapping_sets[cid, kind, week].append(var)
    for variables in mapping_sets.values():
        model.AddAllDifferent(variables)
        # Generated local indices are anonymous accounting labels. Ordering their
        # physical mappings removes equivalent label permutations. Replanning
        # preserves existing labels, so it must not impose this symmetry break.
        if not disruption:
            for previous, following in zip(variables, variables[1:]): model.Add(previous < following)
    for (aid, week, night), choice in local_nights.items():
        activity = instance.activities[aid]
        model.Add(physical[aid, week] == mappings[activity.contract_number, activity.activity_type, week, night]).OnlyEnforceIf(choice)
    for left, right in itertools.combinations(sorted(instance.activities), 2):
        check_budget()
        common = work[left] & work[right]
        protection_hits = (footprint[left] & footprint[right]) - common
        if not common and not protection_hits: continue
        for week in range(max(windows[left][0], windows[right][0]), min(windows[left][1], windows[right][1]) + 1):
            active = [x[left, week], x[right, week]]
            if common:
                same = model.NewBoolVar(f"same_night_{left}_{right}_{week}")
                model.Add(physical[left, week] == physical[right, week]).OnlyEnforceIf([*active, same])
                model.Add(physical[left, week] != physical[right, week]).OnlyEnforceIf([*active, same.Not()])
                model.Add(same <= x[left, week]); model.Add(same <= x[right, week])
                # Shared at one work location implies shared at all overlapping
                # work locations. Labels themselves need not match across sites.
                for loc in common: model.Add(sum(shared_terms[left, right, week, loc]) == same)
            else:
                # No direct co-sharing exemption, including buffer/buffer hits.
                model.Add(physical[left, week] != physical[right, week]).OnlyEnforceIf(active)
    primary = sum(objective)
    churn_terms = []
    if incumbent:
        old = {(r.activity_id, r.week): r for r in incumbent.accesses}
        for key, var in x.items():
            value = int(key in old); model.AddHint(var, value)
            if disruption:
                if key[1] < disruption.start_week: model.Add(var == value)
                else: churn_terms.append(100 * ((1 - var) if value else var))
        for key, var in eclo.items():
            value = old[key].eclo if key in old else 0; model.AddHint(var, value)
            if disruption:
                if key[1] < disruption.start_week: model.Add(var == value)
                else: churn_terms.append(20 * ((1 - var) if value else var))
        for (aid, week, night), var in local_nights.items():
            value = int((aid, week) in old and old[aid, week].access_night == night); model.AddHint(var, value)
            if disruption:
                if week < disruption.start_week: model.Add(var == value)
                else: churn_terms.append(5 * ((1 - var) if value else var))
        old_groups = defaultdict(set)
        for row in incumbent.occupancy: old_groups[row.location_id, row.week, row.co_share_group].add(row.activity_id)
        old_patterns = {(loc, tuple(sorted(ids)), week) for (loc, week, _label), ids in old_groups.items()}
        for (index, week), var in group_vars.items():
            loc, members = patterns[index]
            value = int((loc, members, week) in old_patterns); model.AddHint(var, value)
            if disruption:
                if week < disruption.start_week: model.Add(var == value)
                else: churn_terms.append((1 - var) if value else var)
    churn = sum(churn_terms)
    max_churn = 100 * len(x) + 20 * len(eclo) + 5 * len(local_nights) + len(group_vars)
    search_objective = primary * (max_churn + 1) + churn if disruption else primary
    model.Minimize(search_objective)

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
                loc, members = patterns[index]
                for aid in members: occupancy.append(OccupancyAssignment(aid, week, loc, f"p{index}"))
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
        if disruption:
            solution.solver_stats["churn_score"] = reader.Value(churn)
        solution.explanations = [f"All {len(instance.activities)} activities meet their required workload.",
                                 f"{solution.validation.soft_scores['contracts_overrunning']} contracts finish after their planned date.",
                                 "Supply counts work groups only. CSV validation reconstructs a consistent seven-night assignment across contracts; exact maintenance dates are not provided by the input."]
        return solution

    best = [None if disruption else incumbent]
    best_rank = [None if disruption or not incumbent else (round(10 * incumbent.validation.soft_scores['objective_score']), 0)]
    first_time = [None]; callback_error = [None]
    class Publish(cp_model.CpSolverSolutionCallback):
        def __init__(self): super().__init__(); self.last = -math.inf
        def on_solution_callback(self):
            if cancel_event.is_set(): self.StopSearch(); return
            if time.monotonic() - self.last < 2: return
            rank = (self.Value(primary), self.Value(churn) if disruption else 0)
            if best_rank[0] is not None and rank >= best_rank[0]: return
            try:
                solution = extract(self)
                if first_time[0] is None: first_time[0] = time.monotonic() - started
                solution.solver_stats = {"elapsed_seconds": time.monotonic() - started, "best_score": solution.validation.soft_scores['objective_score'], "best_bound": self.BestObjectiveBound() / 10, "optimal": False, "first_feasible_seconds": first_time[0]}
                best[0] = solution
                best_rank[0] = rank
                if on_solution: on_solution(solution)
            except Exception as error:
                callback_error[0] = error; self.StopSearch()
            self.last = time.monotonic()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.01, time_limit_seconds - (time.monotonic() - started))
    solver.parameters.num_search_workers = 8; solver.parameters.random_seed = 42
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
        rank = (solver.Value(primary), solver.Value(churn) if disruption else 0)
        if best_rank[0] is None or rank <= best_rank[0]: best[0] = candidate; best_rank[0] = rank
        if first_time[0] is None: first_time[0] = time.monotonic() - started
    # Lexicographic second pass only after proving the primary optimum.
    remaining = time_limit_seconds - (time.monotonic() - started)
    if not disruption and status == cp_model.OPTIMAL and remaining > 0.1 and not cancel_event.is_set():
        model.Add(primary == round(solver.ObjectiveValue()))
        model.Minimize(sum(week * var for (aid, week), var in x.items()))
        early_solver = cp_model.CpSolver()
        early_solver.parameters.max_time_in_seconds = remaining
        early_solver.parameters.num_search_workers = 8
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
    bound = (solver.BestObjectiveBound() / 10
             if not disruption and status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None)
    score = solution.validation.soft_scores['objective_score']
    solution.solver_stats = {"elapsed_seconds": time.monotonic() - started, "first_feasible_seconds": first_time[0], "best_score": score,
                             "best_bound": bound, "relative_gap": None if bound is None else max(0, score - bound) / max(1, abs(score)),
                             "optimal": status == cp_model.OPTIMAL, "termination_reason": reason,
                             "model_variables": len(model.Proto().variables), "search_workers": 8,
                             "process_peak_memory_mb": peak_memory_mb()}
    if disruption:
        solution.solver_stats["churn_score"] = best_rank[0][1] if best_rank[0] else None
    return solution
