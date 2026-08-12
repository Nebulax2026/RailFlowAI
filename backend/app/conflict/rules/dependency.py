from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, MaintenanceRequest, ScheduledWork


def detect_dependency_conflicts(
    schedule: list[ScheduledWork],
    requests: list[MaintenanceRequest],
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    schedule_by_request = {item.request_id: item for item in schedule}
    requests_by_id = {request.request_id: request for request in requests}

    for request in requests:
        scheduled = schedule_by_request.get(request.request_id)
        if not scheduled:
            continue
        for dependency_id in request.dependencies:
            dependency = schedule_by_request.get(dependency_id)
            if not dependency:
                conflicts.append(
                    Conflict(
                        conflict_id=f"dependency-missing-{dependency_id}-{request.request_id}",
                        type=ConflictType.DEPENDENCY,
                        severity=ConflictSeverity.HIGH,
                        request_ids=[dependency_id, request.request_id],
                        resource=dependency_id,
                        explanation=f"{request.request_id} depends on {dependency_id}, but {dependency_id} is not scheduled.",
                        suggested_action=f"Schedule {dependency_id} before {request.request_id}.",
                    )
                )
                continue
            if dependency.end_time > scheduled.start_time:
                dependency_title = requests_by_id.get(dependency_id).title if dependency_id in requests_by_id else dependency_id
                conflicts.append(
                    Conflict(
                        conflict_id=f"dependency-order-{dependency_id}-{request.request_id}",
                        type=ConflictType.DEPENDENCY,
                        severity=ConflictSeverity.HIGH,
                        request_ids=[dependency_id, request.request_id],
                        resource=dependency_id,
                        time_overlap=(scheduled.start_time, dependency.end_time),
                        explanation=(
                            f"{request.request_id} starts before dependency {dependency_id} "
                            f"({dependency_title}) is complete."
                        ),
                        suggested_action=f"Move {request.request_id} after {dependency_id} finishes.",
                    )
                )
    return conflicts
