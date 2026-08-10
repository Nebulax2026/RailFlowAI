from app.domain.models import Conflict, ScheduledWork


def detect_dependency_conflicts(schedule: list[ScheduledWork]) -> list[Conflict]:
    # Dependency validation needs the request graph, so this scaffold keeps the rule boundary explicit.
    return []
