from app.domain.models import MaintenanceRequest


def validate_business_rules(request: MaintenanceRequest) -> list[str]:
    errors: list[str] = []
    if request.deadline <= request.earliest_start:
        errors.append("Deadline must be after earliest start.")
    if request.locked and (request.fixed_start is None or request.fixed_end is None):
        errors.append("Locked requests must include fixed start and fixed end.")
    return errors
