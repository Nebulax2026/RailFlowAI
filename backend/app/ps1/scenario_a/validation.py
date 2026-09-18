"""CSV-only validation. Does not import the optimizer or its topology expansion."""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict, deque
from datetime import date, timedelta

from app.ps1.models import Instance, ValidationReport
from app.ps1.scenario_a.policy import POLICY_VERSION

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
    if c.nature_of_activity == "Live" and any(edges[eid].from_station_id == "H01" and edges[eid].to_station_id == "H02" for eid in expanded):
        for other in instance.lines:
            for direction in ("EB", "WB"):
                footprint.update((f"SEC:{other}:H01_H02:{direction}", f"PLAT:{other}:H01:{direction}", f"PLAT:{other}:H02:{direction}"))
    if not footprint <= instance.supply.keys():
        raise ValueError("Required footprint absent from input supply.")
    return actual, footprint - actual


def validate_csvs(instance: Instance, files: dict[str, bytes], expected_cost: int | None = None) -> ValidationReport:
    violations = []

    def fail(rule, detail):
        violations.append({"rule": rule, "severity": "hard", "detail": detail})

    def report(scores=None, detail=None):
        return ValidationReport("A", not violations, violations, scores or {}, {
            "validation_source": "independent-specification-validator",
            "official_validator_available": False, "policy": POLICY_VERSION,
            **(detail or {}),
        })

    tables = {}
    try:
        for filename, headers in HEADERS.items():
            reader = csv.DictReader(io.StringIO(files[filename].decode("utf-8-sig")))
            if tuple(reader.fieldnames or ()) != headers:
                raise ValueError(f"Invalid headers: {filename}")
            tables[filename] = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in tables[filename]):
                raise ValueError(f"Invalid column count: {filename}")
        access = [dict(activity_id=r["activity_id"], **{k: int(r[k]) for k in HEADERS["SCHEDULE_ACCESS.csv"][1:]}) for r in tables["SCHEDULE_ACCESS.csv"]]
        occupancy = [(r["activity_id"], int(r["week"]), r["location_id"], r["co_share_group"]) for r in tables["SCHEDULE_OCCUPANCY.csv"]]
        results = [(r["scenario"], r["contract_number"], date.fromisoformat(r["simulated_completion_date"]), int(r["overrun_days"])) for r in tables["RESULTS.csv"]]
    except (KeyError, ValueError, TypeError, UnicodeError, csv.Error) as exc:
        fail("schema", str(exc)); return report()
    by_activity = defaultdict(list)
    night_members = defaultdict(set)
    for r in access:
        aid, week = r["activity_id"], r["week"]
        if aid not in instance.activities:
            fail("activity", f"Unknown activity {aid}."); continue
        by_activity[aid].append(r)
        if not 1 <= week <= instance.horizon_weeks:
            fail("horizon", f"{aid}: week {week} outside horizon.")
        if r["eclo"] != 0:
            fail("eclo", f"{aid}: Scenario A requires eclo=0.")
        a = instance.activities[aid]
        c = instance.contracts[a.contract_number]
        if not 1 <= r["access_night"] <= c.number_of_maximum_access_per_week:
            fail("weekly_allocation", f"{aid}: invalid local access night.")
        night_members[(a.contract_number, a.activity_type, week, r["access_night"])].add(aid)
    for key, members in night_members.items():
        if len(members) > instance.contracts[key[0]].number_of_workfronts:
            fail("workfront", f"{key}: too many teams.")
    expected, reservations = set(), defaultdict(set)
    footprints = {}
    for aid, a in instance.activities.items():
        rows = by_activity[aid]
        weeks = [r["week"] for r in rows]
        if len(rows) != a.total_accesses:
            fail("workload", f"{aid}: {len(rows)} accesses, expected {a.total_accesses}.")
        if len(weeks) != len(set(weeks)):
            fail("weekly_activity", f"{aid}: duplicate access in a week.")
        if sorted(r["access_seq"] for r in rows) != list(range(1, len(rows) + 1)):
            fail("access_seq", f"{aid}: missing or duplicate sequence numbers.")
        if weeks and min(weeks) < max(1, (a.planned_start_date - instance.horizon_start).days // 7 + 1):
            fail("planned_start", f"{aid}: starts before planned week.")
        pred_rows = by_activity[a.predecessor_activity_id] if a.predecessor_activity_id else []
        if weeks and pred_rows and min(weeks) <= max(r["week"] for r in pred_rows):
            fail("predecessor", f"{aid}: successor must start in a strictly later week.")
        try:
            actual, reserve = independent_footprints(instance, aid)
            footprints[aid] = (actual, reserve)
            for week in set(weeks):
                expected.update((aid, week, loc) for loc in actual)
                for loc in reserve:
                    reservations[loc, week].add(aid)
        except (ValueError, KeyError) as exc:
            fail("topology", f"{aid}: {exc}")
    actual_keys = [(a, w, loc) for a, w, loc, _ in occupancy]
    if len(actual_keys) != len(set(actual_keys)):
        fail("occupancy_duplicate", "Duplicate activity/week/location rows.")
    missing, extra = expected - set(actual_keys), set(actual_keys) - expected
    if missing:
        fail("occupancy", f"Missing {len(missing)} required locations; example {sorted(missing)[0]}.")
    if extra:
        fail("occupancy", f"Unexpected occupancy; example {sorted(extra)[0]}.")
    groups = defaultdict(set)
    for aid, week, loc, group in occupancy:
        if not group.strip():
            fail("sharing", "Empty co_share_group.")
        if aid in instance.activities and loc in instance.supply:
            groups[(loc, week, group)].add(aid)
    slot_counts = Counter()
    actual_groups = defaultdict(list)
    partners = defaultdict(set)
    for (loc, week, group), members in groups.items():
        types = Counter(instance.contracts[instance.activities[a].contract_number].access_type for a in members)
        if len(members) > 4 or types["PC"] > 1 or (types["PM"] and len(members) > 1):
            fail("sharing", f"{loc}/{week}/{group}: illegal PM/PC/C mix.")
        slot_counts[(loc, week)] += 1
        actual_groups[loc, week].append(set(members))
        for aid in members:
            partners[week, aid].update(members - {aid})
    hotspots = []
    for loc, week in sorted(slot_counts.keys() | reservations.keys()):
        capacity = instance.supply[loc].supply_capacity
        reserved = reservations[(loc, week)]
        used = reservation_slots(instance, actual_groups[loc, week], reserved, {a: partners[week, a] for a in reserved}, capacity)
        if used is None:
            used = max(capacity + 1, slot_counts[(loc, week)])
            fail("closure_buffer_capacity" if reserved else "capacity", f"{loc} week {week}: no legal packing of work and {len(reserved)} reservations within supply {capacity}.")
        if used >= capacity:
            hotspots.append({"location_id": loc, "week": week, "used": used, "capacity": capacity})
    completions = {aid: instance.horizon_start + timedelta(days=7 * max(r["week"] for r in rows) - 1) for aid, rows in by_activity.items() if rows}
    result_map = {}
    for scenario, cid, completion, overrun in results:
        if scenario != "A" or cid not in instance.contracts or cid in result_map:
            fail("results", f"Unknown/duplicate contract or wrong scenario: {scenario}/{cid}."); continue
        result_map[cid] = (completion, overrun)
    overrun_total, overrunning, weighted, priority = 0, 0, 0, {"1": 0, "2": 0, "3": 0}
    activity_costs = {}
    for cid, c in instance.contracts.items():
        dates = [completions[a.activity_id] for a in instance.activities.values() if a.contract_number == cid and a.activity_id in completions]
        if not dates:
            fail("results", f"{cid}: no scheduled activities."); continue
        completion = max(dates)
        overrun = max(0, (completion - c.planned_completion_date).days)
        if result_map.get(cid) != (completion, overrun):
            fail("results", f"{cid}: completion/overrun does not match access CSV.")
        overrun_total += overrun; overrunning += int(overrun > 0)
    for aid, a in instance.activities.items():
        if aid not in completions:
            continue
        c = instance.contracts[a.contract_number]
        days = max(0, (completions[aid] - c.planned_completion_date).days)
        # Integer tenths, computed independently of model coefficients.
        cost = days * (100 if c.contract_priority == 1 else 10 if c.contract_priority == 2 else 1) * (13 if a.activity_priority == 1 else 12 if a.activity_priority == 2 else 10)
        weighted += cost; priority[str(c.contract_priority)] += days
        activity_costs[aid] = cost / 10
    if expected_cost is not None and weighted != expected_cost:
        fail("objective", f"CSV cost {weighted} tenths differs from optimizer {expected_cost}.")
    scores = {"overrun_days_total": overrun_total, "contracts_overrunning": overrunning,
              "priority_overrun": priority, "priority_weighted_score": weighted / 10,
              "eclo_nights_total": 0, "excess_access_nights_total": 0,
              "formula_version": "ps1-spec-activity-days-v1"}
    if not violations:
        scores["objective_score"] = weighted / 10
    return report(scores, {"capacity_hotspots": hotspots, "nights_scheduled": len(access), "eclo_nights": 0,
                           "activity_costs": activity_costs})


def reservation_slots(instance, actual_groups, reserved, partners, capacity):
    """Independent bounded backtracking, not the optimizer's CP-SAT model.

Actual CSV groups remain fixed. Only implicit external reservations are packed;
every sharing pair must be witnessed in a real work group elsewhere that week.
"""
    if len(actual_groups) > capacity:
        return None
    groups = [set(g) for g in actual_groups]
    types = {a: instance.contracts[item.contract_number].access_type for a, item in instance.activities.items()}
    ordered = sorted(reserved, key=lambda a: (len(partners.get(a, set())), a))
    failed = set()

    def place(index):
        if index == len(ordered):
            return len(groups)
        signature = (index, tuple(sorted(tuple(sorted(g)) for g in groups)))
        if signature in failed:
            return None
        aid = ordered[index]
        for group in groups:
            if len(group) >= 4 or not group <= partners.get(aid, set()):
                continue
            mix = [types[a] for a in group] + [types[aid]]
            if "PM" in mix or mix.count("PC") > 1:
                continue
            group.add(aid)
            result = place(index + 1)
            group.remove(aid)
            if result is not None:
                return result
        if len(groups) < capacity:
            groups.append({aid})
            result = place(index + 1)
            groups.pop()
            if result is not None:
                return result
        failed.add(signature)
        return None
    return place(0)
