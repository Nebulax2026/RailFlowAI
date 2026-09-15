from __future__ import annotations

from app.conflict.rules.crew import detect_crew_conflicts
from app.conflict.rules.equipment import detect_equipment_conflicts
from app.conflict.rules.safety import detect_safety_conflicts
from app.conflict.rules.track import detect_track_conflicts
from app.domain.models import Conflict, MaintenanceRequest, ScheduledWork


def detect_conflicts(
    schedule: list[ScheduledWork],
    requests: list[MaintenanceRequest] | None = None,
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    conflicts.extend(detect_track_conflicts(schedule))
    conflicts.extend(detect_crew_conflicts(schedule))
    conflicts.extend(detect_equipment_conflicts(schedule))
    conflicts.extend(detect_safety_conflicts(schedule, requests or []))
    return conflicts
