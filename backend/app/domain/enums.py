from enum import StrEnum


class RequestSource(StrEnum):
    MANUAL = "manual"
    CSV = "csv"
    JSON = "json"
    OFFICIAL_DATASET = "official_dataset"
    EMERGENCY = "emergency"


class ApprovalStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    LOCKED = "locked"
    SCHEDULED = "scheduled"
    CONFLICT = "conflict"


class ConflictType(StrEnum):
    TRACK = "track"
    CREW = "crew"
    EQUIPMENT = "equipment"
    SAFETY = "safety"
    DEPENDENCY = "dependency"
    ENGINEERING_HOURS = "engineering_hours"


class ConflictSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScheduleOption(StrEnum):
    REQUESTED_SLOT = "requested_slot"
    MINIMUM_DISRUPTION = "minimum_disruption"
    MINIMUM_OVERTIME = "minimum_overtime"
    MAXIMUM_COMPLETION = "maximum_completion"
    CRITICAL_WORK_FIRST = "critical_work_first"


class ScheduleHorizon(StrEnum):
    FROZEN = "frozen"
    FIRM = "firm"
    FLUID = "fluid"
