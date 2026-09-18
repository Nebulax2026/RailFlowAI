from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Callable

from app.ps1.cpu_budget import resolve_workers, validate_workers
from app.ps1.models import Instance, ScenarioSolution


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
            raise ValueError("Unknown Scenario A strategy.")
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


def solve(instance: Instance, config: SearchConfig = SearchConfig(),
          cancelled: Callable[[], bool] = lambda: False,
          checkpoint: Callable[[ScenarioSolution, dict], None] | None = None) -> SearchResult:
    # All selectable strategies share the compatibility constraints and CSV
    # validator. Keep this entry point for the existing Scenario A API/CLI.
    from app.ps1.models import Scenario
    from app.ps1.scenario_search import solve as solve_shared
    return solve_shared(instance, Scenario.A, config, cancelled, checkpoint)


def neighborhood(instance, p, solution, operator, fraction, rng):
    ids = sorted(instance.activities)
    target = max(1, math.ceil(len(ids) * fraction))
    costs = solution.validation.detail.get("activity_costs", {})
    weeks = defaultdict(set)
    for r in solution.accesses:
        weeks[r.activity_id].add(r.week)
    seed = rng.choices(ids, weights=[1 + costs.get(a, 0) for a in ids])[0]
    selected = {seed}
    if operator == "delay":
        related = p.spatial[seed] | p.resources[seed] | p.predecessors[seed] | p.successors[seed]
    elif operator == "bottleneck":
        hotspots = solution.validation.detail.get("capacity_hotspots", [])
        if hotspots:
            h = rng.choice(hotspots)
            related = {a for a in ids if h["location_id"] in p.work[a] | p.reserve[a] and any(abs(w - h["week"]) <= 2 for w in weeks[a])}
        else:
            related = p.spatial[seed]
    elif operator == "sharing":
        related = p.sharing[seed]
    elif operator == "precedence":
        related, pending = set(), [seed]
        while pending:
            a = pending.pop()
            for b in p.predecessors[a] | p.successors[a]:
                if b not in related and b != seed:
                    related.add(b); pending.append(b)
    elif operator == "contract":
        related = p.resources[seed]
    else:
        if rng.random() < 0.5:
            week = rng.randint(1, instance.horizon_weeks)
            related = {a for a in ids if any(abs(w - week) <= 1 for w in weeks[a])}
        else:
            related = p.spatial[seed] | p.sharing[seed] | p.resources[seed]
    pool = sorted(related - selected)
    rng.shuffle(pool)
    selected.update(pool[:max(0, target - len(selected))])
    rest = sorted(set(ids) - selected); rng.shuffle(rest)
    selected.update(rest[:max(0, target - len(selected))])
    # Release every existing shared-group member transitively. All location slot
    # and local night variables remain free globally, even outside this closure.
    groups = defaultdict(set)
    for r in solution.occupancy:
        groups[r.location_id, r.week, r.co_share_group].add(r.activity_id)
    changed = True
    while changed:
        old = len(selected)
        for members in groups.values():
            if members & selected:
                selected.update(members)
        changed = len(selected) != old
    return selected
