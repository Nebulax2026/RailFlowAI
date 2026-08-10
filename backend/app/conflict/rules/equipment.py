from app.conflict.utils import overlap_window, overlaps
from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, ScheduledWork


def detect_equipment_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for index, left in enumerate(schedule):
        for right in schedule[index + 1 :]:
            shared = sorted(set(left.assigned_equipment) & set(right.assigned_equipment))
            if not shared or not overlaps(left.start_time, left.end_time, right.start_time, right.end_time):
                continue
            conflicts.append(
                Conflict(
                    conflict_id=f"equipment-{left.request_id}-{right.request_id}",
                    type=ConflictType.EQUIPMENT,
                    severity=ConflictSeverity.HIGH,
                    request_ids=[left.request_id, right.request_id],
                    resource=", ".join(shared),
                    time_overlap=overlap_window(left.start_time, left.end_time, right.start_time, right.end_time),
                    explanation=f"{left.request_id} and {right.request_id} require the same equipment during an overlapping window.",
                    suggested_action="Reserve alternate equipment or move one request.",
                )
            )
    return conflicts
