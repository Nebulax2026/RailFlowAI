from app.conflict.rules.crew import detect_crew_conflicts
from app.conflict.rules.dependency import detect_dependency_conflicts
from app.conflict.rules.engineering_hours import detect_engineering_hours_conflicts
from app.conflict.rules.equipment import detect_equipment_conflicts
from app.conflict.rules.safety import detect_safety_conflicts
from app.conflict.rules.track import detect_track_conflicts
from app.domain.models import Conflict, ScheduledWork


def detect_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    conflicts.extend(detect_track_conflicts(schedule))
    conflicts.extend(detect_crew_conflicts(schedule))
    conflicts.extend(detect_equipment_conflicts(schedule))
    conflicts.extend(detect_safety_conflicts(schedule))
    conflicts.extend(detect_dependency_conflicts(schedule))
    conflicts.extend(detect_engineering_hours_conflicts(schedule))
    return conflicts
