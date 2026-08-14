from app.conflict.utils import overlap_window, overlaps
from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, MaintenanceRequest, ScheduledWork


def detect_safety_conflicts(schedule: list[ScheduledWork], requests: list[MaintenanceRequest]) -> list[Conflict]:
    request_by_id = {request.request_id: request for request in requests}
    conflicts: list[Conflict] = []
    for index, left in enumerate(schedule):
        left_request = request_by_id.get(left.request_id)
        if not left_request:
            continue
        for right in schedule[index + 1 :]:
            right_request = request_by_id.get(right.request_id)
            if not right_request:
                continue
            if left.track_sector != right.track_sector:
                continue
            if not overlaps(left.start_time, left.end_time, right.start_time, right.end_time):
                continue

            incompatible_types = sorted(
                {
                    work_type
                    for work_type in (left_request.work_type, right_request.work_type)
                    if work_type in left_request.incompatible_work_types or work_type in right_request.incompatible_work_types
                }
            )
            if not incompatible_types:
                continue

            conflicts.append(
                Conflict(
                    conflict_id=f"safety-{left.request_id}-{right.request_id}",
                    type=ConflictType.SAFETY,
                    severity=ConflictSeverity.HIGH,
                    request_ids=[left.request_id, right.request_id],
                    resource=", ".join(incompatible_types),
                    time_overlap=overlap_window(left.start_time, left.end_time, right.start_time, right.end_time),
                    explanation=(
                        f"{left.request_id} ({left_request.work_type}) and {right.request_id} ({right_request.work_type}) "
                        f"cannot overlap on track sector {left.track_sector} because one work type marks the other as incompatible."
                    ),
                    suggested_action="Move one request outside the overlapping safety-incompatible window.",
                )
            )
    return conflicts
