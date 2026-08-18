from collections.abc import Iterator
from contextlib import contextmanager

from app.domain.enums import BlockStatus, DisplacementApprovalStatus, ScheduleOption
from app.domain.models import (
    AuditEvent,
    BlockedTimeSlot,
    DisplacementApproval,
    MaintenanceRequest,
    Notification,
    ProposalSnapshot,
    ScheduledWork,
    SchedulingSettings,
)
from app.storage import (
    AUDIT_EVENTS,
    BLOCKED_TIME_SLOTS,
    DISPLACEMENT_APPROVALS,
    NOTIFICATIONS,
    PROPOSAL_SNAPSHOTS,
    REQUESTS,
    SCHEDULED_WORK,
    SETTINGS,
    persistence_transaction,
)


class RequestRepository:
    def list(self) -> list[MaintenanceRequest]:
        return list(REQUESTS.values())

    def get(self, request_id: str) -> MaintenanceRequest | None:
        return REQUESTS.get(request_id)

    def save(self, request: MaintenanceRequest) -> MaintenanceRequest:
        REQUESTS[request.request_id] = request
        return request

    def delete(self, request_id: str) -> MaintenanceRequest | None:
        return REQUESTS.pop(request_id, None)

    def clear(self) -> None:
        REQUESTS.clear()


class ScheduleRepository:
    def list(self) -> list[ScheduledWork]:
        return list(SCHEDULED_WORK.values())

    def get(self, request_id: str) -> ScheduledWork | None:
        return SCHEDULED_WORK.get(request_id)

    def save(self, scheduled_work: ScheduledWork) -> ScheduledWork:
        SCHEDULED_WORK[scheduled_work.request_id] = scheduled_work
        return scheduled_work

    def replace_all(self, scheduled_work: list[ScheduledWork]) -> None:
        SCHEDULED_WORK.clear()
        for item in scheduled_work:
            SCHEDULED_WORK[item.request_id] = item

    def delete(self, request_id: str) -> ScheduledWork | None:
        return SCHEDULED_WORK.pop(request_id, None)

    def clear(self) -> None:
        SCHEDULED_WORK.clear()


class ProposalSnapshotRepository:
    def list(self) -> list[ProposalSnapshot]:
        return sorted(PROPOSAL_SNAPSHOTS.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, proposal_id: str) -> ProposalSnapshot | None:
        return PROPOSAL_SNAPSHOTS.get(proposal_id)

    def save(self, snapshot: ProposalSnapshot) -> ProposalSnapshot:
        PROPOSAL_SNAPSHOTS[snapshot.proposal_id] = snapshot
        return snapshot

    def latest_generated_for(self, request_ids: list[str], option: ScheduleOption) -> ProposalSnapshot | None:
        selected = set(request_ids)
        candidates = [
            snapshot
            for snapshot in PROPOSAL_SNAPSHOTS.values()
            if snapshot.status == "generated"
            and set(snapshot.request_ids) == selected
            and any(alternative.option == option for alternative in snapshot.alternatives)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.created_at)

    def clear(self) -> None:
        PROPOSAL_SNAPSHOTS.clear()


class AuditEventRepository:
    def list(self, request_id: str | None = None, event_type: str | None = None) -> list[AuditEvent]:
        events = AUDIT_EVENTS.values()
        if request_id:
            events = [event for event in events if request_id in event.request_ids]
        if event_type:
            events = [event for event in events if event.event_type == event_type]
        return sorted(events, key=lambda item: item.created_at, reverse=True)

    def get(self, event_id: str) -> AuditEvent | None:
        return AUDIT_EVENTS.get(event_id)

    def save(self, event: AuditEvent) -> AuditEvent:
        AUDIT_EVENTS[event.event_id] = event
        return event

    def clear(self) -> None:
        AUDIT_EVENTS.clear()


