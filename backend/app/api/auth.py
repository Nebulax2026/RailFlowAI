from fastapi import HTTPException


SCHEDULE_MANAGER_ROLE = "schedule_manager"


def require_schedule_manager(role: str, action: str) -> None:
    if role != SCHEDULE_MANAGER_ROLE:
        raise HTTPException(status_code=403, detail=f"Only Schedule Managers can {action}.")
