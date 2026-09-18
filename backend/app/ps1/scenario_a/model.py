from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from ortools.sat.python import cp_model

from app.ps1.models import AccessAssignment, ContractResult, Instance, OccupancyAssignment, Scenario, ScenarioSolution, ValidationReport
from app.ps1.scenario_a.policy import Prepared


@dataclass
class IntegratedModel:
    model: cp_model.CpModel
    x: dict
    nights: dict
    slots: dict
    cost: cp_model.LinearExpr
    instance: Instance
    prepared: Prepared

    def extract(self, value) -> ScenarioSolution:
        chosen = defaultdict(list)
        for (aid, week), var in self.x.items():
            if value(var):
                chosen[aid].append(week)
        accesses, occupancy = [], []
        for aid, weeks in sorted(chosen.items()):
            for seq, week in enumerate(sorted(weeks), 1):
                night = next(n for (a, w, n), v in self.nights.items() if a == aid and w == week and value(v))
                accesses.append(AccessAssignment(aid, seq, week, 0, night))
        for (aid, week, location, slot), var in self.slots.items():
            if location in self.prepared.work[aid] and value(var):
                occupancy.append(OccupancyAssignment(aid, week, location, f"s{slot + 1}"))
        return assemble(self.instance, accesses, occupancy)


def build_model(instance: Instance, p: Prepared, deadline: float) -> IntegratedModel:
    model = cp_model.CpModel()
    x, nights, slots, starts, ends = {}, {}, {}, {}, {}
    resource_terms, location_terms = defaultdict(list), defaultdict(list)
    objective = []
    for aid in sorted(instance.activities):
        if time.monotonic() >= deadline:
            raise TimeoutError("Time budget exhausted during model construction.")
        a = instance.activities[aid]
        c = instance.contracts[a.contract_number]
        weeks = list(range(p.earliest[aid], p.latest[aid] + 1))
        if len(weeks) < a.total_accesses:
            model.add(False)
        for w in weeks:
            selected = model.new_bool_var(f"x:{aid}:{w}")
            x[aid, w] = selected
            local_nights = []
            for n in range(1, c.number_of_maximum_access_per_week + 1):
                v = model.new_bool_var(f"n:{aid}:{w}:{n}")
                nights[aid, w, n] = v
                local_nights.append(v)
                resource_terms[a.contract_number, a.activity_type, w, n].append(v)
            model.add(sum(local_nights) == selected)
            for loc in sorted(p.work[aid] | p.reserve[aid]):
                location_terms[loc, w].append(aid)
        model.add(sum(x[aid, w] for w in weeks) == a.total_accesses)
        starts[aid] = model.new_int_var(1, instance.horizon_weeks + 1, f"start:{aid}")
        ends[aid] = model.new_int_var(0, instance.horizon_weeks, f"end:{aid}")
        if weeks:
            model.add_min_equality(starts[aid], [w * x[aid, w] + (instance.horizon_weeks + 1) * (1 - x[aid, w]) for w in weeks])
            model.add_max_equality(ends[aid], [w * x[aid, w] for w in weeks])
        planned_offset = (c.planned_completion_date - instance.horizon_start).days
        late = model.new_int_var(0, max(0, 7 * instance.horizon_weeks - 1 - planned_offset), f"late_days:{aid}")
        model.add_max_equality(late, [0, 7 * ends[aid] - 1 - planned_offset])
        objective.append(p.weights[aid] * late)
    for aid in starts:
        for pred in p.predecessors[aid]:
            model.add(ends[pred] < starts[aid])
    for (cid, _kind, _week, _night), terms in resource_terms.items():
        model.add(sum(terms) <= instance.contracts[cid].number_of_workfronts)
    for (loc, week), members in sorted(location_terms.items()):
        if time.monotonic() >= deadline:
            raise TimeoutError("Time budget exhausted during slot model construction.")
        # More slots than affected activities are provably unnecessary.
        capacity = min(instance.supply[loc].supply_capacity, len(members))
        by_slot, previous_used = defaultdict(list), None
        for aid in members:
            choices = []
            for s in range(capacity):
                v = model.new_bool_var(f"slot:{aid}:{week}:{loc}:{s}")
                slots[aid, week, loc, s] = v
                choices.append(v); by_slot[s].append((aid, v))
            model.add(sum(choices) == x[aid, week])
        for s, terms in by_slot.items():
            used = model.new_bool_var(f"used:{loc}:{week}:{s}")
            count = sum(v for _, v in terms)
            pcs, exclusive = [], []
            for aid, v in terms:
                access_type = instance.contracts[instance.activities[aid].contract_number].access_type
                if access_type == "PM":
                    exclusive.append(v)
                elif access_type == "PC":
                    pcs.append(v)
            model.add(count <= 4 * used)
            model.add(count >= used)
            model.add(count + 3 * sum(exclusive) <= 4)
            model.add(sum(pcs) <= 1)
            # Only local slot labels are interchangeable; no cross-location link.
            if previous_used is not None:
                model.add(previous_used >= used)
            previous_used = used
    # A reservation never grants blanket exemption to an external activity.
    # Direct partners must actually co-share a work location in this week.
    # These are Boolean relationships, not global day/slot indices.
    partners = {}
    for (loc, week), members in sorted(location_terms.items()):
        if time.monotonic() >= deadline:
            raise TimeoutError("Time budget exhausted during safety constraints.")
        capacity = min(instance.supply[loc].supply_capacity, len(members))
        for i, aid in enumerate(members):
            for bid in members[i + 1:]:
                if loc not in p.reserve[aid] and loc not in p.reserve[bid]:
                    continue
                key = (*sorted((aid, bid)), week)
                if key not in partners:
                    witnesses = []
                    if bid in p.sharing[aid]:
                        for shared in sorted(p.work[aid] & p.work[bid]):
                            for s in range(instance.supply[shared].supply_capacity):
                                va, vb = slots.get((aid, week, shared, s)), slots.get((bid, week, shared, s))
                                if va is not None and vb is not None:
                                    both = model.new_bool_var(f"share:{aid}:{bid}:{week}:{shared}:{s}")
                                    model.add(both <= va); model.add(both <= vb)
                                    model.add(both >= va + vb - 1)
                                    witnesses.append(both)
                    if witnesses:
                        partner = model.new_bool_var(f"partner:{aid}:{bid}:{week}")
                        model.add_max_equality(partner, witnesses)
                        partners[key] = partner
                    else:
                        partners[key] = 0
                for s in range(capacity):
                    model.add(slots[aid, week, loc, s] + slots[bid, week, loc, s] <= 1 + partners[key])
    cost = sum(objective)
    model.minimize(cost)
    return IntegratedModel(model, x, nights, slots, cost, instance, p)


