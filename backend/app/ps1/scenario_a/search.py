from __future__ import annotations

import math
import random
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Callable

import ortools
from ortools.sat.python import cp_model

from app.ps1.exporter import scenario_csvs
from app.ps1.models import Instance, ScenarioSolution
from app.ps1.scenario_a.model import build_model, greedy
from app.ps1.scenario_a.policy import POLICY_VERSION, SOURCE_REVISION, prepare
from app.ps1.scenario_a.validation import validate_csvs

try:
    import resource
except ImportError:  # Windows has no resource module.
    resource = None


@dataclass(frozen=True)
class SearchConfig:
    strategy: str = "integrated"
    initialization: str = "greedy_hint"
    time_limit_seconds: float = 30
    workers: int = 1
    seed: int = 42
    memory_limit_mb: int = 2048
    initial_fraction: float = 0.4
    repair_seconds: float = 2
    neighborhood_min: float = 0.15
    neighborhood_max: float = 0.7
    restart_every: int = 6

    def __post_init__(self):
        if self.strategy not in {"greedy", "integrated", "random_lns", "alns"}:
            raise ValueError("Unknown Scenario A strategy.")
        if self.initialization not in {"direct", "feasibility", "greedy_hint"}:
            raise ValueError("Unknown initialization.")
        if not 0.2 <= self.time_limit_seconds <= 600 or not 1 <= self.workers <= 8:
            raise ValueError("Use 0.2–600 seconds and 1–8 workers.")
        if not 256 <= self.memory_limit_mb <= 16384 or not 0 <= self.seed <= 2**31 - 1:
            raise ValueError("Invalid memory limit or seed.")
        if not 0 < self.initial_fraction <= 1 or not 0 < self.neighborhood_min <= self.neighborhood_max <= 1:
            raise ValueError("Invalid search fractions.")
        if self.repair_seconds <= 0 or self.restart_every < 1:
            raise ValueError("Invalid repair/restart configuration.")


@dataclass
class SearchResult:
    solution: ScenarioSolution | None
    diagnostics: dict


OPERATORS = ("delay", "bottleneck", "sharing", "precedence", "contract", "diversify")


