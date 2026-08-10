from datetime import timedelta

from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduledWork


def optimise_schedule(
    requests: list[MaintenanceRequest],
    option: ScheduleOption = ScheduleOption.MINIMUM_DISRUPTION,
) -> list[ScheduledWork]:
    # This greedy baseline preserves the API contract while CP-SAT constraints are expanded.
    sorted_requests = sorted(requests, key=lambda item: (-item.priority, item.deadline, item.earliest_start))
    scheduled: list[ScheduledWork] = []
    next_available_by_track: dict[str, object] = {}
    next_available_by_crew: dict[str, object] = {}
    next_available_by_equipment: dict[str, object] = {}

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
            end_time = start_time + timedelta(minutes=request.duration_minutes)

        scheduled_item = ScheduledWork(
            schedule_id=f"schedule-{option.value}",
            request_id=request.request_id,
            start_time=start_time,
            end_time=end_time,
            assigned_crew=request.required_crew,
            assigned_equipment=request.required_equipment,
            track_sector=request.track_sector,
            status=ApprovalStatus.SCHEDULED,
            changed_from_original=bool(request.fixed_start and request.fixed_start != start_time),
            change_reason=None,
        )
        scheduled.append(scheduled_item)

        next_available_by_track[request.track_sector] = end_time
        for crew in request.required_crew:
            next_available_by_crew[crew] = end_time
        for equipment in request.required_equipment:
            next_available_by_equipment[equipment] = end_time

    return scheduled
