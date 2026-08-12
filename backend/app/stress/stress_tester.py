from datetime import timedelta

from app.conflict.detector import detect_conflicts
from app.domain.models import MaintenanceRequest, ScheduledWork


def stress_test_duration_increase(
    schedule: list[ScheduledWork],
    increase_percent: int,
    requests: list[MaintenanceRequest] | None = None,
) -> dict:
    stressed = [
        item.model_copy(
            update={
                "end_time": item.start_time
                + (item.end_time - item.start_time)
                + timedelta(minutes=int((item.end_time - item.start_time).total_seconds() / 60 * increase_percent / 100))
            }
        )
        for item in schedule
    ]
    conflicts = detect_conflicts(stressed, requests or [])
    return {
        "scenario": f"duration_increase_{increase_percent}_percent",
        "conflicts": conflicts,
        "robustness_score": max(0, 100 - len(conflicts) * 10),
    }
