from datetime import datetime, timedelta

from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduledWork
from app.scheduler.time_windows import align_to_engineering_window


def optimise_schedule(
    requests: list[MaintenanceRequest],
    option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION,
) -> list[ScheduledWork]:
    # This greedy baseline preserves the API contract while CP-SAT constraints are expanded.
    if option == ScheduleOption.REQUESTED_SLOT:
        option = ScheduleOption.MINIMUM_DISRUPTION

    locked_requests = sorted(
        [item for item in requests if item.locked and item.fixed_start and item.fixed_end],
        key=lambda item: item.fixed_start or item.earliest_start,
    )
    movable_requests = [item for item in requests if item not in locked_requests]

    if option == ScheduleOption.MINIMUM_OVERTIME:
        sorted_movable = sorted(movable_requests, key=lambda item: (item.deadline, -item.priority, item.earliest_start))
    elif option == ScheduleOption.MAXIMUM_COMPLETION:
        sorted_movable = sorted(movable_requests, key=lambda item: (item.duration_minutes, item.deadline, -item.priority))
    elif option == ScheduleOption.CRITICAL_WORK_FIRST:
        sorted_movable = sorted(movable_requests, key=lambda item: (-item.priority, item.deadline, item.earliest_start))
    else:
        sorted_movable = sorted(
            movable_requests,
            key=lambda item: (0 if item.approval_status == ApprovalStatus.APPROVED else 1, item.earliest_start),
        )

    sorted_requests = [*locked_requests, *sorted_movable]
    scheduled: list[ScheduledWork] = []
    next_available_by_track: dict[str, datetime] = {}
    next_available_by_crew: dict[str, datetime] = {}
    next_available_by_equipment: dict[str, datetime] = {}

    for request in sorted_requests:
        if request.locked and request.fixed_start and request.fixed_end:
            start_time = request.fixed_start
            end_time = request.fixed_end
        else:
            start_time = request.earliest_start
            blockers = [next_available_by_track.get(request.track_sector)]
            blockers.extend(next_available_by_crew.get(crew) for crew in request.required_crew)
            blockers.extend(next_available_by_equipment.get(equipment) for equipment in request.required_equipment)
            for blocker in blockers:
                if blocker and blocker > start_time:
                    start_time = blocker
            start_time = align_to_engineering_window(start_time, request.duration_minutes, request.deadline)
            end_time = start_time + timedelta(minutes=request.duration_minutes)

        if end_time > request.deadline:
            continue

        scheduled_item = ScheduledWork(
            schedule_id=f"schedule-{option.value}",
            request_id=request.request_id,
            start_time=start_time,
            end_time=end_time,
            assigned_crew=request.required_crew,
            assigned_equipment=request.required_equipment,
            track_sector=request.track_sector,
            status=ApprovalStatus.LOCKED if request.locked else ApprovalStatus.SCHEDULED,
            changed_from_original=start_time != request.earliest_start,
            change_reason=(
                "Moved from requested earliest start to avoid track, crew, or equipment overlap."
                if start_time != request.earliest_start
                else None
            ),
        )
        scheduled.append(scheduled_item)

        next_available_by_track[request.track_sector] = end_time
        for crew in request.required_crew:
            next_available_by_crew[crew] = end_time
        for equipment in request.required_equipment:
            next_available_by_equipment[equipment] = end_time

    return scheduled
