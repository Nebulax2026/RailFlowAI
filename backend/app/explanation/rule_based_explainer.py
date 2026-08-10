from app.domain.enums import ScheduleOption
from app.domain.models import KpiSnapshot, MaintenanceRequest, ScheduledWork


def explain_change(request: MaintenanceRequest, scheduled: ScheduledWork) -> str:
    if not scheduled.changed_from_original:
        return f"{request.request_id} remains within its requested maintenance window."
    return (
        f"{request.request_id} was moved to resolve resource or track conflicts while respecting "
        "deadline, priority, locked work, and engineering-hours constraints."
    )


def explain_alternative(option: ScheduleOption, kpis: KpiSnapshot) -> str:
    return (
        f"{option.value.replace('_', ' ').title()} produces {kpis.unresolved_conflicts} unresolved conflicts, "
        f"{kpis.schedule_stability}% schedule stability, and a robustness score of {kpis.robustness_score}."
    )
