from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import BlockedTimeSlot, MaintenanceRequest, ScheduledWork
from app.repositories import blocked_time_slot_repository, schedule_repository, scheduling_settings_repository
from app.scheduler.policy import is_frozen_work, is_planning_eligible
from app.scheduler.time_windows import align_to_engineering_window

SOLVER_TIME_LIMIT_SECONDS = 5.0
SLOT_MINUTES = 5
EARLY_START_WEIGHT = 20
PRIORITY_DELAY_WEIGHT = 3
MOVEMENT_WEIGHT = 8
FROZEN_MOVEMENT_WEIGHT = 1000
MISSING_CREW_BREAK_WEIGHT = 500


def optimise_schedule(
    requests: list[MaintenanceRequest],
    option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION,
    blocked_slots: list[BlockedTimeSlot] | None = None,
) -> list[ScheduledWork]:
    settings = scheduling_settings_repository.get()
    active_blocks = blocked_slots if blocked_slots is not None else blocked_time_slot_repository.list(active_only=True)
    eligible = [request for request in requests if request.locked or is_planning_eligible(request, settings)]
    if not eligible:
        return []

    windows = {request.request_id: _request_window(request) for request in eligible}
    if any(start > latest for start, latest in windows.values()):
        return []

    origin = min(start for start, _ in windows.values())
    horizon = max(latest + timedelta(minutes=request.duration_minutes) for request in eligible for _, latest in [windows[request.request_id]])
    model = cp_model.CpModel()
    current_by_request = {item.request_id: item for item in schedule_repository.list()}

    starts: dict[str, cp_model.IntVar] = {}
    ends: dict[str, cp_model.IntVar] = {}
    intervals: dict[str, cp_model.IntervalVar] = {}

    for request in eligible:
        earliest_minute, latest_start_minute = windows[request.request_id]
        start_lb = _to_slot(origin, earliest_minute)
        start_ub = _to_slot(origin, latest_start_minute)
        duration_slots = _duration_slots(request.duration_minutes)
        start = model.NewIntVar(start_lb, start_ub, f"start_{request.request_id}")
        end = model.NewIntVar(start_lb + duration_slots, start_ub + duration_slots, f"end_{request.request_id}")
        interval = model.NewIntervalVar(start, duration_slots, end, f"interval_{request.request_id}")
        starts[request.request_id] = start
        ends[request.request_id] = end
        intervals[request.request_id] = interval

        current = current_by_request.get(request.request_id)
        if request.locked and request.fixed_start and request.fixed_end:
            model.Add(start == _to_slot(origin, request.fixed_start))
            model.Add(end == _to_slot(origin, request.fixed_end))
    _add_resource_no_overlap(model, eligible, intervals)
    _add_block_constraints(model, eligible, active_blocks, starts, ends, origin)
    _add_dependency_constraints(model, eligible, starts, ends)

    objective_terms: list[cp_model.LinearExpr] = []
    for request in eligible:
        earliest_slot = _to_slot(origin, windows[request.request_id][0])
        delay = model.NewIntVar(0, max(0, _to_slot(origin, horizon) - earliest_slot), f"delay_{request.request_id}")
        model.Add(delay == starts[request.request_id] - earliest_slot)
        objective_terms.append(delay * _delay_weight(request, option))

        current = current_by_request.get(request.request_id)
        if current:
            movement = model.NewIntVar(0, _to_slot(origin, horizon), f"movement_{request.request_id}")
            model.AddAbsEquality(movement, starts[request.request_id] - _to_slot(origin, current.start_time))
            weight = FROZEN_MOVEMENT_WEIGHT if is_frozen_work(current, settings) else MOVEMENT_WEIGHT
            if option == ScheduleOption.MINIMUM_DISRUPTION:
                weight *= 2
            objective_terms.append(movement * weight)

    objective_terms.extend(_add_long_crew_break_preferences(model, eligible, starts, ends))
    model.Minimize(sum(objective_terms) if objective_terms else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []

    scheduled: list[ScheduledWork] = []
    for request in sorted(eligible, key=lambda item: solver.Value(starts[item.request_id])):
        start_time = _from_slot(origin, solver.Value(starts[request.request_id]))
        end_time = start_time + timedelta(minutes=request.duration_minutes)
        current = current_by_request.get(request.request_id)
        status_value = ApprovalStatus.LOCKED if request.locked else ApprovalStatus.SCHEDULED
        if current and current.status == ApprovalStatus.LOCKED and current.start_time == start_time and current.end_time == end_time:
            status_value = ApprovalStatus.LOCKED
        scheduled.append(
            ScheduledWork(
                schedule_id=f"schedule-{option.value}",
                request_id=request.request_id,
                start_time=start_time,
                end_time=end_time,
                assigned_crew=request.required_crew,
                assigned_equipment=request.required_equipment,
                track_sector=request.track_sector,
                status=status_value,
                changed_from_original=start_time != request.earliest_start,
                change_reason=(
                    "Moved from earliest start to satisfy resource, freeze, dependency, or working-window constraints."
                    if start_time != request.earliest_start
                    else None
                ),
            )
        )
    return scheduled


def _request_window(request: MaintenanceRequest) -> tuple[datetime, datetime]:
    start = request.fixed_start or align_to_engineering_window(request.earliest_start, request.duration_minutes, request.deadline)
    if start + timedelta(minutes=request.duration_minutes) > request.deadline:
        start = request.earliest_start
    latest_start = (request.fixed_end - timedelta(minutes=request.duration_minutes)) if request.fixed_end else request.deadline - timedelta(minutes=request.duration_minutes)
    return start, latest_start


def _to_slot(origin: datetime, value: datetime) -> int:
    return round((value - origin).total_seconds() / 60 / SLOT_MINUTES)


def _from_slot(origin: datetime, slot: int) -> datetime:
    return origin + timedelta(minutes=slot * SLOT_MINUTES)


def _duration_slots(duration_minutes: int) -> int:
    return max(1, round(duration_minutes / SLOT_MINUTES))


def _delay_weight(request: MaintenanceRequest, option: ScheduleOption) -> int:
    if option == ScheduleOption.CRITICAL_WORK_FIRST:
        return EARLY_START_WEIGHT + request.priority * PRIORITY_DELAY_WEIGHT * 2
    if option == ScheduleOption.MAXIMUM_COMPLETION:
        return EARLY_START_WEIGHT // 2 + request.priority
    return EARLY_START_WEIGHT + request.priority * PRIORITY_DELAY_WEIGHT


def _add_resource_no_overlap(
    model: cp_model.CpModel,
    requests: list[MaintenanceRequest],
    intervals: dict[str, cp_model.IntervalVar],
) -> None:
    grouped: dict[str, list[cp_model.IntervalVar]] = {}
    for request in requests:
        resources = [f"track:{request.track_sector}"]
        resources.extend(f"crew:{crew}" for crew in request.required_crew)
        resources.extend(f"equipment:{equipment}" for equipment in request.required_equipment)
        for resource in resources:
            grouped.setdefault(resource, []).append(intervals[request.request_id])
    for resource_intervals in grouped.values():
        if len(resource_intervals) > 1:
            model.AddNoOverlap(resource_intervals)


def _add_dependency_constraints(
    model: cp_model.CpModel,
    requests: list[MaintenanceRequest],
    starts: dict[str, cp_model.IntVar],
    ends: dict[str, cp_model.IntVar],
) -> None:
    request_ids = {request.request_id for request in requests}
    for request in requests:
        for dependency_id in request.dependencies:
            if dependency_id in request_ids:
                model.Add(ends[dependency_id] <= starts[request.request_id])


def _add_block_constraints(
    model: cp_model.CpModel,
    requests: list[MaintenanceRequest],
    blocks: list[BlockedTimeSlot],
    starts: dict[str, cp_model.IntVar],
    ends: dict[str, cp_model.IntVar],
    origin: datetime,
) -> None:
    for request in requests:
        for block in blocks:
            if request.track_sector not in block.track_sectors:
                continue
            before = model.NewBoolVar(f"{request.request_id}_before_{block.block_id}")
            after = model.NewBoolVar(f"{request.request_id}_after_{block.block_id}")
            model.Add(ends[request.request_id] <= _to_slot(origin, block.start_time)).OnlyEnforceIf(before)
            model.Add(starts[request.request_id] >= _to_slot(origin, block.end_time)).OnlyEnforceIf(after)
            model.AddBoolOr([before, after])


def _add_long_crew_break_preferences(
    model: cp_model.CpModel,
    requests: list[MaintenanceRequest],
    starts: dict[str, cp_model.IntVar],
    ends: dict[str, cp_model.IntVar],
) -> list[cp_model.LinearExpr]:
    penalty_terms: list[cp_model.LinearExpr] = []
    for index, left in enumerate(requests):
        for right in requests[index + 1 :]:
            if not set(left.required_crew) & set(right.required_crew):
                continue
            if left.duration_minutes + right.duration_minutes <= 240:
                continue
            left_before = model.NewBoolVar(f"{left.request_id}_before_{right.request_id}_long_crew")
            right_before = model.NewBoolVar(f"{right.request_id}_before_{left.request_id}_long_crew")
            break_slots = _duration_slots(30)
            left_has_break = model.NewBoolVar(f"{left.request_id}_break_before_{right.request_id}")
            right_has_break = model.NewBoolVar(f"{right.request_id}_break_before_{left.request_id}")
            left_missing_break = model.NewBoolVar(f"{left.request_id}_missing_break_before_{right.request_id}")
            right_missing_break = model.NewBoolVar(f"{right.request_id}_missing_break_before_{left.request_id}")

            model.Add(ends[left.request_id] <= starts[right.request_id]).OnlyEnforceIf(left_before)
            model.Add(ends[right.request_id] <= starts[left.request_id]).OnlyEnforceIf(right_before)
            model.AddBoolOr([left_before, right_before])
            model.Add(starts[right.request_id] - ends[left.request_id] >= break_slots).OnlyEnforceIf(left_has_break)
            model.Add(starts[left.request_id] - ends[right.request_id] >= break_slots).OnlyEnforceIf(right_has_break)
            model.AddImplication(left_has_break, left_before)
            model.AddImplication(right_has_break, right_before)
            model.AddBoolOr([left_before.Not(), left_has_break, left_missing_break])
            model.AddBoolOr([right_before.Not(), right_has_break, right_missing_break])
            penalty_terms.append(left_missing_break * MISSING_CREW_BREAK_WEIGHT)
            penalty_terms.append(right_missing_break * MISSING_CREW_BREAK_WEIGHT)
    return penalty_terms