def assemble(instance, accesses, occupancy):
    weeks = defaultdict(list)
    for r in accesses:
        weeks[instance.activities[r.activity_id].contract_number].append(r.week)
    results = []
    for cid, values in sorted(weeks.items()):
        completion = instance.horizon_start + timedelta(days=7 * max(values) - 1)
        results.append(ContractResult("A", cid, completion, max(0, (completion - instance.contracts[cid].planned_completion_date).days)))
    return ScenarioSolution(Scenario.A, sorted(accesses, key=lambda r: (r.activity_id, r.access_seq)),
                            sorted(occupancy, key=lambda r: (r.activity_id, r.week, r.location_id)), results,
                            ValidationReport("A", False, [], {}, {}))


def greedy(instance: Instance, p: Prepared, deadline: float) -> ScenarioSolution | None:
    """Priority/slack constructive baseline. Failure does not prove infeasibility."""
    assigned, weekly_members, resource_count = {}, defaultdict(set), defaultdict(int)
    pending = set(instance.activities)
    while pending:
        if time.monotonic() >= deadline:
            return None
        ready = [aid for aid in pending if p.predecessors[aid] <= assigned.keys()]
        aid = min(ready, key=lambda a: (-p.weights[a], p.latest[a] - p.earliest[a] - instance.activities[a].total_accesses, -len(p.spatial[a]), a))
        a = instance.activities[aid]; c = instance.contracts[a.contract_number]
        earliest = max(p.earliest[aid], max((max(assigned[b]) + 1 for b in p.predecessors[aid]), default=1))
        chosen = []
        for w in range(earliest, p.latest[aid] + 1):
            resource = (a.contract_number, a.activity_type, w)
            if resource_count[resource] >= c.number_of_workfronts * c.number_of_maximum_access_per_week:
                continue
            if greedy_layout(instance, p, weekly_members[w] | {aid}) is None:
                continue
            chosen.append(w); resource_count[resource] += 1
            weekly_members[w].add(aid)
            if len(chosen) == a.total_accesses:
                break
        if len(chosen) != a.total_accesses:
            return None
        assigned[aid] = chosen; pending.remove(aid)
    accesses, occupancy, teams = [], [], defaultdict(int)
    for aid, weeks in sorted(assigned.items()):
        a = instance.activities[aid]; c = instance.contracts[a.contract_number]
        for seq, w in enumerate(weeks, 1):
            key = (a.contract_number, a.activity_type, w)
            night = teams[key] // c.number_of_workfronts + 1
            teams[key] += 1
            accesses.append(AccessAssignment(aid, seq, w, 0, night))
    for week, members in sorted(weekly_members.items()):
        for loc, groups in greedy_layout(instance, p, members).items():
            for slot, group in enumerate(groups, 1):
                occupancy.extend(OccupancyAssignment(a, week, loc, f"s{slot}") for a in group)
    return assemble(instance, accesses, occupancy)


def greedy_layout(instance, p, members):
    # The heuristic consults the independent safety checker. The integrated
    # CP-SAT model does not use this packing procedure.
    from app.ps1.scenario_a.validation import reservation_slots
    work, reserve, partners = defaultdict(list), defaultdict(set), defaultdict(set)
    for aid in sorted(members):
        for loc in p.work[aid]:
            work[loc].append(aid)
        for loc in p.reserve[aid]:
            reserve[loc].add(aid)
    groups = {loc: pack(instance, items) for loc, items in work.items()}
    for local in groups.values():
        for group in local:
            for aid in group:
                partners[aid].update(set(group) - {aid})
    for loc in work.keys() | reserve.keys():
        if reservation_slots(instance, groups.get(loc, []), reserve[loc], partners, instance.supply[loc].supply_capacity) is None:
            return None
    return groups


def pack(instance, members):
    buckets = {t: sorted(a for a in members if instance.contracts[instance.activities[a].contract_number].access_type == t) for t in ("PM", "PC", "C")}
    groups = [[a] for a in buckets["PM"]]
    workers = buckets["C"]
    for pc in buckets["PC"]:
        groups.append([pc, *workers[:3]]); workers = workers[3:]
    groups.extend(workers[i:i + 4] for i in range(0, len(workers), 4))
    return groups
