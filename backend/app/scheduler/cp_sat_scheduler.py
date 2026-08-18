from dataclasses import dataclass
from datetime import datetime, time, timedelta

from ortools.sat.python import cp_model

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduledWork
from app.scheduler.horizon import move_penalty
from app.scheduler.objective_profiles import OBJECTIVE_PROFILES
from app.settings import cp_sat_time_limit_seconds
from app.storage import SCHEDULED_WORK

ENGINEERING_START = time(9, 0)
ENGINEERING_END = time(18, 0)

MAX_PROFILE_WEIGHT = max(weight for profile in OBJECTIVE_PROFILES.values() for weight in profile.values())
MAX_PRIORITY = 5


def _completion_weight(horizon_bound: int) -> int:
    """A per-request reward large enough that scheduling a job always beats dropping
    it, no matter how large the other soft penalties on that job grow. Otherwise a
    tight, high-priority profile could make delaying a job look "more expensive" than
    leaving it unscheduled, which would silently drop schedulable work."""
    day_bound = horizon_bound + 2 * 24 * 60
    worst_case_penalty = MAX_PROFILE_WEIGHT * MAX_PRIORITY * (horizon_bound + 2 * day_bound)
    return worst_case_penalty + 100_000


class SchedulingInfeasibleError(RuntimeError):
    """Raised when no arrangement can satisfy the mandatory (locked) baseline work."""

    def __init__(self, blockers: list[str]):
        super().__init__("No feasible schedule exists for the locked work in this batch.")
        self.blockers = blockers


@dataclass
class _RequestVars:
    request: MaintenanceRequest
    start: cp_model.IntVar
    end: cp_model.IntVar
    presence: cp_model.IntVar | None
    interval: cp_model.IntervalVar


def optimise_schedule(
    requests: list[MaintenanceRequest],
    option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION,
    time_limit_seconds: float | None = None,
) -> list[ScheduledWork]:
    if option == ScheduleOption.REQUESTED_SLOT:
        option = ScheduleOption.MINIMUM_DISRUPTION
    if not requests:
        return []

    profile = OBJECTIVE_PROFILES[option]
    origin = _origin(requests)
    horizon_bound = max(_minutes(request.deadline, origin) for request in requests) + 1
    completion_weight = _completion_weight(horizon_bound)

    model = cp_model.CpModel()
    request_vars = {request.request_id: _build_request_vars(model, request, origin) for request in requests}

    _add_resource_constraints(model, request_vars, requests)
    _add_dependency_constraints(model, request_vars)

    objective_terms: list[cp_model.LinearExprT] = []
    for request in requests:
        objective_terms.extend(
            _objective_terms_for(
                model, request, request_vars[request.request_id], profile, origin, horizon_bound, completion_weight
            )
        )
    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds if time_limit_seconds is not None else cp_sat_time_limit_seconds()
    # Single worker with a fixed seed keeps demo runs reproducible: the plan's seeded
    # demo must produce the same schedule on every run.
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SchedulingInfeasibleError(_locked_blockers(requests))

    return _extract_schedule(solver, request_vars, requests, option, origin)


def _origin(requests: list[MaintenanceRequest]) -> datetime:
    candidates = [request.earliest_start for request in requests]
    for request in requests:
        if request.fixed_start:
            candidates.append(request.fixed_start)
        baseline = SCHEDULED_WORK.get(request.request_id)
        if baseline:
            candidates.append(baseline.start_time)
    return min(candidates)


def _minutes(moment: datetime, origin: datetime) -> int:
    return int((moment - origin).total_seconds() // 60)


def _from_minutes(minutes: int, origin: datetime) -> datetime:
    return origin + timedelta(minutes=minutes)


def _build_request_vars(model: cp_model.CpModel, request: MaintenanceRequest, origin: datetime) -> _RequestVars:
    rid = request.request_id
    duration = request.duration_minutes

    if request.locked and request.fixed_start and request.fixed_end:
        start_value = _minutes(request.fixed_start, origin)
        end_value = _minutes(request.fixed_end, origin)
        start = model.NewConstant(start_value)
        end = model.NewConstant(end_value)
        interval = model.NewIntervalVar(start, end_value - start_value, end, f"interval_{rid}")
        return _RequestVars(request=request, start=start, end=end, presence=None, interval=interval)

    earliest = _minutes(request.earliest_start, origin)
    deadline = max(_minutes(request.deadline, origin), earliest)
    start = model.NewIntVar(earliest, deadline, f"start_{rid}")
    end = model.NewIntVar(earliest, deadline, f"end_{rid}")
    presence = model.NewBoolVar(f"present_{rid}")
    interval = model.NewOptionalIntervalVar(start, duration, end, presence, f"interval_{rid}")
    return _RequestVars(request=request, start=start, end=end, presence=presence, interval=interval)


def _add_resource_constraints(
    model: cp_model.CpModel,
    request_vars: dict[str, _RequestVars],
    requests: list[MaintenanceRequest],
) -> None:
    track_groups: dict[str, list[cp_model.IntervalVar]] = {}
    crew_groups: dict[str, list[cp_model.IntervalVar]] = {}
    equipment_groups: dict[str, list[cp_model.IntervalVar]] = {}

    for request in requests:
        interval = request_vars[request.request_id].interval
        track_groups.setdefault(request.track_sector, []).append(interval)
        for crew in request.required_crew:
            crew_groups.setdefault(crew, []).append(interval)
        for equipment in request.required_equipment:
            equipment_groups.setdefault(equipment, []).append(interval)

    for intervals in (*track_groups.values(), *crew_groups.values(), *equipment_groups.values()):
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)


