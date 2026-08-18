from datetime import timedelta

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import Conflict, MaintenanceRequest, RequestFitResponse, ScheduleAlternative, ScheduleChange, ScheduledWork
from app.scheduler.alternative_generator import generate_alternatives, requested_slot_schedule
from app.scheduler.cp_sat_scheduler import SchedulingInfeasibleError, optimise_schedule
from app.scheduler.horizon import classify_horizon, move_penalty
from app.storage import REQUESTS, SCHEDULED_WORK
from app.validation.business_validator import validate_business_rules
from app.validation.dependency_rules import validate_work_type_prerequisites
from app.validation.schedule_validator import validate_scheduled_work


def validate_request_for_queue(request: MaintenanceRequest) -> list[str]:
    errors = validate_business_rules(request)
    errors.extend(validate_work_type_prerequisites(request, REQUESTS, SCHEDULED_WORK))
    return errors


def requests_with_locked_schedule() -> list[MaintenanceRequest]:
    prepared: list[MaintenanceRequest] = []
    for request in REQUESTS.values():
        scheduled = SCHEDULED_WORK.get(request.request_id)
        if scheduled and scheduled.status == ApprovalStatus.LOCKED:
            prepared.append(
                request.model_copy(
                    update={
                        "approval_status": ApprovalStatus.LOCKED,
                        "locked": True,
                        "fixed_start": scheduled.start_time,
                        "fixed_end": scheduled.end_time,
                    }
                )
            )
        else:
            prepared.append(request.model_copy(update={"locked": False, "fixed_start": None, "fixed_end": None}))
    return prepared


def requests_with_movable_schedule(request_ids: list[str] | None = None) -> list[MaintenanceRequest]:
    selected = set(request_ids or [])
    scheduled_ids = set(SCHEDULED_WORK)
    requests = [
        request
        for request in REQUESTS.values()
        if not selected or request.request_id in selected or request.request_id in scheduled_ids or request.approval_status != ApprovalStatus.DRAFT
    ]
    ordered_requests = sorted(
        requests,
        key=lambda request: (0 if request.request_id in selected else 1, -request.priority, request.earliest_start),
    )
    return [
        request.model_copy(update={"locked": False, "fixed_start": None, "fixed_end": None})
        for request in ordered_requests
    ]


def requested_item_for(request: MaintenanceRequest) -> ScheduledWork:
    start_time = request.fixed_start or request.earliest_start
    end_time = request.fixed_end or start_time + timedelta(minutes=request.duration_minutes)
    return ScheduledWork(
        schedule_id="schedule-requested-fit",
        request_id=request.request_id,
        start_time=start_time,
        end_time=end_time,
        assigned_crew=request.required_crew,
        assigned_equipment=request.required_equipment,
        track_sector=request.track_sector,
        status=ApprovalStatus.SCHEDULED,
    )


def evaluate_fit(request: MaintenanceRequest) -> RequestFitResponse:
    requested_item = requested_item_for(request)
    candidate = [*SCHEDULED_WORK.values(), requested_item]
    conflicts = detect_conflicts(candidate, list(REQUESTS.values()))
    fits = not conflicts
    if fits:
        scheduled = requested_item.model_copy(update={"schedule_id": "schedule-tentative"})
        SCHEDULED_WORK[request.request_id] = scheduled
        REQUESTS[request.request_id] = request.model_copy(update={"approval_status": ApprovalStatus.SCHEDULED})
        return RequestFitResponse(
            request=REQUESTS[request.request_id],
            fits_current_schedule=True,
            conflicts=[],
            scheduled_work=scheduled,
        )

    alternatives = generate_reschedule_proposals()
    selected = alternatives[0] if alternatives else None
    proposed_item = (
        next((item for item in selected.scheduled_work if item.request_id == request.request_id), None)
        if selected
        else None
    )
    return RequestFitResponse(
        request=request,
        fits_current_schedule=False,
        conflicts=conflicts,
        suggested_alternatives=alternatives,
        scheduled_work=proposed_item,
        requires_manager_review=bool(selected),
        affected_changes=schedule_changes_for(selected.scheduled_work) if selected else [],
        proposal_option=selected.option if selected else None,
    )


