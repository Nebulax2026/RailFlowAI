from app.domain.models import Conflict, ScheduledWork


def detect_safety_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    # Safety compatibility rules are configured after official rules are available.
    return []
