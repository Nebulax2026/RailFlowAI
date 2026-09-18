from __future__ import annotations

from dataclasses import dataclass, replace

from app.ps1.cpu_budget import resolve_workers, validate_workers
from app.ps1.models import ScenarioSolution


@dataclass(frozen=True)
class SearchConfig:
    strategy: str = "integrated"
    initialization: str = "direct"
    time_limit_seconds: float = 30
    workers: int | str = "auto"
    seed: int = 42
    memory_limit_mb: int = 2048
    initial_fraction: float = 0.4
    repair_seconds: float = 2
    neighborhood_min: float = 0.15
    neighborhood_max: float = 0.7
    restart_every: int = 6

    def __post_init__(self):
        if self.strategy not in {"integrated", "random_lns", "alns"}:
            raise ValueError("Unknown search strategy.")
        if self.initialization not in {"direct", "feasibility"}:
            raise ValueError("Unknown initialization.")
        validate_workers(self.workers)
        if not 0.2 <= self.time_limit_seconds <= 600:
            raise ValueError("Use 0.2–600 seconds.")
        if not 256 <= self.memory_limit_mb <= 16384 or not 0 <= self.seed <= 2**31 - 1:
            raise ValueError("Invalid memory limit or seed.")
        if not 0 < self.initial_fraction <= 1 or not 0 < self.neighborhood_min <= self.neighborhood_max <= 1:
            raise ValueError("Invalid search fractions.")
        if self.repair_seconds <= 0 or self.restart_every < 1:
            raise ValueError("Invalid repair/restart configuration.")

    def resolved(self):
        return replace(self, workers=resolve_workers(self.workers))


@dataclass
class SearchResult:
    solution: ScenarioSolution | None
    diagnostics: dict


OPERATORS = ("delay", "bottleneck", "sharing", "precedence", "contract", "diversify")
