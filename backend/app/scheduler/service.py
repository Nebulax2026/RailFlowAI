from datetime import timedelta

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import Conflict, MaintenanceRequest, RequestFitResponse, ScheduledWork
from app.scheduler.alternative_generator import generate_alternatives, requested_slot_schedule
from app.scheduler.cp_sat_scheduler import optimise_schedule
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
    candidate = [*SCHEDULED_WORK.values(), requested_item_for(request)]
    conflicts = detect_conflicts(candidate, list(REQUESTS.values()))
    fits = not conflicts
    alternatives = [] if fits else generate_alternatives(requests_with_locked_schedule())
    return RequestFitResponse(
        request=request,
        fits_current_schedule=fits,
        conflicts=conflicts,
        suggested_alternatives=alternatives,
    )


def build_optimised_schedule(option: ScheduleOption) -> tuple[list[ScheduledWork], list[str], list[Conflict]]:
    requests = requests_with_locked_schedule()
    scheduled = optimise_schedule(requests, option)
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


def apply_alternative(option: ScheduleOption) -> tuple[list[ScheduledWork], list[str], list[Conflict]]:
    requests = requests_with_locked_schedule()
    schedule = requested_slot_schedule(requests) if option == ScheduleOption.REQUESTED_SLOT else optimise_schedule(requests, option)
    errors = validate_scheduled_work(schedule, requests)
    conflicts = detect_conflicts(schedule, requests)
    if errors:
        return schedule, errors, conflicts
    apply_schedule(schedule)
    return schedule, errors, conflicts
