from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class Scenario(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Line:
    code: str
    name: str


@dataclass(frozen=True)
class Station:
    station_id: str
    line_code: str
    seq: int
    is_interchange: bool


@dataclass(frozen=True)
class Sector:
    sector_id: str
    line_code: str
    from_station_id: str
    to_station_id: str
    seq: int
    is_shared: bool


@dataclass(frozen=True)
class LocationSupply:
    location_id: str
    location_kind: str
    line_code: str
    bound: str
    supply_capacity: int


@dataclass(frozen=True)
class BufferRule:
    nature_of_works: str
    up_to_buffer_sectors: int
    opposite_bound_required: bool


@dataclass(frozen=True)
class Contract:
    contract_number: str
    contract_description: str
    contract_award_date: date
    activity_type: str
    nature_of_activity: str
    contract_priority: int
    contract_completion_date: date
    planned_completion_date: date
    number_of_workfronts: int
    access_type: str
    number_of_maximum_access_per_week: int


@dataclass(frozen=True)
class Activity:
    activity_id: str
    contract_number: str
    activity_type: str
    start_location_id: str
    end_location_id: str
    total_accesses: int
    planned_start_date: date
    predecessor_activity_id: str | None
    activity_priority: int


@dataclass
class Instance:
    lines: dict[str, Line]
    stations: dict[tuple[str, str], Station]
    sectors: dict[str, Sector]
    supply: dict[str, LocationSupply]
    buffer_rules: dict[str, BufferRule]
    horizon_start: date
    horizon_weeks: int
    contracts: dict[str, Contract]
    activities: dict[str, Activity]


@dataclass(frozen=True)
class AccessAssignment:
    activity_id: str
    access_seq: int
    week: int
    eclo: int
    access_night: int


@dataclass(frozen=True)
class OccupancyAssignment:
    activity_id: str
    week: int
    location_id: str
    co_share_group: str


@dataclass(frozen=True)
class ContractResult:
    scenario: str
    contract_number: str
    simulated_completion_date: date
    overrun_days: int


@dataclass
class ValidationReport:
    scenario: str
    feasible: bool
    hard_violations: list[dict[str, str]]
    soft_scores: dict[str, Any]
    detail: dict[str, Any]


@dataclass
class ScenarioSolution:
    scenario: Scenario
    accesses: list[AccessAssignment]
    occupancy: list[OccupancyAssignment]
    results: list[ContractResult]
    validation: ValidationReport
    explanations: list[str] = field(default_factory=list)


@dataclass
class ScenarioRun:
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    message: str = "Waiting to run."
    solution: ScenarioSolution | None = None
    error: str | None = None


@dataclass
class SolveJob:
    job_id: str
    status: JobStatus
    created_at: datetime
    expires_at: datetime
    source: str
    instance: Instance
    scenarios: dict[Scenario, ScenarioRun]
    cancel_requested: bool = False
    error: str | None = None