def _add_dependency_constraints(model: cp_model.CpModel, request_vars: dict[str, _RequestVars]) -> None:
    for vars_ in request_vars.values():
        for dependency_id in vars_.request.dependencies:
            dep_vars = request_vars.get(dependency_id)
            if dep_vars is None:
                continue

            order_constraint = model.Add(dep_vars.end <= vars_.start)
            enforce_literals = [literal for literal in (vars_.presence, dep_vars.presence) if literal is not None]
            if enforce_literals:
                order_constraint.OnlyEnforceIf(enforce_literals)

            if vars_.presence is not None and dep_vars.presence is not None:
                model.AddImplication(vars_.presence, dep_vars.presence)
            elif vars_.presence is None and dep_vars.presence is not None:
                model.Add(dep_vars.presence == 1)


def _objective_terms_for(
    model: cp_model.CpModel,
    request: MaintenanceRequest,
    vars_: _RequestVars,
    profile: dict[str, int],
    origin: datetime,
    horizon_bound: int,
    completion_weight: int,
) -> list[cp_model.LinearExprT]:
    if vars_.presence is None:
        return []

    # Reward is priority-weighted: when resource capacity forces a drop, the tie must
    # fall on the lowest-priority job, not on whichever job happens to be cheapest to
    # delay (which would otherwise tend to be the highest-priority one).
    terms: list[cp_model.LinearExprT] = [
        completion_weight * request.priority * vars_.presence,
        profile["completion"] * vars_.presence,
    ]

    earliest_minutes = _minutes(request.earliest_start, origin)
    delay = model.NewIntVar(0, horizon_bound, f"delay_{request.request_id}")
    model.Add(delay == vars_.start - earliest_minutes).OnlyEnforceIf(vars_.presence)
    model.Add(delay == 0).OnlyEnforceIf(vars_.presence.Not())
    terms.append(-profile["priority_delay"] * request.priority * delay)

    day = request.earliest_start.date()
    day_start_minutes = _minutes(datetime.combine(day, ENGINEERING_START), origin)
    day_end_minutes = _minutes(datetime.combine(day, ENGINEERING_END), origin)
    # Day boundaries are anchored to absolute clock time, so their distance from the
    # scheduling origin can exceed the deadline-derived horizon_bound; give these
    # variables their own generous domain instead of reusing horizon_bound directly.
    day_bound = horizon_bound + 2 * 24 * 60
    early = model.NewIntVar(0, day_bound, f"early_{request.request_id}")
    late = model.NewIntVar(0, day_bound, f"late_{request.request_id}")
    model.AddMaxEquality(early, [0, day_start_minutes - vars_.start])
    model.AddMaxEquality(late, [0, vars_.end - day_end_minutes])
    terms.append(-profile["overtime"] * (early + late))

    baseline = SCHEDULED_WORK.get(request.request_id)
    if baseline is not None:
        baseline_start_minutes = _minutes(baseline.start_time, origin)
        penalty_weight = move_penalty(baseline)
        moved = model.NewBoolVar(f"moved_{request.request_id}")
        model.Add(vars_.start == baseline_start_minutes).OnlyEnforceIf([vars_.presence, moved.Not()])
        model.Add(moved == 1).OnlyEnforceIf(vars_.presence.Not())
        terms.append(-profile["approved_change"] * penalty_weight * moved)

    return terms


def _extract_schedule(
    solver: cp_model.CpSolver,
    request_vars: dict[str, _RequestVars],
    requests: list[MaintenanceRequest],
    option: ScheduleOption,
    origin: datetime,
) -> list[ScheduledWork]:
    scheduled: list[ScheduledWork] = []
    for request in requests:
        vars_ = request_vars[request.request_id]
        if vars_.presence is not None and not solver.BooleanValue(vars_.presence):
            continue

        start_time = _from_minutes(solver.Value(vars_.start), origin)
        end_time = _from_minutes(solver.Value(vars_.end), origin)
        changed = start_time != request.earliest_start

        scheduled.append(
            ScheduledWork(
                schedule_id=f"schedule-{option.value}",
                request_id=request.request_id,
                start_time=start_time,
                end_time=end_time,
                assigned_crew=request.required_crew,
                assigned_equipment=request.required_equipment,
                track_sector=request.track_sector,
                status=ApprovalStatus.LOCKED if request.locked else ApprovalStatus.SCHEDULED,
                changed_from_original=changed,
                change_reason=(
                    "Placed by the CP-SAT solver to satisfy resource, dependency, and deadline "
                    "constraints while honouring the selected optimisation profile."
                    if changed
                    else None
                ),
            )
        )
    return scheduled


def _locked_blockers(requests: list[MaintenanceRequest]) -> list[str]:
    locked_items = [
        ScheduledWork(
            schedule_id="locked-baseline",
            request_id=request.request_id,
            start_time=request.fixed_start,
            end_time=request.fixed_end,
            assigned_crew=request.required_crew,
            assigned_equipment=request.required_equipment,
            track_sector=request.track_sector,
            status=ApprovalStatus.LOCKED,
        )
        for request in requests
        if request.locked and request.fixed_start and request.fixed_end
    ]
    conflicts = detect_conflicts(locked_items, requests)
    if conflicts:
        return [conflict.explanation for conflict in conflicts]
    return ["No arrangement satisfies the locked baseline together with the requested deadlines and dependencies."]
