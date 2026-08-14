from datetime import time

from app.domain.models import MaintenanceRequest, ScheduledWork

ENGINEERING_START = time(9, 0)
ENGINEERING_END = time(18, 0)


def validate_scheduled_work(
    schedule: list[ScheduledWork],
    requests: list[MaintenanceRequest],
) -> list[str]:
    errors: list[str] = []
    schedule_by_request = {item.request_id: item for item in schedule}
    requests_by_id = {request.request_id: request for request in requests}

    for item in schedule:
        request = requests_by_id.get(item.request_id)
        if request and item.end_time > request.deadline:
            errors.append(f"{item.request_id} cannot finish before its deadline.")

    for request in requests:
        scheduled = schedule_by_request.get(request.request_id)
        if not scheduled:
            continue
        for dependency_id in request.dependencies:
            dependency = schedule_by_request.get(dependency_id)
            if not dependency:
                errors.append(f"{request.request_id} requires {dependency_id}, but {dependency_id} is not scheduled.")
            elif dependency.end_time > scheduled.start_time:
                errors.append(f"{request.request_id} must start after {dependency_id} finishes.")

    return errors
