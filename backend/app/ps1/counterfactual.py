"""Bounded, non-mutating counterfactual checks for schedule explanations."""
from __future__ import annotations

from collections import defaultdict
import threading
import time

from ortools.sat.python import cp_model

from app.ps1.solver import SolveFailure, build_scenario_model


# An explanation must never compete with production planning runs. One small
# check at a time is enough for an interactive answer and avoids an unbounded
# model-controlled solver surface.
_one_check_at_a_time = threading.BoundedSemaphore(1)
MAX_SECONDS = 4.0


def _weeks(solution, activity_id: str) -> list[int]:
    return sorted(row.week for row in solution.accesses if row.activity_id == activity_id)


def _changed_activities(baseline, candidate) -> list[str]:
    before, after = defaultdict(list), defaultdict(list)
    for row in baseline.accesses:
        before[row.activity_id].append((row.week, row.eclo, row.access_night))
    for row in candidate.accesses:
        after[row.activity_id].append((row.week, row.eclo, row.access_night))
    return [aid for aid in sorted(set(before) | set(after)) if sorted(before[aid]) != sorted(after[aid])]


def evaluate_activity_boundary(instance, scenario, baseline, activity_id: str, boundary: str,
                               target_week: int, budget_seconds: float = MAX_SECONDS) -> dict:
    """Force one activity start or finish week, then independently validate it.

    The caller keeps the result ephemeral. `feasible` means the generated CSV
    passed the application's independent validator; it is not an official
    validator-parity claim. A time-limited/unknown result is deliberately not
    treated as evidence that the alternative is impossible.
    """
    if activity_id not in instance.activities:
        return {"status": "invalid", "error": "Unknown activity ID."}
    if boundary not in {"start", "finish"}:
        return {"status": "invalid", "error": "Boundary must be start or finish."}
    if not isinstance(target_week, int) or not 1 <= target_week <= instance.horizon_weeks:
        return {"status": "invalid", "error": "Target week is outside the planning horizon."}
    if not _one_check_at_a_time.acquire(blocking=False):
        return {"status": "busy", "error": "Another counterfactual check is running. Retry shortly."}

    started = time.monotonic()
    try:
        built = build_scenario_model(instance, scenario, budget_seconds, started, threading.Event())
        variable = built.starts[activity_id] if boundary == "start" else built.finishes[activity_id]
        built.model.Add(variable == target_week)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.01, budget_seconds - (time.monotonic() - started))
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        status = solver.Solve(built.model)
        elapsed = round(time.monotonic() - started, 3)
        constraint = f"{activity_id} {boundary} in week {target_week}"
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {
                "status": "infeasible" if status == cp_model.INFEASIBLE else "unknown",
                "constraint": constraint,
                "solver_status": solver.StatusName(status),
                "elapsed_seconds": elapsed,
                "note": ("No schedule satisfies this forced timing under the modeled constraints."
                         if status == cp_model.INFEASIBLE else
                         "The bounded check did not find a validated alternative; this is not infeasibility evidence."),
            }
        candidate = built.extract(solver)
        safety = candidate.validation.detail.get("safety_status")
        if not candidate.validation.feasible or safety != "verified":
            return {"status": "invalid", "constraint": constraint, "elapsed_seconds": elapsed,
                    "note": "The candidate did not pass independent validation; no conclusion is drawn."}
        baseline_score = baseline.validation.soft_scores["objective_score"]
        candidate_score = candidate.validation.soft_scores["objective_score"]
        contract_id = instance.activities[activity_id].contract_number
        old_contract = next(row for row in baseline.results if row.contract_number == contract_id)
        new_contract = next(row for row in candidate.results if row.contract_number == contract_id)
        changed = _changed_activities(baseline, candidate)
        return {
            "status": "feasible", "constraint": constraint, "elapsed_seconds": elapsed,
            "validation_status": "verified", "baseline": {
                "objective_score": baseline_score, "activity_weeks": _weeks(baseline, activity_id),
                "contract_completion": str(old_contract.simulated_completion_date), "contract_overrun_days": old_contract.overrun_days,
            },
            "counterfactual": {
                "objective_score": candidate_score, "activity_weeks": _weeks(candidate, activity_id),
                "contract_completion": str(new_contract.simulated_completion_date), "contract_overrun_days": new_contract.overrun_days,
            },
            "score_delta": candidate_score - baseline_score,
            "changed_activity_count": len(changed), "changed_activity_ids": changed[:25],
            "note": "A separate bounded solve and independent CSV validation produced this comparison. It changes no saved schedule.",
        }
    except SolveFailure as error:
        return {"status": "unknown", "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 3),
                "note": "The bounded check could not establish a validated alternative."}
    except Exception:
        return {"status": "unknown", "elapsed_seconds": round(time.monotonic() - started, 3),
                "note": "The counterfactual check failed safely; no conclusion is drawn."}
    finally:
        _one_check_at_a_time.release()
