from fastapi import APIRouter, HTTPException

from app.domain.models import Notification
from app.repositories import notification_repository, unit_of_work

router = APIRouter()


@router.get("", response_model=list[Notification])
def list_notifications(owner: str | None = None, unread_only: bool = False) -> list[Notification]:
    return notification_repository.list(owner=owner, unread_only=unread_only)


@router.post("/{notification_id}/read", response_model=Notification)
def mark_notification_read(notification_id: str) -> Notification:
    notification = notification_repository.get(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")
    updated = notification.model_copy(update={"read": True})
    with unit_of_work() as work:
        return work.notifications.save(updated)
