from app.domain.enums import ConflictSeverity, ConflictType
from app.domain.models import Conflict, ScheduledWork
from app.scheduler.time_windows import ENGINEERING_END, ENGINEERING_START, to_planning_time


def detect_engineering_hours_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for item in schedule:
        start_time = to_planning_time(item.start_time)
        end_time = to_planning_time(item.end_time)
        if start_time.time() < ENGINEERING_START or end_time.time() > ENGINEERING_END:
            conflicts.append(
                Conflict(
                    conflict_id=f"engineering-hours-{item.request_id}",
                    type=ConflictType.ENGINEERING_HOURS,
                    severity=ConflictSeverity.CRITICAL,
                    request_ids=[item.request_id],
                    resource="engineering_hours",
                    explanation=f"{item.request_id} is scheduled outside standard engineering hours.",
                    suggested_action="Move the request into 09:00-18:00 or use overtime.",
                )
            )
    return conflicts
