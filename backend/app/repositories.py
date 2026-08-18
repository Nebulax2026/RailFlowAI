from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from app.domain.enums import ScheduleOption
from app.domain.models import AuditEvent, MaintenanceRequest, ProposalSnapshot, ScheduledWork
from app.storage import AUDIT_EVENTS, PROPOSAL_SNAPSHOTS, REQUESTS, SCHEDULED_WORK, persistence_transaction


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


class RailFlowUnitOfWork:
    def __init__(self) -> None:
        self.requests = RequestRepository()
        self.schedule = ScheduleRepository()
        self.proposals = ProposalSnapshotRepository()
        self.audit = AuditEventRepository()

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


@contextmanager
def unit_of_work() -> Iterator[RailFlowUnitOfWork]:
    with RailFlowUnitOfWork() as work:
        yield work
