from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.conflict.detector import detect_conflicts
from app.audit import record_audit_event
from app.domain.enums import ApprovalStatus, ConflictSeverity, ConflictType, DisplacementApprovalStatus, RequestSource, ScheduleOption
from app.domain.models import Conflict, DisplacementApproval, MaintenanceRequest, Notification, RequestFitResponse, ScheduleAlternative, ScheduleChange, ScheduledWork, SlotRecommendation
from app.proposals import record_proposal_snapshot
from app.repositories import (
    blocked_time_slot_repository,
    displacement_approval_repository,
    notification_repository,
    requests_repository,
    schedule_repository,
    scheduling_settings_repository,
    unit_of_work,
)
from app.scheduler.alternative_generator import generate_alternatives, requested_slot_schedule
from app.scheduler.cp_sat_scheduler import optimise_schedule
from app.scheduler.horizon import classify_horizon, move_penalty
from app.scheduler.policy import block_overlaps_work, frozen_date_cutoff, is_frozen_work, is_planning_eligible, is_urgent, planning_now, requires_urgent_approver_review
from app.scheduler.time_windows import align_to_engineering_window
from app.validation.business_validator import validate_business_rules
from app.validation.dependency_rules import validate_work_type_prerequisites
from app.validation.schedule_validator import validate_scheduled_work


def validate_request_for_queue(request: MaintenanceRequest) -> list[str]:
    errors = validate_business_rules(request)
    existing_requests = {item.request_id: item for item in requests_repository.list()}
    existing_schedule = {item.request_id: item for item in schedule_repository.list()}
    errors.extend(validate_work_type_prerequisites(request, existing_requests, existing_schedule))
    return errors


