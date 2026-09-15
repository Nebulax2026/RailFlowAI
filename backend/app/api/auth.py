from fastapi import HTTPException


APPROVER_ROLES = {"approver", "schedule_manager"}
SCHEDULE_MANAGER_ROLE = "schedule_manager"


def require_schedule_manager(role: str, action: str) -> None:
    if role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail=f"Only Approvers can {action}.")
