"""Prepared activity relationships for diagnostics and search neighborhoods.

Production A/B/C searches share the observed weekly-closure policy.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ps1.models import Instance

from app.ps1.safety import POLICY_VERSION
SOURCE_REVISION = "966c976005db2e3e40a691cff268fdb8f396a5df"


@dataclass
class Prepared:
    work: dict[str, frozenset[str]]
    reserve: dict[str, frozenset[str]]
    earliest: dict[str, int]
    latest: dict[str, int]
    weights: dict[str, int]
    predecessors: dict[str, set[str]]
    successors: dict[str, set[str]]
    spatial: dict[str, set[str]]
    sharing: dict[str, set[str]]
    resources: dict[str, set[str]]
    order: list[str]


def prepare(instance: Instance) -> Prepared:
    work, reserve = {}, {}
    ids = sorted(instance.activities)
    predecessors = {a: set() for a in ids}
    successors = {a: set() for a in ids}
    weights = {}
    for aid in ids:
        a = instance.activities[aid]
        c = instance.contracts[a.contract_number]
        start, end = instance.supply[a.start_location_id], instance.supply[a.end_location_id]
        if (start.line_code, start.bound) != (end.line_code, end.bound):
            raise ValueError(f"{aid}: endpoints must use one line and bound.")
        line, bound = start.line_code, start.bound
        sectors = sorted((s for s in instance.sectors.values() if s.line_code == line), key=lambda s: s.seq)
        if not sectors or any(l.to_station_id != r.from_station_id for l, r in zip(sectors, sectors[1:])):
            raise ValueError(f"{line}: expected a connected linear network.")
        stations = [sectors[0].from_station_id, *[s.to_station_id for s in sectors]]
        positions = {f"PLAT:{line}:{s}:{bound}": (i, i) for i, s in enumerate(stations)}
        positions.update({f"{s.sector_id}:{bound}": (i, i + 1) for i, s in enumerate(sectors)})
        if a.start_location_id not in positions or a.end_location_id not in positions:
            raise ValueError(f"{aid}: endpoint missing from topology.")
        low = min(positions[a.start_location_id][0], positions[a.end_location_id][0])
        high = max(positions[a.start_location_id][1], positions[a.end_location_id][1])

        def span(left: int, right: int) -> set[str]:
            return ({f"PLAT:{line}:{s}:{bound}" for s in stations[left:right + 1]}
                    | {f"{s.sector_id}:{bound}" for s in sectors[left:right]})

        actual = span(low, high)
        from app.ps1.topology import closure_locations
        footprint = actual | closure_locations(instance, a)
        missing = footprint - instance.supply.keys()
        if missing:
            raise ValueError(f"{aid}: required locations absent from supply: {sorted(missing)}")
        work[aid], reserve[aid] = frozenset(actual), frozenset(footprint - actual)
        weights[aid] = {1: 100, 2: 10, 3: 1}[c.contract_priority] * {1: 13, 2: 12, 3: 10}[a.activity_priority]
        if a.predecessor_activity_id:
            predecessors[aid].add(a.predecessor_activity_id)
            successors[a.predecessor_activity_id].add(aid)
    order, pending = [], set(ids)
    while pending:
        ready = sorted(a for a in pending if not (predecessors[a] & pending))
        if not ready:
            raise ValueError("Predecessor cycle.")
        order.extend(ready)
        pending.difference_update(ready)
    earliest, latest = {}, {}
    for aid in order:
        a = instance.activities[aid]
        earliest[aid] = max(1, (a.planned_start_date - instance.horizon_start).days // 7 + 1,
                            max((earliest[p] + instance.activities[p].total_accesses for p in predecessors[aid]), default=1))
    for aid in reversed(order):
        latest[aid] = min(instance.horizon_weeks,
                          min((latest[s] - instance.activities[s].total_accesses for s in successors[aid]), default=instance.horizon_weeks))
    spatial, sharing, resources = ({a: set() for a in ids} for _ in range(3))
    for i, a in enumerate(ids):
        ca = instance.contracts[instance.activities[a].contract_number]
        for b in ids[i + 1:]:
            cb = instance.contracts[instance.activities[b].contract_number]
            if (work[a] | reserve[a]) & (work[b] | reserve[b]):
                spatial[a].add(b); spatial[b].add(a)
            if work[a] & work[b] and sorted((ca.access_type, cb.access_type)) in (["C", "C"], ["C", "PC"]):
                sharing[a].add(b); sharing[b].add(a)
            if (ca.contract_number, instance.activities[a].activity_type) == (cb.contract_number, instance.activities[b].activity_type):
                resources[a].add(b); resources[b].add(a)
    return Prepared(work, reserve, earliest, latest, weights, predecessors, successors, spatial, sharing, resources, order)
