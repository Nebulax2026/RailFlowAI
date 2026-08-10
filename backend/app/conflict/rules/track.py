from app.conflict.utils import overlap_window, overlaps
from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, ScheduledWork


def detect_track_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for index, left in enumerate(schedule):
        for right in schedule[index + 1 :]:
            if left.track_sector != right.track_sector:
                continue
            if not overlaps(left.start_time, left.end_time, right.start_time, right.end_time):
                continue
            window = overlap_window(left.start_time, left.end_time, right.start_time, right.end_time)
            conflicts.append(
                Conflict(
                    conflict_id=f"track-{left.request_id}-{right.request_id}",
                    type=ConflictType.TRACK,
                    severity=ConflictSeverity.HIGH,
                    request_ids=[left.request_id, right.request_id],
                    resource=left.track_sector,
                    time_overlap=window,
                    explanation=f"{left.request_id} and {right.request_id} use track sector {left.track_sector} at the same time.",
                    suggested_action="Move one request outside the overlapping window.",
                )
            )
    return conflicts