def build_optimised_schedule(option: ScheduleOption) -> tuple[list[ScheduledWork], list[str], list[Conflict]]:
    requests = requests_with_locked_schedule()
    try:
        scheduled = optimise_schedule(requests, option)
    except SchedulingInfeasibleError as error:
        return [], list(error.blockers), []
    errors = validate_scheduled_work(scheduled, requests)
    if len(scheduled) != len(requests):
        scheduled_ids = {item.request_id for item in scheduled}
        missing = [request.request_id for request in requests if request.request_id not in scheduled_ids]
        errors.extend(f"{request_id} could not be placed within its allowed window." for request_id in missing)
    conflicts = detect_conflicts(scheduled, requests)
    return scheduled, errors, conflicts


def apply_schedule(schedule: list[ScheduledWork]) -> None:
    SCHEDULED_WORK.clear()
    for item in schedule:
        SCHEDULED_WORK[item.request_id] = item


def apply_alternative(option: ScheduleOption, request_ids: list[str] | None = None) -> tuple[list[ScheduledWork], list[str], list[Conflict]]:
    requests = requests_with_movable_schedule(request_ids)
    try:
        schedule = requested_slot_schedule(requests) if option == ScheduleOption.REQUESTED_SLOT else optimise_schedule(requests, option)
    except SchedulingInfeasibleError as error:
        return [], list(error.blockers), []
    errors = validate_scheduled_work(schedule, requests)
    conflicts = detect_conflicts(schedule, requests)
    if errors or conflicts:
        return schedule, errors, conflicts
    apply_reschedule(schedule)
    return schedule, errors, conflicts


def generate_reschedule_proposals(request_ids: list[str] | None = None) -> list[ScheduleAlternative]:
    selected = set(request_ids or [])
    proposals = [alternative for alternative in generate_alternatives(requests_with_movable_schedule(request_ids)) if not alternative.conflicts]
    if not selected:
        return proposals
    return [
        alternative
        for alternative in proposals
        if selected.issubset({item.request_id for item in alternative.scheduled_work})
    ]


def schedule_changes_for(schedule: list[ScheduledWork]) -> list[ScheduleChange]:
    changes: list[ScheduleChange] = []
    current_by_request = {item.request_id: item for item in SCHEDULED_WORK.values()}
    requests_by_id = {request.request_id: request for request in REQUESTS.values()}

    for proposed in schedule:
        request = requests_by_id.get(proposed.request_id)
        current = current_by_request.get(proposed.request_id)
        if current and current.start_time == proposed.start_time and current.end_time == proposed.end_time:
            continue
        changes.append(
            ScheduleChange(
                request_id=proposed.request_id,
                owner=request.created_by if request else "field",
                previous_start=current.start_time if current else None,
                previous_end=current.end_time if current else None,
                proposed_start=proposed.start_time,
                proposed_end=proposed.end_time,
                was_locked=current.status == ApprovalStatus.LOCKED if current else False,
                horizon=classify_horizon(current) if current else classify_horizon(proposed),
                move_penalty=move_penalty(current) if current else 0,
                reason=(
                    proposed.change_reason
                    or "Scheduled to fit the new request while preserving original request constraints."
                ),
            )
        )
    return changes


def apply_reschedule(schedule: list[ScheduledWork]) -> None:
    current_by_request = {item.request_id: item for item in SCHEDULED_WORK.values()}
    SCHEDULED_WORK.clear()
    for item in schedule:
        current = current_by_request.get(item.request_id)
        unchanged_locked = (
            current
            and current.status == ApprovalStatus.LOCKED
            and current.start_time == item.start_time
            and current.end_time == item.end_time
        )
        status = ApprovalStatus.LOCKED if unchanged_locked else ApprovalStatus.SCHEDULED
        applied = item.model_copy(update={"status": status})
        SCHEDULED_WORK[item.request_id] = applied

        request = REQUESTS.get(item.request_id)
        if request:
            REQUESTS[item.request_id] = request.model_copy(
                update={
                    "approval_status": status,
                    "locked": status == ApprovalStatus.LOCKED,
                    "fixed_start": applied.start_time if status == ApprovalStatus.LOCKED else None,
                    "fixed_end": applied.end_time if status == ApprovalStatus.LOCKED else None,
                }
            )
