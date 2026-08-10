from app.domain.enums import RequestSource, ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduledWork
from app.scheduler.cp_sat_scheduler import optimise_schedule


def reschedule_with_emergency(
    current_requests: list[MaintenanceRequest],
    emergency_request: MaintenanceRequest,
) -> list[ScheduledWork]:
    emergency_request.source = RequestSource.EMERGENCY
    emergency_request.priority = 5
    return optimise_schedule([*current_requests, emergency_request], ScheduleOption.MINIMUM_DISRUPTION)