def solve(instance: Instance, config: SearchConfig = SearchConfig(),
          cancelled: Callable[[], bool] = lambda: False,
          checkpoint: Callable[[ScenarioSolution, dict], None] | None = None) -> SearchResult:
    started = time.monotonic()
    deadline = started + config.time_limit_seconds
    search_deadline = deadline - min(1.0, config.time_limit_seconds * 0.08)
    rng = random.Random(config.seed)
    best, best_cost, first, bound = None, None, None, 0
    trajectory, phases = [], []
    validation_seconds, build_seconds, search_seconds = 0.0, 0.0, 0.0
    operators = {name: dict(calls=0, seconds=0.0, feasible=0, improvement=0.0, best_updates=0, weight=1.0) for name in OPERATORS}
    status = "no_solution_within_budget"

    def summary():
        return {"status": status, "strategy": config.strategy, "config": asdict(config),
                "objective": None if best_cost is None else best_cost / 10,
                "global_lower_bound": bound / 10, "absolute_gap": None if best_cost is None else max(0, best_cost - bound) / 10,
                "bound_scope": f"full model under {POLICY_VERSION}; not an official-validator bound",
                "optimality_scope": "configured specification policy only",
                "time_to_first_feasible": first, "elapsed_seconds": time.monotonic() - started,
                "model_build_seconds": build_seconds, "search_seconds": search_seconds,
                "validation_seconds": validation_seconds, "trajectory": list(trajectory), "phases": list(phases),
                "operators": {k: {**v, "feasible_rate": v["feasible"] / max(1, v["calls"]),
                                  "improvement_per_second": v["improvement"] / max(1e-9, v["seconds"])} for k, v in operators.items()},
                "policy": POLICY_VERSION, "source_revision": SOURCE_REVISION,
                "official_validator_available": False, "ortools_version": ortools.__version__}

    def accept(solution, cost=None):
        nonlocal best, best_cost, first, validation_seconds, status
        t = time.monotonic()
        validation = validate_csvs(instance, scenario_csvs(solution), cost)
        validation_seconds += time.monotonic() - t
        if not validation.feasible:
            raise ValueError(f"Optimizer/CSV validation mismatch: {validation.hard_violations[:3]}")
        solution.validation = validation
        measured = round(validation.soft_scores["objective_score"] * 10)
        if best_cost is not None and measured >= best_cost:
            return False
        best, best_cost = solution, measured
        elapsed = time.monotonic() - started
        first = elapsed if first is None else first
        status = "feasible"
        trajectory.append({"seconds": elapsed, "objective": measured / 10})
        if checkpoint:
            checkpoint(solution, summary())
        return True

    try:
        prep_start = time.monotonic()
        p = prepare(instance)
        preprocessing_seconds = time.monotonic() - prep_start
        # Admissible relaxation: each DAG chain at its earliest start, ignoring
        # all location and contract competition. Costs are nonnegative.
        bound = sum(p.weights[a] * max(0, 7 * (p.earliest[a] + item.total_accesses - 1) - 1
                                          - (instance.contracts[item.contract_number].planned_completion_date - instance.horizon_start).days)
                    for a, item in instance.activities.items())
        if config.strategy == "greedy" or config.initialization == "greedy_hint":
            candidate = greedy(instance, p, search_deadline)
            if candidate:
                accept(candidate)
        if config.strategy == "greedy":
            status = "optimal_for_policy" if best_cost is not None and best_cost == bound else status
        elif best_cost is not None and best_cost == bound:
            status = "optimal_for_policy"
        else:
            t = time.monotonic()
            integrated = build_model(instance, p, search_deadline)
            build_seconds = time.monotonic() - t
            model_error = integrated.model.validate()
            if model_error:
                raise ValueError(model_error)

            def run_phase(seconds, relaxed=None, feasibility=False, label="global"):
                nonlocal bound, status, search_seconds
                if cancelled() or time.monotonic() >= search_deadline:
                    return None
                model = integrated.model.clone()
                if feasibility:
                    model.clear_objective()
                chosen = {(r.activity_id, r.week) for r in best.accesses} if best else set()
                if best:
                    for key, var in integrated.x.items():
                        model.add_hint(var, int(key in chosen))
                        if relaxed is not None and key[0] not in relaxed:
                            model.add(var == int(key in chosen))
                    if not feasibility:
                        model.add(integrated.cost <= best_cost)
                solver = cp_model.CpSolver()
                solver.parameters.max_time_in_seconds = max(0.001, min(seconds, search_deadline - time.monotonic()))
                solver.parameters.num_search_workers = config.workers
                solver.parameters.random_seed = config.seed + len(phases)
                solver.parameters.max_memory_in_mb = config.memory_limit_mb
                solver.parameters.stop_after_first_solution = feasibility

                class Incumbent(cp_model.CpSolverSolutionCallback):
                    def on_solution_callback(self):
                        nonlocal bound
                        if not feasibility and relaxed is None:
                            bound = max(bound, math.ceil(self.best_objective_bound - 1e-6))
                        cost = round(self.value(integrated.cost))
                        if best_cost is None or cost < best_cost:
                            accept(integrated.extract(self.value), cost)
                        if cancelled() or best_cost == bound or time.monotonic() >= search_deadline:
                            self.stop_search()

                done = threading.Event()
                def monitor():
                    while not done.wait(0.05):
                        if cancelled() or time.monotonic() >= search_deadline:
                            solver.stop_search(); return
                watcher = threading.Thread(target=monitor, daemon=True)
                watcher.start()
                phase_start = time.monotonic()
                try:
                    result = solver.solve(model, Incumbent())
                finally:
                    done.set(); watcher.join()
                elapsed = time.monotonic() - phase_start
                search_seconds += elapsed
                phases.append({"phase": label, "seconds": elapsed, "solver_status": solver.status_name(result),
                               "relaxed_activities": len(relaxed) if relaxed is not None else len(instance.activities),
                               "bound_scope": "subproblem_not_global" if relaxed is not None else "full_model"})
                if relaxed is None and not feasibility and result != cp_model.MODEL_INVALID:
                    bound = max(bound, math.ceil(solver.best_objective_bound - 1e-6))
                if result == cp_model.MODEL_INVALID:
                    raise ValueError(solver.solution_info())
                if result == cp_model.INFEASIBLE and relaxed is None and best is None:
                    status = "infeasible_for_policy"
                if best_cost is not None and best_cost <= bound:
                    status = "optimal_for_policy"
                return result

            remaining = max(0, search_deadline - time.monotonic())
            if config.initialization == "feasibility":
                run_phase(min(remaining * 0.2, 5), feasibility=True, label="feasibility")
            remaining = max(0, search_deadline - time.monotonic())
            run_phase(remaining if config.strategy == "integrated" else remaining * config.initial_fraction)
            stagnation = iteration = 0
            while (config.strategy in {"alns", "random_lns"} and status not in {"optimal_for_policy", "infeasible_for_policy"}
                   and not cancelled() and time.monotonic() < search_deadline):
                iteration += 1
                if best is None or iteration % config.restart_every == 0:
                    run_phase(config.repair_seconds, label="global_restart")
                    continue
                op = "diversify" if config.strategy == "random_lns" else rng.choices(OPERATORS, weights=[operators[o]["weight"] for o in OPERATORS])[0]
                fraction = min(config.neighborhood_max, config.neighborhood_min * (1 + stagnation / 3))
                relaxed = neighborhood(instance, p, best, op, fraction, rng)
                before, t = best_cost, time.monotonic()
                result = run_phase(config.repair_seconds, relaxed=relaxed, label=op)
                elapsed = time.monotonic() - t
                delta = (before - best_cost) / 10
                stats = operators[op]
                stats["calls"] += 1; stats["seconds"] += elapsed
                stats["feasible"] += int(result in (cp_model.FEASIBLE, cp_model.OPTIMAL))
                stats["improvement"] += delta; stats["best_updates"] += int(delta > 0)
                reward = 1 + min(20, delta / max(elapsed, 0.01))
                stats["weight"] = max(0.2, 0.75 * stats["weight"] + 0.25 * reward)
                stagnation = 0 if delta > 0 else stagnation + 1
        if cancelled():
            status = "cancelled_with_feasible" if best else "cancelled_without_solution"
        if best:
            # Reparse the final deliverable, even if the incumbent callback did.
            t = time.monotonic()
            best.validation = validate_csvs(instance, scenario_csvs(best), best_cost)
            validation_seconds += time.monotonic() - t
            if not best.validation.feasible:
                raise ValueError("Final CSV validation failed.")
            best.explanations = [f"Scenario A: all {sum(a.total_accesses for a in instance.activities.values())} access units completed.",
                                 f"{config.strategy}: specification cost {best_cost / 10:g}; full-model lower bound {bound / 10:g} under the configured policy.",
                                 "Independently validated against a conservative specification policy. Official validator not supplied."]
    except TimeoutError:
        preprocessing_seconds = locals().get("preprocessing_seconds", time.monotonic() - started)
    except (ValueError, KeyError) as exc:
        diagnostics = summary()
        diagnostics.update(status="input_or_model_error", error=str(exc))
        return SearchResult(best, diagnostics)
    diagnostics = summary()
    diagnostics["preprocessing_seconds"] = preprocessing_seconds
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else 0
    import sys
    diagnostics["peak_rss_mb"] = rss / (1024**2 if sys.platform == "darwin" else 1024)
    diagnostics["deadline_exceeded"] = time.monotonic() > deadline
    return SearchResult(best, diagnostics)