def requests_with_locked_schedule() -> list[MaintenanceRequest]:
    settings = scheduling_settings_repository.get()
    prepared: list[MaintenanceRequest] = []
    for request in requests_repository.list():
        if request.approval_status == ApprovalStatus.PENDING_APPROVAL:
            continue
        if not request.locked and not is_planning_eligible(request, settings):
            continue
        scheduled = schedule_repository.get(request.request_id)
        if scheduled and (scheduled.status == ApprovalStatus.LOCKED or is_frozen_work(scheduled, settings)):
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
    settings = scheduling_settings_repository.get()
    selected = set(request_ids or [])
    scheduled_ids = {item.request_id for item in schedule_repository.list()}
    requests = [
        request
        for request in requests_repository.list()
        if (not selected or request.request_id in selected or request.request_id in scheduled_ids or request.approval_status != ApprovalStatus.DRAFT)
        and (request.request_id in selected or request.locked or is_planning_eligible(request, settings))
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
    start_time = request.fixed_start or align_to_engineering_window(request.earliest_start, request.duration_minutes, request.deadline)
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


def fixed_existing_requests_for_recommendation() -> list[MaintenanceRequest]:
    existing = {request.request_id: request for request in requests_repository.list()}
    fixed: list[MaintenanceRequest] = []
    for item in schedule_repository.list():
        request = existing.get(item.request_id)
        if not request:
            continue
        fixed.append(
            request.model_copy(
                update={
                    "locked": True,
                    "fixed_start": item.start_time,
                    "fixed_end": item.end_time,
                    "approval_status": ApprovalStatus.LOCKED,
                }
            )
        )
    return fixed


def recommend_slot(request: MaintenanceRequest) -> SlotRecommendation:
    scheduled = optimise_schedule([*fixed_existing_requests_for_recommendation(), request], ScheduleOption.MINIMUM_DISRUPTION)
    recommended = next((item for item in scheduled if item.request_id == request.request_id), None)
    conflicts = detect_conflicts([*schedule_repository.list(), requested_item_for(request)], requests_repository.list())
    if not recommended:
        return SlotRecommendation(
            request=request,
            available=False,
            message="No feasible slot is available. Send the requirement to an Approver for manual review.",
        )
    return SlotRecommendation(
        request=request,
        available=True,
        recommended_work=recommended,
        message="Recommended slot is available for Approver review." if conflicts else "Recommended slot is available.",
    )


def blocked_slot_conflicts(item: ScheduledWork) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for block in blocked_time_slot_repository.list(active_only=True):
        if not block_overlaps_work(block, item):
            continue
        conflicts.append(
            Conflict(
                conflict_id=f"conflict-block-{block.block_id}-{item.request_id}",
                type=ConflictType.TRACK,
                severity=ConflictSeverity.HIGH,
                request_ids=[item.request_id],
                resource=", ".join(block.track_sectors),
                time_overlap=(item.start_time, item.end_time),
                explanation=(
                    f"{item.request_id} overlaps manager blocked track time {block.block_id} "
                    f"for {', '.join(block.track_sectors)}."
                ),
                suggested_action="Choose a proposal outside the blocked window or ask a Schedule Manager to revise the block.",
            )
        )
    return conflicts


def validate_schedule_against_blocks(schedule: list[ScheduledWork]) -> list[str]:
    errors: list[str] = []
    for item in schedule:
        for block in blocked_time_slot_repository.list(active_only=True):
            if block_overlaps_work(block, item):
                errors.append(f"{item.request_id} overlaps blocked slot {block.block_id}.")
    return errors


def create_notification(
    owner: str,
    message: str,
    notification_type: str,
    request_ids: list[str] | None = None,
    block_id: str | None = None,
    approval_id: str | None = None,
) -> Notification:
    notification = Notification(
        notification_id=f"notice-{uuid4().hex}",
        owner=owner,
        type=notification_type,
        message=message,
        request_ids=request_ids or [],
        block_id=block_id,
        approval_id=approval_id,
        created_at=datetime.now(timezone.utc),
    )
    return notification_repository.save(notification)


def create_displacement_approval_if_needed(request: MaintenanceRequest, alternatives: list[ScheduleAlternative]) -> None:
    settings = scheduling_settings_repository.get()
    if not is_urgent(request, settings):
        return
    current_by_request = {item.request_id: item for item in schedule_repository.list()}
    requests_by_id = {item.request_id: item for item in requests_repository.list()}
    for alternative in alternatives:
        urgent_work = next((item for item in alternative.scheduled_work if item.request_id == request.request_id), None)
        if not urgent_work:
            continue
        for proposed in alternative.scheduled_work:
            current = current_by_request.get(proposed.request_id)
            if not current or proposed.request_id == request.request_id:
                continue
            if current.start_time == proposed.start_time and current.end_time == proposed.end_time:
                continue
            displaced_request = requests_by_id.get(proposed.request_id)
            owner = displaced_request.created_by if displaced_request else "field"
            existing = [
                approval
                for approval in displacement_approval_repository.list(status=DisplacementApprovalStatus.PENDING)
                if approval.urgent_request_id == request.request_id and approval.displaced_request_id == proposed.request_id
            ]
            if existing:
                return
            approval = displacement_approval_repository.save(
                DisplacementApproval(
                    approval_id=f"approval-{uuid4().hex}",
                    urgent_request_id=request.request_id,
                    displaced_request_id=proposed.request_id,
                    owner=owner,
                    previous_start=current.start_time,
                    previous_end=current.end_time,
                    proposed_start=proposed.start_time,
                    proposed_end=proposed.end_time,
                    urgent_work=urgent_work,
                    displaced_work=proposed,
                    created_at=datetime.now(timezone.utc),
                )
            )
            create_notification(
                owner=owner,
                message=(
                    f"Urgent request {request.request_id} needs your slot. "
                    f"Approve moving {proposed.request_id} to the proposed later window."
                ),
                notification_type="displacement_approval_requested",
                request_ids=[request.request_id, proposed.request_id],
                approval_id=approval.approval_id,
            )
            create_notification(
                owner=request.created_by,
                message=(
                    f"No suitable slot is free for urgent request {request.request_id}. "
                    f"Approval has been requested to move {proposed.request_id}."
                ),
                notification_type="urgent_displacement_pending",
                request_ids=[request.request_id, proposed.request_id],
                approval_id=approval.approval_id,
            )
            return


def evaluate_fit(request: MaintenanceRequest) -> RequestFitResponse:
    settings = scheduling_settings_repository.get()
    if not is_planning_eligible(request, settings):
        return RequestFitResponse(
            request=request,
            fits_current_schedule=True,
            conflicts=[],
        )
    if requires_urgent_approver_review(request, settings):
        recommendation = recommend_slot(request)
        updates = {
            "approval_status": ApprovalStatus.PENDING_APPROVAL,
            "source": RequestSource.EMERGENCY,
        }
        if recommendation.recommended_work:
            updates["recommended_start"] = recommendation.recommended_work.start_time
            updates["recommended_end"] = recommendation.recommended_work.end_time
        pending_request = request.model_copy(update=updates)
        create_notification(
            owner="approver",
            message=f"Urgent request {request.request_id} is waiting for approval.",
            notification_type="urgent_approval_requested",
            request_ids=[request.request_id],
        )
        create_notification(
            owner="schedule_manager",
            message=f"Urgent request {request.request_id} is waiting for approval.",
            notification_type="urgent_approval_requested",
            request_ids=[request.request_id],
        )
        return RequestFitResponse(
            request=pending_request,
            fits_current_schedule=False,
            conflicts=[],
            requires_manager_review=True,
            scheduled_work=None,
        )
    requested_item = requested_item_for(request)
    candidate = [*schedule_repository.list(), requested_item]
    conflicts = [*detect_conflicts(candidate, requests_repository.list()), *blocked_slot_conflicts(requested_item)]
    fits = not conflicts
    if fits:
        return RequestFitResponse(
            request=request,
            fits_current_schedule=True,
            conflicts=[],
            scheduled_work=requested_item,
        )

    alternatives = generate_reschedule_proposals()
    selected = alternatives[0] if alternatives else None
    create_displacement_approval_if_needed(request, alternatives)
    return RequestFitResponse(
        request=request,
        fits_current_schedule=False,
        conflicts=conflicts,
        suggested_alternatives=alternatives,
        requires_manager_review=bool(selected),
        affected_changes=schedule_changes_for(selected.scheduled_work) if selected else [],
        proposal_option=selected.option if selected else None,
    )


def confirm_urgent_request(request_id: str, requester_message: str | None = None) -> MaintenanceRequest:
    request = requests_repository.get(request_id)
    if not request:
        raise ValueError("Request not found.")
    recommendation = recommend_slot(request)
    updates = {
        "approval_status": ApprovalStatus.PENDING_APPROVAL,
        "requester_message": requester_message,
        "source": RequestSource.EMERGENCY,
    }
    if recommendation.recommended_work:
        updates["recommended_start"] = recommendation.recommended_work.start_time
        updates["recommended_end"] = recommendation.recommended_work.end_time
    with unit_of_work() as work:
        saved = work.requests.save(request.model_copy(update=updates))
        create_notification(
            owner="approver",
            message=f"Urgent request {request_id} is waiting for approval.",
            notification_type="urgent_approval_requested",
            request_ids=[request_id],
        )
        create_notification(
            owner="schedule_manager",
            message=f"Urgent request {request_id} is waiting for approval.",
            notification_type="urgent_approval_requested",
            request_ids=[request_id],
        )
        return saved


def approve_pending_request(request_id: str, actor: str) -> ScheduledWork:
    request = requests_repository.get(request_id)
    if not request:
        raise ValueError("Request not found.")
    if request.approval_status != ApprovalStatus.PENDING_APPROVAL:
        raise ValueError("Request is not waiting for Approver approval.")
    start = request.recommended_start
    end = request.recommended_end
    if not start or not end:
        recommendation = recommend_slot(request)
        if not recommendation.recommended_work:
            raise ValueError("No feasible recommended slot exists.")
        start = recommendation.recommended_work.start_time
        end = recommendation.recommended_work.end_time
    scheduled = ScheduledWork(
        schedule_id="schedule-approver-approved",
        request_id=request_id,
        start_time=start,
        end_time=end,
        assigned_crew=request.required_crew,
        assigned_equipment=request.required_equipment,
        track_sector=request.track_sector,
        status=ApprovalStatus.SCHEDULED,
        changed_from_original=start != request.earliest_start,
        change_reason="Approved urgent or pending request at the recommended slot.",
    )
    proposed = [item for item in schedule_repository.list() if item.request_id != request_id]
    proposed.append(scheduled)
    errors = validate_scheduled_work(proposed, [*requests_repository.list(), request])
    errors.extend(validate_schedule_against_blocks(proposed))
    conflicts = detect_conflicts(proposed, requests_repository.list())
    if errors or conflicts:
        raise ValueError("; ".join(errors or [conflict.explanation for conflict in conflicts]))
    with unit_of_work() as work:
        saved = work.schedule.save(scheduled)
        work.requests.save(
            request.model_copy(
                update={
                    "approval_status": ApprovalStatus.SCHEDULED,
                    "locked": False,
                    "fixed_start": None,
                    "fixed_end": None,
                    "rejection_reason": None,
                }
            )
        )
        create_notification(
            owner=request.created_by,
            message=f"Request {request_id} was approved by an Approver.",
            notification_type="request_approved",
            request_ids=[request_id],
        )
        record_audit_event("request_approved", f"Request {request_id} was approved.", actor=actor, request_ids=[request_id])
        return saved


def reject_pending_request(request_id: str, reason: str, actor: str) -> MaintenanceRequest:
    request = requests_repository.get(request_id)
    if not request:
        raise ValueError("Request not found.")
    with unit_of_work() as work:
        saved = work.requests.save(
            request.model_copy(
                update={
                    "approval_status": ApprovalStatus.REJECTED,
                    "locked": False,
                    "rejection_reason": reason,
                }
            )
        )
        work.schedule.delete(request_id)
        create_notification(
            owner=request.created_by,
            message=f"Request {request_id} was rejected: {reason}",
            notification_type="request_rejected",
            request_ids=[request_id],
        )
        record_audit_event(
            "request_rejected",
            f"Request {request_id} was rejected.",
            actor=actor,
            request_ids=[request_id],
            details={"reason": reason},
        )
        return saved


def freeze_d_plus_three_batch(now: datetime | None = None) -> dict:
    settings = scheduling_settings_repository.get()
    target_date = frozen_date_cutoff(settings, now or planning_now())
    scheduled, errors, conflicts = build_optimised_schedule(ScheduleOption.MINIMUM_DISRUPTION)
    if errors or conflicts:
        return {
            "frozen": False,
            "target_date": target_date.isoformat(),
            "errors": errors or [conflict.explanation for conflict in conflicts],
            "locked_items": 0,
        }
    locked_count = 0
    with unit_of_work() as work:
        work.schedule.replace_all(scheduled)
        for item in scheduled:
            if item.start_time.date() > target_date:
                continue
            locked = item.model_copy(update={"status": ApprovalStatus.LOCKED})
            work.schedule.save(locked)
            request = work.requests.get(item.request_id)
            if request:
                work.requests.save(
                    request.model_copy(
                        update={
                            "approval_status": ApprovalStatus.LOCKED,
                            "locked": True,
                            "fixed_start": locked.start_time,
                            "fixed_end": locked.end_time,
                        }
                    )
                )
            locked_count += 1
        record_audit_event(
            "schedule_batch_frozen",
            f"Frozen schedule through {target_date.isoformat()}.",
            actor="system",
            request_ids=[item.request_id for item in scheduled if item.start_time.date() <= target_date],
            details={"target_date": target_date.isoformat(), "locked_items": locked_count},
        )
    return {"frozen": True, "target_date": target_date.isoformat(), "locked_items": locked_count, "errors": []}


def build_optimised_schedule(option: ScheduleOption) -> tuple[list[ScheduledWork], list[str], list[Conflict]]:
    requests = requests_with_locked_schedule()
    scheduled = optimise_schedule(requests, option)
    errors = validate_scheduled_work(scheduled, requests)
    errors.extend(validate_schedule_against_blocks(scheduled))
    if len(scheduled) != len(requests):
        scheduled_ids = {item.request_id for item in scheduled}
        missing = [request.request_id for request in requests if request.request_id not in scheduled_ids]
        errors.extend(f"{request_id} could not be placed within its allowed window." for request_id in missing)
    conflicts = detect_conflicts(scheduled, requests)
    return scheduled, errors, conflicts


def apply_schedule(schedule: list[ScheduledWork]) -> None:
    with unit_of_work() as work:
        work.schedule.replace_all(schedule)


def apply_alternative(option: ScheduleOption, request_ids: list[str] | None = None) -> tuple[list[ScheduledWork], list[str], list[Conflict]]:
    requests = requests_with_movable_schedule(request_ids)
    schedule = requested_slot_schedule(requests) if option == ScheduleOption.REQUESTED_SLOT else optimise_schedule(requests, option)
    errors = validate_scheduled_work(schedule, requests)
    errors.extend(validate_schedule_against_blocks(schedule))
    conflicts = detect_conflicts(schedule, requests)
    if errors or conflicts:
        return schedule, errors, conflicts
    apply_reschedule(schedule)
    return schedule, errors, conflicts


def generate_reschedule_proposals(request_ids: list[str] | None = None) -> list[ScheduleAlternative]:
    selected = set(request_ids or [])
    proposals = [alternative for alternative in generate_alternatives(requests_with_movable_schedule(request_ids)) if not alternative.conflicts]
    filtered = proposals if not selected else [
        alternative
        for alternative in proposals
        if selected.issubset({item.request_id for item in alternative.scheduled_work})
    ]
    if filtered:
        record_proposal_snapshot(request_ids or [], filtered)
    return filtered


def schedule_changes_for(schedule: list[ScheduledWork]) -> list[ScheduleChange]:
    changes: list[ScheduleChange] = []
    current_by_request = {item.request_id: item for item in schedule_repository.list()}
    requests_by_id = {request.request_id: request for request in requests_repository.list()}

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
    current_by_request = {item.request_id: item for item in schedule_repository.list()}
    with unit_of_work() as work:
        work.schedule.clear()
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
            work.schedule.save(applied)

            request = work.requests.get(item.request_id)
            if request:
                work.requests.save(
                    request.model_copy(
                        update={
                            "approval_status": status,
                            "locked": status == ApprovalStatus.LOCKED,
                            "fixed_start": applied.start_time if status == ApprovalStatus.LOCKED else None,
                            "fixed_end": applied.end_time if status == ApprovalStatus.LOCKED else None,
                        }
                    )
                )
