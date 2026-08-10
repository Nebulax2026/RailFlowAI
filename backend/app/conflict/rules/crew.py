from app.conflict.utils import overlap_window, overlaps
from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, ScheduledWork


def detect_crew_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for index, left in enumerate(schedule):
        for right in schedule[index + 1 :]:
            shared = sorted(set(left.assigned_crew) & set(right.assigned_crew))
            if not shared or not overlaps(left.start_time, left.end_time, right.start_time, right.end_time):
                continue
            conflicts.append(
                Conflict(
                    conflict_id=f"crew-{left.request_id}-{right.request_id}",
                    type=ConflictType.CREW,
                    severity=ConflictSeverity.HIGH,
                    request_ids=[left.request_id, right.request_id],
                    resource=", ".join(shared),
                    time_overlap=overlap_window(left.start_time, left.end_time, right.start_time, right.end_time),
                    explanation=f"{left.request_id} and {right.request_id} require the same crew during an overlapping window.",
                    suggested_action="Assign another crew or move one request.",
                )
            )
    return conflicts
