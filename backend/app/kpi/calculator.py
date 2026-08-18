from datetime import datetime

from app.domain.models import Conflict, KpiSnapshot, MaintenanceRequest, ScheduledWork
from app.scheduler.time_windows import ENGINEERING_END, ENGINEERING_START, to_planning_time


def overtime_minutes(item: ScheduledWork) -> int:
    start_time = to_planning_time(item.start_time)
    end_time = to_planning_time(item.end_time)
    standard_start = datetime.combine(start_time.date(), ENGINEERING_START)
    standard_end = datetime.combine(start_time.date(), ENGINEERING_END)
    if start_time.tzinfo is not None:
        standard_start = standard_start.replace(tzinfo=start_time.tzinfo)
        standard_end = standard_end.replace(tzinfo=start_time.tzinfo)
    before_start = max(0, int((min(end_time, standard_start) - start_time).total_seconds() / 60))
    after_end = max(0, int((end_time - max(start_time, standard_end)).total_seconds() / 60))
    return before_start + after_end


def standard_window_minutes_used(item: ScheduledWork) -> int:
    start_time = to_planning_time(item.start_time)
    end_time = to_planning_time(item.end_time)
    standard_start = datetime.combine(start_time.date(), ENGINEERING_START)
    standard_end = datetime.combine(start_time.date(), ENGINEERING_END)
    if start_time.tzinfo is not None:
        standard_start = standard_start.replace(tzinfo=start_time.tzinfo)
        standard_end = standard_end.replace(tzinfo=start_time.tzinfo)
    overlap_start = max(start_time, standard_start)
    overlap_end = min(end_time, standard_end)
    return max(0, int((overlap_end - overlap_start).total_seconds() / 60))


def calculate_kpis(
    requests: list[MaintenanceRequest],
    scheduled_work: list[ScheduledWork],
    conflicts: list[Conflict],
) -> KpiSnapshot:
    critical_ids = {request.request_id for request in requests if request.priority >= 4}
    scheduled_ids = {item.request_id for item in scheduled_work}
    changed_count = sum(1 for item in scheduled_work if item.changed_from_original)
    total = max(len(requests), 1)
    scheduled_dates = {to_planning_time(item.start_time).date() for item in scheduled_work}
    standard_minutes = (
        int(
            (
                datetime.combine(datetime.today(), ENGINEERING_END)
                - datetime.combine(datetime.today(), ENGINEERING_START)
            ).total_seconds()
            / 60
        )
        * max(len(scheduled_dates), 1)
    )
    used_standard_minutes = sum(standard_window_minutes_used(item) for item in scheduled_work)

    return KpiSnapshot(
        unresolved_conflicts=len(conflicts),
        critical_jobs_scheduled=len(critical_ids & scheduled_ids),
        engineering_hours_utilisation=min(round(used_standard_minutes / standard_minutes * 100, 1), 100.0),
        estimated_overtime_minutes=sum(overtime_minutes(item) for item in scheduled_work),
        schedule_stability=round((total - changed_count) / total * 100, 1),
        robustness_score=max(0, 100 - len(conflicts) * 10 - changed_count * 2),
    )
