from datetime import timedelta

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduleAlternative, ScheduledWork
from app.kpi.calculator import calculate_kpis
from app.scheduler.cp_sat_scheduler import optimise_schedule
from app.validation.schedule_validator import validate_scheduled_work

MAX_ALTERNATIVES = 3


def requested_slot_schedule(requests: list[MaintenanceRequest]) -> list[ScheduledWork]:
    scheduled: list[ScheduledWork] = []
    for request in requests:
        start_time = request.fixed_start or request.earliest_start
        end_time = request.fixed_end or start_time + timedelta(minutes=request.duration_minutes)
        scheduled.append(
            ScheduledWork(
                schedule_id=f"schedule-{ScheduleOption.REQUESTED_SLOT.value}",
                request_id=request.request_id,
                start_time=start_time,
                end_time=end_time,
                assigned_crew=request.required_crew,
                assigned_equipment=request.required_equipment,
                track_sector=request.track_sector,
                status=ApprovalStatus.SCHEDULED,
                changed_from_original=False,
            )
        )
    return scheduled


def schedule_signature(schedule: list[ScheduledWork]) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (item.request_id, item.start_time.isoformat(), item.end_time.isoformat())
            for item in schedule
        )
    )


def score_candidate(
    requests: list[MaintenanceRequest],
    schedule: list[ScheduledWork],
    conflicts_count: int,
) -> tuple[int, int, int, int, int]:
    total = max(len(requests), 1)
    scheduled_ids = {item.request_id for item in schedule}
    changed_count = sum(1 for item in schedule if item.changed_from_original)
    overtime_minutes = sum(
        max(0, int((item.end_time - request.deadline).total_seconds() / 60))
        for item in schedule
        for request in requests
        if request.request_id == item.request_id
    )
    critical_ids = {request.request_id for request in requests if request.priority >= 4}

    disruption_score = max(0, round(100 - (changed_count / total * 100)))
    overtime_score = max(0, 100 - overtime_minutes)
    completion_score = round(len(scheduled_ids) / total * 100)
    critical_priority_score = round((len(critical_ids & scheduled_ids) / max(len(critical_ids), 1)) * 100)
    overall_score = round(
        disruption_score * 0.3
        + overtime_score * 0.25
        + completion_score * 0.25
        + critical_priority_score * 0.2
        - conflicts_count * 20
    )
    return disruption_score, overtime_score, completion_score, critical_priority_score, max(0, overall_score)


def explain_ranked_alternative(alternative: ScheduleAlternative) -> str:
    return (
        f"{alternative.label} scores {alternative.overall_score}/100 overall with "
        f"{alternative.disruption_score} disruption, {alternative.overtime_score} overtime, "
        f"{alternative.completion_score} completion, and {alternative.critical_priority_score} critical-priority scores."
    )


def generate_alternatives(requests: list[MaintenanceRequest]) -> list[ScheduleAlternative]:
    candidates: list[ScheduleAlternative] = []
    seen: set[tuple[tuple[str, str, str], ...]] = set()

    candidate_options = [
        ScheduleOption.REQUESTED_SLOT,
        ScheduleOption.MINIMUM_DISRUPTION,
        ScheduleOption.MINIMUM_OVERTIME,
        ScheduleOption.MAXIMUM_COMPLETION,
        ScheduleOption.CRITICAL_WORK_FIRST,
    ]

    for option in candidate_options:
        scheduled = requested_slot_schedule(requests) if option == ScheduleOption.REQUESTED_SLOT else optimise_schedule(requests, option)
        if len(scheduled) != len(requests) or validate_scheduled_work(scheduled, requests):
            continue

        signature = schedule_signature(scheduled)
        if signature in seen:
            continue
        seen.add(signature)

        conflicts = detect_conflicts(scheduled, requests)
        kpis = calculate_kpis(requests, scheduled, conflicts)
        scores = score_candidate(requests, scheduled, len(conflicts))
        candidates.append(
            ScheduleAlternative(
                option=option,
                label="Requested Slot" if option == ScheduleOption.REQUESTED_SLOT else "Feasible Alternative",
                scheduled_work=scheduled,
                conflicts=conflicts,
                kpis=kpis,
                explanation="",
                disruption_score=scores[0],
                overtime_score=scores[1],
                completion_score=scores[2],
                critical_priority_score=scores[3],
                overall_score=scores[4],
            )
        )

    ranked = sorted(candidates, key=lambda item: item.overall_score, reverse=True)[:MAX_ALTERNATIVES]
    for index, alternative in enumerate(ranked, start=1):
        alternative.rank = index
        if alternative.option != ScheduleOption.REQUESTED_SLOT:
            alternative.label = f"Alternative {index}"
        alternative.explanation = explain_ranked_alternative(alternative)
    return ranked
