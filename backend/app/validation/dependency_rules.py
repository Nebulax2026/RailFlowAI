from app.domain.models import MaintenanceRequest, ScheduledWork


WORK_TYPE_PREREQUISITES = {
    "signal_test": ["signal_replacement"],
    "track_renewal": ["track_inspection"],
    "electrical_repair": ["power_isolation"],
    "service_restore": ["safety_clearance"],
}


def validate_work_type_prerequisites(
    request: MaintenanceRequest,
    requests: dict[str, MaintenanceRequest],
    scheduled_work: dict[str, ScheduledWork],
) -> list[str]:
    required_work_types = WORK_TYPE_PREREQUISITES.get(request.work_type, [])
    if not required_work_types:
        return []

    scheduled_request_ids = set(scheduled_work)
    scheduled_requests = [
        existing
        for existing in requests.values()
        if existing.request_id in scheduled_request_ids and existing.track_sector == request.track_sector
    ]
    present_work_types = {existing.work_type for existing in scheduled_requests}
    missing = [work_type for work_type in required_work_types if work_type not in present_work_types]
    if not missing:
        return []

    formatted_missing = ", ".join(missing).replace("_", " ")
    formatted_work = request.work_type.replace("_", " ")
    return [
        f"{formatted_work} requires scheduled prerequisite work on {request.track_sector}: {formatted_missing}."
    ]
