from app.domain.models import Conflict, KpiSnapshot, MaintenanceRequest, ScheduledWork


def calculate_kpis(
    requests: list[MaintenanceRequest],
    scheduled_work: list[ScheduledWork],
    conflicts: list[Conflict],
) -> KpiSnapshot:
    critical_ids = {request.request_id for request in requests if request.priority >= 4}
    scheduled_ids = {item.request_id for item in scheduled_work}
    changed_count = sum(1 for item in scheduled_work if item.changed_from_original)
    total = max(len(requests), 1)

    return KpiSnapshot(
        unresolved_conflicts=len(conflicts),
        critical_jobs_scheduled=len(critical_ids & scheduled_ids),
        engineering_hours_utilisation=min(round(len(scheduled_work) / total * 100, 1), 100.0),
        estimated_overtime_minutes=0,
        schedule_stability=round((total - changed_count) / total * 100, 1),
        robustness_score=max(0, 100 - len(conflicts) * 10 - changed_count * 2),
    )
