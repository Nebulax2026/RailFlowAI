"""Independent topology audit helpers used by regression tests."""
from __future__ import annotations

from collections import defaultdict, deque

from app.ps1.models import Instance


HEADERS = {
    "SCHEDULE_ACCESS.csv": ("activity_id", "access_seq", "week", "eclo", "access_night"),
    "SCHEDULE_OCCUPANCY.csv": ("activity_id", "week", "location_id", "co_share_group"),
    "RESULTS.csv": ("scenario", "contract_number", "simulated_completion_date", "overrun_days"),
}


def independent_footprints(instance: Instance, aid: str) -> tuple[set[str], set[str]]:
    """Walk the station graph, then expand adjacent edges by buffer radius."""
    a = instance.activities[aid]
    c = instance.contracts[a.contract_number]
    supply = instance.supply[a.start_location_id]
    line, bound = supply.line_code, supply.bound
    end_supply = instance.supply[a.end_location_id]
    if (line, bound) != (end_supply.line_code, end_supply.bound):
        raise ValueError("Endpoints use different lines/bounds.")
    edges = {s.sector_id: s for s in instance.sectors.values() if s.line_code == line}
    adjacency = defaultdict(list)
    for eid, e in edges.items():
        adjacency[e.from_station_id].append((e.to_station_id, eid))
        adjacency[e.to_station_id].append((e.from_station_id, eid))

    def endpoints(loc):
        if loc.startswith("PLAT:"):
            return {loc.split(":")[2]}, set()
        eid = loc.rsplit(":", 1)[0]
        e = edges[eid]
        return {e.from_station_id, e.to_station_id}, {eid}

    left, required = endpoints(a.start_location_id)
    right, more = endpoints(a.end_location_id)
    required |= more
    # Connect both endpoint sectors by the shortest station path.
    queue = deque((s, []) for s in sorted(left))
    visited = set(left)
    path = None
    while queue:
        station, traversed = queue.popleft()
        if station in right:
            path = traversed
            break
        for neighbor, edge in adjacency[station]:
            if neighbor not in visited:
                visited.add(neighbor); queue.append((neighbor, [*traversed, edge]))
    if path is None:
        raise ValueError("Disconnected activity path.")
    required.update(path)
    nodes = left | right
    for eid in required:
        nodes.update((edges[eid].from_station_id, edges[eid].to_station_id))
    actual = {eid + ":" + bound for eid in required} | {f"PLAT:{line}:{s}:{bound}" for s in nodes}
    expanded = set(required)
    rule = instance.buffer_rules[c.nature_of_activity]
    for _ in range(rule.up_to_buffer_sectors):
        expanded.update(eid for s in list(nodes) for _, eid in adjacency[s])
        for eid in expanded:
            nodes.update((edges[eid].from_station_id, edges[eid].to_station_id))
    footprint = {eid + ":" + bound for eid in expanded} | {f"PLAT:{line}:{s}:{bound}" for s in nodes}
    if rule.opposite_bound_required:
        opposite = "WB" if bound == "EB" else "EB"
        footprint.update(loc[:-2] + opposite for loc in list(footprint))
    if c.nature_of_activity == "Live" and any({edges[eid].from_station_id, edges[eid].to_station_id} == {"H01", "H02"} for eid in required):
        for other in instance.lines:
            if other == line:
                continue
            other_edges = {s.sector_id: s for s in instance.sectors.values() if s.line_code == other}
            crossed = {eid for eid, s in other_edges.items() if {s.from_station_id, s.to_station_id} == {"H01", "H02"}}
            other_nodes = {s for eid in crossed for s in (other_edges[eid].from_station_id, other_edges[eid].to_station_id)}
            for _ in range(rule.up_to_buffer_sectors):
                crossed.update(eid for eid, s in other_edges.items() if s.from_station_id in other_nodes or s.to_station_id in other_nodes)
                other_nodes.update(s for eid in crossed for s in (other_edges[eid].from_station_id, other_edges[eid].to_station_id))
            for direction in ("EB", "WB"):
                footprint.update(f"{eid}:{direction}" for eid in crossed)
                footprint.update(f"PLAT:{other}:{s}:{direction}" for s in other_nodes)
    if not footprint <= instance.supply.keys():
        raise ValueError("Required footprint absent from input supply.")
    return actual, footprint - actual


