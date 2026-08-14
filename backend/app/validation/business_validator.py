from app.domain.catalog import CREWS, EQUIPMENT, TRACK_SECTORS, WORK_TYPES
from app.domain.models import MaintenanceRequest


def validate_business_rules(request: MaintenanceRequest) -> list[str]:
    errors: list[str] = []
    if request.track_sector not in TRACK_SECTORS:
        errors.append(f"Track sector must be one of: {', '.join(TRACK_SECTORS)}.")
    if request.work_type not in WORK_TYPES:
        errors.append(f"Work type must be one of: {', '.join(WORK_TYPES)}.")
    invalid_crews = [crew for crew in request.required_crew if crew not in CREWS]
    if invalid_crews:
        errors.append(f"Unknown crew values: {', '.join(invalid_crews)}.")
    invalid_equipment = [item for item in request.required_equipment if item not in EQUIPMENT]
    if invalid_equipment:
        errors.append(f"Unknown equipment values: {', '.join(invalid_equipment)}.")
    if request.deadline <= request.earliest_start:
        errors.append("Deadline must be after earliest start.")
    requested_minutes = (request.deadline - request.earliest_start).total_seconds() / 60
    if requested_minutes < request.duration_minutes:
        errors.append("Duration must fit between earliest start and deadline.")
    if request.locked and (request.fixed_start is None or request.fixed_end is None):
        errors.append("Locked requests must include fixed start and fixed end.")
    if request.fixed_start and request.fixed_end and request.fixed_end <= request.fixed_start:
        errors.append("Fixed end must be after fixed start.")
    return errors
