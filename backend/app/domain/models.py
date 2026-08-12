from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import ApprovalStatus, ConflictSeverity, ConflictType, RequestSource, ScheduleOption


class MaintenanceRequest(BaseModel):
    request_id: str
    title: str
    track_sector: str
    work_type: str
    duration_minutes: int = Field(gt=0)
    earliest_start: datetime
    deadline: datetime
    priority: int = Field(ge=1, le=5)
    required_crew: list[str] = Field(default_factory=list)
    required_equipment: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    incompatible_work_types: list[str] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    locked: bool = False
    fixed_start: datetime | None = None
    fixed_end: datetime | None = None
    duration_variance_percent: int = Field(default=0, ge=0)
    notes: str | None = None
    created_by: str = "field"
    source: RequestSource = RequestSource.MANUAL


class ScheduledWork(BaseModel):
    schedule_id: str
    request_id: str
    start_time: datetime
    end_time: datetime
    assigned_crew: list[str] = Field(default_factory=list)
    assigned_equipment: list[str] = Field(default_factory=list)
    track_sector: str
    status: ApprovalStatus = ApprovalStatus.SCHEDULED
    changed_from_original: bool = False
    change_reason: str | None = None


class Conflict(BaseModel):
    conflict_id: str
    type: ConflictType
    severity: ConflictSeverity
    request_ids: list[str]
    resource: str | None = None
    time_overlap: tuple[datetime, datetime] | None = None
    explanation: str
    suggested_action: str | None = None


class KpiSnapshot(BaseModel):
    unresolved_conflicts: int
    critical_jobs_scheduled: int
    engineering_hours_utilisation: float
    estimated_overtime_minutes: int
    schedule_stability: float
    robustness_score: int


class ScheduleAlternative(BaseModel):
    option: ScheduleOption
    label: str
    scheduled_work: list[ScheduledWork]
    conflicts: list[Conflict]
    kpis: KpiSnapshot
    explanation: str
    rank: int = 0
    disruption_score: int = 0
    overtime_score: int = 0
    completion_score: int = 0
    critical_priority_score: int = 0
    overall_score: int = 0


class RequestFitResponse(BaseModel):
    request: MaintenanceRequest
    fits_current_schedule: bool
    conflicts: list[Conflict]
    suggested_alternatives: list[ScheduleAlternative] = Field(default_factory=list)