class SchedulingSettingsRepository:
    key = "scheduling"

    def get(self) -> SchedulingSettings:
        settings = SETTINGS.get(self.key)
        if settings:
            return settings
        settings = SchedulingSettings()
        SETTINGS[self.key] = settings
        return settings

    def save(self, settings: SchedulingSettings) -> SchedulingSettings:
        SETTINGS[self.key] = settings
        return settings

    def clear(self) -> None:
        SETTINGS.clear()


class BlockedTimeSlotRepository:
    def list(self, active_only: bool = False) -> list[BlockedTimeSlot]:
        slots = BLOCKED_TIME_SLOTS.values()
        if active_only:
            slots = [slot for slot in slots if slot.status == BlockStatus.ACTIVE]
        return sorted(slots, key=lambda item: item.start_time)

    def get(self, block_id: str) -> BlockedTimeSlot | None:
        return BLOCKED_TIME_SLOTS.get(block_id)

    def save(self, slot: BlockedTimeSlot) -> BlockedTimeSlot:
        BLOCKED_TIME_SLOTS[slot.block_id] = slot
        return slot

    def delete(self, block_id: str) -> BlockedTimeSlot | None:
        return BLOCKED_TIME_SLOTS.pop(block_id, None)

    def clear(self) -> None:
        BLOCKED_TIME_SLOTS.clear()


class NotificationRepository:
    def list(self, owner: str | None = None, unread_only: bool = False) -> list[Notification]:
        notifications = NOTIFICATIONS.values()
        if owner:
            notifications = [notification for notification in notifications if notification.owner == owner]
        if unread_only:
            notifications = [notification for notification in notifications if not notification.read]
        return sorted(notifications, key=lambda item: item.created_at, reverse=True)

    def get(self, notification_id: str) -> Notification | None:
        return NOTIFICATIONS.get(notification_id)

    def save(self, notification: Notification) -> Notification:
        NOTIFICATIONS[notification.notification_id] = notification
        return notification

    def clear(self) -> None:
        NOTIFICATIONS.clear()


class DisplacementApprovalRepository:
    def list(
        self,
        owner: str | None = None,
        status: DisplacementApprovalStatus | None = None,
    ) -> list[DisplacementApproval]:
        approvals = DISPLACEMENT_APPROVALS.values()
        if owner:
            approvals = [approval for approval in approvals if approval.owner == owner]
        if status:
            approvals = [approval for approval in approvals if approval.status == status]
        return sorted(approvals, key=lambda item: item.created_at, reverse=True)

    def get(self, approval_id: str) -> DisplacementApproval | None:
        return DISPLACEMENT_APPROVALS.get(approval_id)

    def save(self, approval: DisplacementApproval) -> DisplacementApproval:
        DISPLACEMENT_APPROVALS[approval.approval_id] = approval
        return approval

    def clear(self) -> None:
        DISPLACEMENT_APPROVALS.clear()


class RailFlowUnitOfWork:
    def __init__(self) -> None:
        self.requests = RequestRepository()
        self.schedule = ScheduleRepository()
        self.proposals = ProposalSnapshotRepository()
        self.audit = AuditEventRepository()
        self.settings = SchedulingSettingsRepository()
        self.blocked_slots = BlockedTimeSlotRepository()
        self.notifications = NotificationRepository()
        self.displacement_approvals = DisplacementApprovalRepository()

    def __enter__(self) -> "RailFlowUnitOfWork":
        self._transaction = persistence_transaction()
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:  # type: ignore[no-untyped-def]
        return self._transaction.__exit__(exc_type, exc_value, traceback)


requests_repository = RequestRepository()
schedule_repository = ScheduleRepository()
proposal_snapshot_repository = ProposalSnapshotRepository()
audit_event_repository = AuditEventRepository()
scheduling_settings_repository = SchedulingSettingsRepository()
blocked_time_slot_repository = BlockedTimeSlotRepository()
notification_repository = NotificationRepository()
displacement_approval_repository = DisplacementApprovalRepository()


@contextmanager
def unit_of_work() -> Iterator[RailFlowUnitOfWork]:
    with RailFlowUnitOfWork() as work:
        yield work
