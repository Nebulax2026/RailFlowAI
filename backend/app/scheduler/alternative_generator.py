from app.conflict.detector import detect_conflicts
from app.domain.enums import ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduleAlternative
from app.explanation.rule_based_explainer import explain_alternative
from app.kpi.calculator import calculate_kpis
from app.scheduler.cp_sat_scheduler import optimise_schedule


def generate_alternatives(requests: list[MaintenanceRequest]) -> list[ScheduleAlternative]:
    alternatives: list[ScheduleAlternative] = []
    for option in ScheduleOption:
        scheduled = optimise_schedule(requests, option)
        conflicts = detect_conflicts(scheduled)
        kpis = calculate_kpis(requests, scheduled, conflicts)
        alternatives.append(
            ScheduleAlternative(
                option=option,
                label=option.value.replace("_", " ").title(),
                scheduled_work=scheduled,
                conflicts=conflicts,
                kpis=kpis,
                explanation=explain_alternative(option, kpis),
            )
        )
    return alternatives
