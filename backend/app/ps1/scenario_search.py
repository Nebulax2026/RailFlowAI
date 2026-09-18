"""Four search strategies for B/C using main's possession model and validator.

A keeps its existing solver and documented policy. LNS fixes activity/week/ECLO
decisions outside the neighborhood; all group and local-night decisions stay free.
"""
from __future__ import annotations

import math
import random
import threading
import time
from collections import Counter, defaultdict

from ortools.sat.python import cp_model

from app.ps1.exporter import scenario_csvs
from app.ps1.models import AccessAssignment, ContractResult, OccupancyAssignment, Scenario, ScenarioSolution
from app.ps1.safety import legal_mix
from app.ps1.scenario_a.search import OPERATORS, SearchResult
from app.ps1.scoring import delay_coefficient, week_end
from app.ps1.solver import SolveFailure, build_scenario_model
from app.ps1.topology import activity_locations, affected_lines, closure_locations
from app.ps1.validator import validate_exported_csvs


def constructive(instance, scenario, deadline, cancelled, seed=42):
    """Topological earliest placement, legal shared cohorts, optional ECLO.

    No CP-SAT calls: failure means this heuristic found no schedule, never a
    proof of infeasibility. Retry order/ECLO choices only within the same budget.
    """
    work = {a: set(activity_locations(instance, item)) for a, item in instance.activities.items()}
    footprint = {a: work[a] | closure_locations(instance, item) for a, item in instance.activities.items()}
    rng = random.Random(seed)
    for attempt in range(8):
        accesses, finish, groups = [], {}, defaultdict(list)
        fronts, ecweeks = Counter(), defaultdict(set)
        pending = set(instance.activities)
        while pending and time.monotonic() < deadline and not cancelled():
            ready = [a for a in pending if not instance.activities[a].predecessor_activity_id or instance.activities[a].predecessor_activity_id in finish]
            if not ready:
                break
            def priority(aid):
                a = instance.activities[aid]; c = instance.contracts[a.contract_number]
                return (c.planned_completion_date, -delay_coefficient(c, a), -a.total_accesses, aid)
            ready.sort(key=priority)
            aid = ready[0] if attempt < 2 else ready[rng.randrange(min(4, len(ready)))]
            a = instance.activities[aid]; c = instance.contracts[a.contract_number]
            low = max(1, (a.planned_start_date - instance.horizon_start).days // 7 + 1,
                      finish.get(a.predecessor_activity_id, 0) + 1)
            high = instance.horizon_weeks
            if scenario == Scenario.B:
                high = min(high, ((c.planned_completion_date - instance.horizon_start).days + 1) // 7)
            remaining, seq = 2 * a.total_accesses, 0
            for week in range(low, high + 1):
                if cancelled() or time.monotonic() >= deadline:
                    return None
                key = (a.contract_number, a.activity_type, week)
                night = next((n for n in range(1, c.number_of_maximum_access_per_week + 1)
                              if fronts[*key, n] < c.number_of_workfronts), None)
                if night is None:
                    continue
                options = []
                for index, members in enumerate(groups[week]):
                    if legal_mix(instance, [*members, aid]) and set.intersection(work[aid], *(work[m] for m in members)):
                        options.append(index)
                options.append(len(groups[week]))
                chosen = None
                for index in options:
                    trial = [set(m) for m in groups[week]]
                    if index == len(trial): trial.append({aid})
                    else: trial[index].add(aid)
                    used = Counter(loc for members in trial for loc in set.union(*(footprint[m] for m in members)))
                    if scenario == Scenario.B or all(count <= instance.supply[loc].supply_capacity + 1 for loc, count in used.items()):
                        chosen = trial
                        break
                if chosen is None:
                    continue
                # Prefer standard yield; B accelerates when its hard deadline
                # requires it. Retry with early acceleration for resource chains.
                extra = int(remaining > 2 and (attempt % 2 == 1 or (scenario == Scenario.B and remaining > 2 * (high - week + 1))))
                lines = affected_lines(instance, a)
                if extra and scenario == Scenario.C and any(max(ecweeks[line] | {week}) - min(ecweeks[line] | {week}) > 1 for line in lines):
                    extra = 0
                groups[week] = chosen
                fronts[*key, night] += 1
                if extra:
                    for line in lines: ecweeks[line].add(week)
                seq += 1
                accesses.append(AccessAssignment(aid, seq, week, extra, night))
                remaining -= 2 + extra
                if remaining <= 0:
                    finish[aid] = week
                    pending.remove(aid)
                    break
            if remaining > 0:
                break
        if not pending:
            occupancy = [OccupancyAssignment(aid, week, loc, f"g{index}")
                         for week, cohorts in sorted(groups.items()) for index, members in enumerate(cohorts)
                         for aid in sorted(members) for loc in sorted(work[aid])]
            results = []
            for cid, c in instance.contracts.items():
                end = week_end(instance, max(finish[a] for a, item in instance.activities.items() if item.contract_number == cid))
                results.append(ContractResult(scenario.value, cid, end, max(0, (end - c.planned_completion_date).days)))
            solution = ScenarioSolution(scenario, accesses, occupancy, results, None)
            solution.validation = validate_exported_csvs(instance, scenario, scenario_csvs(solution))
            if solution.validation.feasible:
                return solution
    return None


def neighborhood(instance, built, solution, operator, fraction, rng):
    aids = sorted(instance.activities)
    target = max(1, math.ceil(len(aids) * fraction))
    rows = defaultdict(list)
    for row in solution.accesses: rows[row.activity_id].append(row)
    costs = {}
    for aid, a in instance.activities.items():
        c = instance.contracts[a.contract_number]
        costs[aid] = delay_coefficient(c, a) * max(0, (week_end(instance, max(r.week for r in rows[aid])) - c.planned_completion_date).days) / 10 + 5 * sum(r.eclo for r in rows[aid])
    anchor = rng.choices(aids, weights=[1 + costs[a] for a in aids])[0]
    selected = {anchor}
    if operator == "bottleneck":
        usage = solution.validation.detail["location_usage"]
        site = rng.choices(usage, weights=[1 + max(0, u["used"] - u["capacity"]) * 10 + u["used"] for u in usage])[0]
        selected.update(a for a in aids if site["location_id"] in built.footprint[a] and any(abs(r.week - site["week"]) <= 2 for r in rows[a]))
    elif operator == "contract":
        selected.update(a for a in aids if instance.activities[a].contract_number == instance.activities[anchor].contract_number)
    elif operator == "precedence":
        pred = instance.activities[anchor].predecessor_activity_id
        while pred:
            selected.add(pred); pred = instance.activities[pred].predecessor_activity_id
    elif operator == "sharing":
        selected.update(a for a in aids if built.work[a] & built.work[anchor] and legal_mix(instance, [anchor, a]))
    elif operator == "diversify":
        selected = set(rng.sample(aids, target))
    else:
        candidates = [a for a in aids if built.footprint[a] & built.footprint[anchor] or instance.activities[a].contract_number == instance.activities[anchor].contract_number]
        selected.update(sorted(candidates, key=lambda a: -costs[a])[:target])
    # Release entire current shared groups, including groups at other locations.
    # Nights/cohorts remain free globally, so no stale labels constrain repairs.
    groups = defaultdict(set)
    for r in solution.occupancy: groups[r.week, r.co_share_group].add(r.activity_id)
    changed = True
    while changed:
        before = len(selected)
        for members in groups.values():
            if selected & members: selected.update(members)
        changed = len(selected) > before
    if len(selected) < target:
        selected.update(rng.sample(sorted(set(aids) - selected), target - len(selected)))
    return selected


def solve(instance, scenario, config, cancelled=lambda: False, checkpoint=None):
    if scenario not in (Scenario.B, Scenario.C):
        raise ValueError("Use the existing Scenario A solver for A.")
    started = time.monotonic()
    deadline = started + config.time_limit_seconds
    search_deadline = deadline - min(1, config.time_limit_seconds * .08)
    best, bound, first = None, 0.0, None
    status = "no_solution_within_budget"
    trajectory, phases = [], []
    operators = {op: dict(calls=0, seconds=0.0, feasible=0, improvement=0.0, best_updates=0, weight=1.0) for op in OPERATORS}
    rng = random.Random(config.seed)
    stop = threading.Event()

    def summary():
        score = best.validation.soft_scores["objective_score"] if best else None
        return dict(scenario=scenario.value, strategy=config.strategy, status=status, objective=score,
                    global_lower_bound=bound, absolute_gap=None if score is None else max(0, score-bound),
                    time_to_first_feasible=first, elapsed_seconds=time.monotonic()-started,
                    trajectory=list(trajectory), phases=list(phases), operators={op: dict(v) for op, v in operators.items()},
                    policy="local-protection-reservations-v1", official_validator_available=False,
                    bound_scope="Full possession model only; restricted repairs never supply global bounds")

    def accept(candidate):
        nonlocal best, first, status
        report = validate_exported_csvs(instance, scenario, scenario_csvs(candidate))
        if not report.feasible:
            raise SolveFailure("validation_failed", str(report.hard_violations[:3]))
        candidate.validation = report
        score = report.soft_scores["objective_score"]
        if best and score >= best.validation.soft_scores["objective_score"]:
            return
        best = candidate
        first = time.monotonic()-started if first is None else first
        status = "feasible"
        trajectory.append(dict(seconds=time.monotonic()-started, objective=score))
        if checkpoint: checkpoint(best, summary())

    done = threading.Event()
    def monitor():
        while not done.wait(.05):
            if cancelled() or time.monotonic() >= search_deadline:
                stop.set(); return
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        if config.strategy == "greedy" or config.initialization == "greedy_hint":
            candidate = constructive(instance, scenario, search_deadline, stop.is_set, config.seed)
            if candidate: accept(candidate)
        if best and best.validation.soft_scores["objective_score"] == 0:
            status = "optimal_for_policy"
        elif config.strategy != "greedy" and not stop.is_set():
            built = build_scenario_model(instance, scenario, search_deadline-started, started, stop)

            def phase(seconds, relaxed=None, label="global", feasibility=False):
                nonlocal bound, status
                if stop.is_set(): return None
                model = built.model.clone()
                if feasibility: model.clear_objective()
                if best:
                    old = {(r.activity_id, r.week): r for r in best.accesses}
                    for key, var in built.x.items():
                        model.add_hint(var, int(key in old))
                        model.add_hint(built.eclo[key], old[key].eclo if key in old else 0)
                        if relaxed is not None and key[0] not in relaxed:
                            model.add(var == int(key in old))
                            model.add(built.eclo[key] == (old[key].eclo if key in old else 0))
                    model.add(built.primary <= round(best.validation.soft_scores["objective_score"] * 10))
                solver = cp_model.CpSolver()
                solver.parameters.max_time_in_seconds = max(.001, min(seconds, search_deadline-time.monotonic()))
                solver.parameters.num_search_workers = config.workers
                solver.parameters.random_seed = config.seed + len(phases)
                solver.parameters.max_memory_in_mb = config.memory_limit_mb
                solver.parameters.stop_after_first_solution = feasibility
                errors = []
                class Publish(cp_model.CpSolverSolutionCallback):
                    def on_solution_callback(self):
                        try:
                            if not best or self.value(built.primary)/10 < best.validation.soft_scores["objective_score"]:
                                accept(built.extract(self))
                        except Exception as error:
                            errors.append(error); self.stop_search()
                        if stop.is_set(): self.stop_search()
                phase_done = threading.Event()
                def cancel_solver():
                    while not phase_done.wait(.05):
                        if stop.is_set(): solver.stop_search(); return
                thread = threading.Thread(target=cancel_solver, daemon=True); thread.start()
                t = time.monotonic()
                try:
                    result = solver.solve(model, Publish())
                finally:
                    phase_done.set(); thread.join()
                if errors: raise errors[0]
                if result == cp_model.MODEL_INVALID:
                    raise SolveFailure("validation_failed", solver.solution_info())
                if relaxed is None and not feasibility:
                    bound = max(bound, math.ceil(solver.best_objective_bound-1e-6)/10)
                    if result == cp_model.INFEASIBLE and best is None:
                        status = "infeasible_for_policy"
                phases.append(dict(phase=label, seconds=time.monotonic()-t, solver_status=solver.status_name(result),
                                   bound_scope="full_model" if relaxed is None and not feasibility else "not_global"))
                if best and best.validation.soft_scores["objective_score"] <= bound:
                    status = "optimal_for_policy"
                return result

            remaining = search_deadline-time.monotonic()
            if config.initialization == "feasibility":
                phase(min(5, remaining*.2), label="feasibility", feasibility=True)
            remaining = search_deadline-time.monotonic()
            phase(remaining if config.strategy == "integrated" else remaining*config.initial_fraction)
            iteration = stagnation = 0
            while config.strategy in {"alns", "random_lns"} and status not in {"optimal_for_policy", "infeasible_for_policy"} and not stop.is_set():
                iteration += 1
                if best is None or iteration % config.restart_every == 0:
                    phase(config.repair_seconds, label="global_restart"); continue
                op = "diversify" if config.strategy == "random_lns" else rng.choices(OPERATORS, weights=[operators[o]["weight"] for o in OPERATORS])[0]
                fraction = min(config.neighborhood_max, config.neighborhood_min*(1+stagnation/3))
                relaxed = neighborhood(instance, built, best, op, fraction, rng)
                before = best.validation.soft_scores["objective_score"]; t = time.monotonic()
                result = phase(config.repair_seconds, relaxed, op)
                elapsed = time.monotonic()-t
                delta = before-best.validation.soft_scores["objective_score"]
                stats = operators[op]
                stats["calls"] += 1; stats["seconds"] += elapsed
                stats["feasible"] += int(result in (cp_model.FEASIBLE, cp_model.OPTIMAL))
                stats["improvement"] += delta; stats["best_updates"] += int(delta > 0)
                stats["weight"] = max(.2, .75*stats["weight"]+.25*(1+min(20, delta/max(.01,elapsed))))
                stagnation = 0 if delta > 0 else stagnation+1
    except SolveFailure as error:
        if error.reason == "infeasible": status = "infeasible_for_policy"
        elif error.reason not in {"cancelled", "time_limit"}: raise
    finally:
        done.set(); watcher.join()
    if cancelled(): status = "cancelled_with_feasible" if best else "cancelled_without_solution"
    if best:
        best.validation = validate_exported_csvs(instance, scenario, scenario_csvs(best))
        if not best.validation.feasible: raise SolveFailure("validation_failed", "Final CSV validation failed.")
        best.explanations = [f"{config.strategy}: Scenario {scenario.value}, all workloads validated.",
                             "Main's conservative protection policy; official-validator parity is unconfirmed."]
    return SearchResult(best, summary())