def neighborhood(instance, p, solution, operator, fraction, rng):
    ids = sorted(instance.activities)
    target = max(1, math.ceil(len(ids) * fraction))
    costs = solution.validation.detail.get("activity_costs", {})
    weeks = defaultdict(set)
    for r in solution.accesses:
        weeks[r.activity_id].add(r.week)
    seed = rng.choices(ids, weights=[1 + costs.get(a, 0) for a in ids])[0]
    selected = {seed}
    if operator == "delay":
        related = p.spatial[seed] | p.resources[seed] | p.predecessors[seed] | p.successors[seed]
    elif operator == "bottleneck":
        hotspots = solution.validation.detail.get("capacity_hotspots", [])
        if hotspots:
            h = rng.choice(hotspots)
            related = {a for a in ids if h["location_id"] in p.work[a] | p.reserve[a] and any(abs(w - h["week"]) <= 2 for w in weeks[a])}
        else:
            related = p.spatial[seed]
    elif operator == "sharing":
        related = p.sharing[seed]
    elif operator == "precedence":
        related, pending = set(), [seed]
        while pending:
            a = pending.pop()
            for b in p.predecessors[a] | p.successors[a]:
                if b not in related and b != seed:
                    related.add(b); pending.append(b)
    elif operator == "contract":
        related = p.resources[seed]
    else:
        if rng.random() < 0.5:
            week = rng.randint(1, instance.horizon_weeks)
            related = {a for a in ids if any(abs(w - week) <= 1 for w in weeks[a])}
        else:
            related = p.spatial[seed] | p.sharing[seed] | p.resources[seed]
    pool = sorted(related - selected)
    rng.shuffle(pool)
    selected.update(pool[:max(0, target - len(selected))])
    rest = sorted(set(ids) - selected); rng.shuffle(rest)
    selected.update(rest[:max(0, target - len(selected))])
    # Release every existing shared-group member transitively. All location slot
    # and local night variables remain free globally, even outside this closure.
    groups = defaultdict(set)
    for r in solution.occupancy:
        groups[r.location_id, r.week, r.co_share_group].add(r.activity_id)
    changed = True
    while changed:
        old = len(selected)
        for members in groups.values():
            if members & selected:
                selected.update(members)
        changed = len(selected) != old
    return selected
