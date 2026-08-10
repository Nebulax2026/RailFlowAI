from datetime import time

from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, ScheduledWork

ENGINEERING_START = time(0, 0)
ENGINEERING_END = time(5, 0)


def detect_engineering_hours_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for item in schedule:
        if item.start_time.time() < ENGINEERING_START or item.end_time.time() > ENGINEERING_END:
            conflicts.append(
                Conflict(
                    conflict_id=f"engineering-hours-{item.request_id}",
                    type=ConflictType.ENGINEERING_HOURS,
                    severity=ConflictSeverity.CRITICAL,
                    request_ids=[item.request_id],
                    resource="engineering_hours",
                    explanation=f"{item.request_id} is scheduled outside the allowed engineering hours.",
                    suggested_action="Move the request into the configured maintenance window.",
                )
            )
    return conflicts
