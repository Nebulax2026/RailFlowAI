from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    ApprovalStatus,
    BlockStatus,
    ConflictSeverity,
    ConflictType,
    DisplacementApprovalStatus,
    RequestSource,
    ScheduleHorizon,
    ScheduleOption,
)


class RailFlowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaintenanceRequest(RailFlowModel):
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
    recommended_start: datetime | None = None
    recommended_end: datetime | None = None
    rejection_reason: str | None = None
    requester_message: str | None = None


class ScheduledWork(RailFlowModel):
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


class SchedulingSettings(RailFlowModel):
    urgent_lead_days: int = Field(default=3, ge=1, le=30)


class BlockedTimeSlot(RailFlowModel):
    block_id: str
    track_sectors: list[str] = Field(min_length=1)
    start_time: datetime
    end_time: datetime
    reason: str
    created_by: str = "schedule_manager"
    status: BlockStatus = BlockStatus.ACTIVE
    created_at: datetime


class Notification(RailFlowModel):
    notification_id: str
    owner: str
    type: str
    message: str
    request_ids: list[str] = Field(default_factory=list)
    block_id: str | None = None
    proposal_id: str | None = None
    approval_id: str | None = None
    read: bool = False
    created_at: datetime


class DisplacementApproval(RailFlowModel):
    approval_id: str
    urgent_request_id: str
    displaced_request_id: str
    owner: str
    previous_start: datetime
    previous_end: datetime
    proposed_start: datetime
    proposed_end: datetime
    urgent_work: ScheduledWork
    displaced_work: ScheduledWork
    status: DisplacementApprovalStatus = DisplacementApprovalStatus.PENDING
    created_at: datetime
    decided_at: datetime | None = None


class Conflict(RailFlowModel):
    conflict_id: str
    type: ConflictType
    severity: ConflictSeverity
    request_ids: list[str]
    resource: str | None = None
    time_overlap: tuple[datetime, datetime] | None = None
    explanation: str
    suggested_action: str | None = None


class KpiSnapshot(RailFlowModel):
    unresolved_conflicts: int
    critical_jobs_scheduled: int
    engineering_hours_utilisation: float
    estimated_overtime_minutes: int
    schedule_stability: float
    robustness_score: int


class ScheduleAlternative(RailFlowModel):
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
    changed_jobs_count: int = 0
    moved_locked_count: int = 0
    churn_penalty: int = 0
    impact_summary: str | None = None


class ProposalSnapshot(RailFlowModel):
    proposal_id: str
    request_ids: list[str] = Field(default_factory=list)
    alternatives: list[ScheduleAlternative] = Field(default_factory=list)
    status: str = "generated"
    selected_option: ScheduleOption | None = None
    created_at: datetime
    applied_at: datetime | None = None
    applied_by: str | None = None


class AuditEvent(RailFlowModel):
    event_id: str
    event_type: str
    actor: str = "system"
    request_ids: list[str] = Field(default_factory=list)
    proposal_id: str | None = None
    summary: str
    details: dict = Field(default_factory=dict)
    created_at: datetime


class ScheduleChange(RailFlowModel):
    request_id: str
    owner: str
    previous_start: datetime | None = None
    previous_end: datetime | None = None
    proposed_start: datetime
    proposed_end: datetime
    was_locked: bool = False
    horizon: ScheduleHorizon = ScheduleHorizon.FLUID
    move_penalty: int = 0
    reason: str


class RequestFitResponse(RailFlowModel):
    request: MaintenanceRequest
    fits_current_schedule: bool
    conflicts: list[Conflict]
    suggested_alternatives: list[ScheduleAlternative] = Field(default_factory=list)
    scheduled_work: ScheduledWork | None = None
    requires_manager_review: bool = False
    affected_changes: list[ScheduleChange] = Field(default_factory=list)
    proposal_option: ScheduleOption | None = None


class SlotRecommendation(RailFlowModel):
    request: MaintenanceRequest
    available: bool
    recommended_work: ScheduledWork | None = None
    message: str | None = None


class RejectRequest(RailFlowModel):
    reason: str = Field(min_length=1)


class UrgentConfirmRequest(RailFlowModel):
    requester_message: str | None = None


class ProposalRequest(RailFlowModel):
    request_ids: list[str] = Field(default_factory=list)
    proposal_id: str | None = None


class ApproveRequest(RailFlowModel):
    request_ids: list[str] = Field(default_factory=list)
