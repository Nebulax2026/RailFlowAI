"""Bounded legacy-model run for comparisons at the same worker/time budget."""
import time
from app.ps1.solver import solve_scenario, SolveFailure
from app.ps1.scenario_a.search import SearchResult


def solve(instance, scenario, config, stop, checkpoint):
    started = time.monotonic()
    best, first = None, None
    trajectory = []

    def diagnostics(status="feasible"):
        stats = best.solver_stats if best else {}
        cost = best.validation.soft_scores["objective_score"] if best else None
        bound = stats.get("best_bound")
        return dict(status=status, scenario=scenario.value, strategy="legacy", objective=cost,
                    global_lower_bound=bound, absolute_gap=None if cost is None or bound is None else max(0, cost-bound),
                    elapsed_seconds=time.monotonic()-started, time_to_first_feasible=first,
                    trajectory=list(trajectory), policy="local-protection-reservations-v1",
                    official_validator_available=False, solver_stats=stats)

    def update(solution):
        nonlocal best, first
        if best and solution.validation.soft_scores["objective_score"] >= best.validation.soft_scores["objective_score"]:
            return
        best = solution
        first = time.monotonic()-started if first is None else first
        trajectory.append(dict(seconds=time.monotonic()-started, objective=best.validation.soft_scores["objective_score"]))
        checkpoint(best, diagnostics())
    try:
        solution = solve_scenario(instance, scenario, config.time_limit_seconds, on_solution=update,
                                  cancel_event=stop, workers=config.workers, seed=config.seed)
        update(solution)
        best = solution
        status = "optimal_for_policy" if solution.solver_stats["optimal"] else "feasible"
    except SolveFailure as error:
        if error.reason not in {"cancelled", "time_limit", "infeasible"}: raise
        status = "infeasible_for_policy" if error.reason == "infeasible" else "feasible" if best else "no_solution_within_budget"
    if stop.is_set(): status = "cancelled_with_feasible" if best else "cancelled_without_solution"
    return SearchResult(best, diagnostics(status))
