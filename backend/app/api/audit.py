from fastapi import APIRouter, HTTPException

from app.domain.models import AuditEvent
from app.repositories import audit_event_repository

router = APIRouter()


@router.get("", response_model=list[AuditEvent])
def list_audit_events(request_id: str | None = None, event_type: str | None = None) -> list[AuditEvent]:
    return audit_event_repository.list(request_id=request_id, event_type=event_type)


@router.get("/{event_id}", response_model=AuditEvent)
def get_audit_event(event_id: str) -> AuditEvent:
    event = audit_event_repository.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Audit event not found.")
    return event
