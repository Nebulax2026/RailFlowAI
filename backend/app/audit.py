from datetime import datetime, timezone
from uuid import uuid4

from app.domain.models import AuditEvent
from app.repositories import audit_event_repository


def record_audit_event(
    event_type: str,
    summary: str,
    actor: str = "system",
    request_ids: list[str] | None = None,
    proposal_id: str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_id=f"audit-{uuid4().hex}",
        event_type=event_type,
        actor=actor,
        request_ids=request_ids or [],
        proposal_id=proposal_id,
        summary=summary,
        details=details or {},
        created_at=datetime.now(timezone.utc),
    )
    return audit_event_repository.save(event)
