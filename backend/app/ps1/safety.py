"""Work supply accounting and independent cross-contract physical-night validation."""
from itertools import combinations
from collections import defaultdict
from app.ps1.topology import activity_locations, closure_locations


def legal_mix(instance, members):
    kinds = [instance.contracts[instance.activities[a].contract_number].access_type for a in members]
    return len(kinds) <= 4 and kinds.count("PC") <= 1 and ("PM" not in kinds or len(kinds) == 1)


def possession_usage(instance, accesses, occupancy):
    work = {a: set(activity_locations(instance, item)) for a, item in instance.activities.items()}
    protection = {a: closure_locations(instance, item) for a, item in instance.activities.items()}
    weeks = defaultdict(set)
    groups = defaultdict(lambda: defaultdict(set))
    for r in accesses:
        if r.activity_id in work: weeks[r.week].add(r.activity_id)
    for r in occupancy:
        if r.activity_id in work and r.location_id in instance.supply:
            groups[(r.location_id, r.week)][r.co_share_group].add(r.activity_id)
    # Protection footprints are evidence, never additional supply consumption.
    reservations = defaultdict(list)
    for week, ids in weeks.items():
        for aid in sorted(ids):
            for loc in protection[aid]: reservations[loc, week].append([aid])
    output = []
    for loc, week in sorted(set(groups) | set(reservations)):
        g = groups[(loc, week)]; protected = reservations[(loc, week)]
        output.append({"location_id": loc, "week": week, "used": len(g),
                       "work_possessions": len(g), "protection_possessions": len(protected),
                       "capacity": instance.supply[loc].supply_capacity,
                       "activities": sorted(set.union(set(), *(set(v) for v in g.values()), *(set(v) for v in protected))),
                       "groups": {k: sorted(v) for k, v in g.items()}, "protection_groups": protected})
    return output



def _color_nights(graph, deadline):
    """Independent exact DSATUR search, with symmetry breaking and a hard budget.

    None means proved impossible; TimeoutError never means infeasible.
    """
    import time
    colors = {}
    def visit():
        if time.monotonic() >= deadline: raise TimeoutError
        if len(colors) == len(graph): return True
        node = max((n for n in graph if n not in colors),
                   key=lambda n: (len({colors[v] for v in graph[n] if v in colors}), len(graph[n]), n))
        banned = {colors[v] for v in graph[node] if v in colors}
        for color in range(1, min(7, max(colors.values(), default=0) + 1) + 1):
            if color in banned: continue
            colors[node] = color
            if visit(): return True
            del colors[node]
        return False
    if visit(): return colors
    return None


def safety_assignment(instance, accesses, occupancy, time_limit_seconds=2.0):
    """Rebuild equalities/conflicts from CSV, without consulting solver state.

    Seven anonymous nights per week; this proves existence, not availability on
    particular maintenance dates, which the supplied input does not specify.
    """
    import time
    deadline = time.monotonic() + time_limit_seconds
    work = {a: set(activity_locations(instance, item)) for a, item in instance.activities.items()}
    protected = {a: closure_locations(instance, item) for a, item in instance.activities.items()}
    labels = {(r.activity_id, r.week, r.location_id): r.co_share_group for r in occupancy}
    weeks = defaultdict(dict)
    for row in accesses:
        if row.activity_id in work and 1 <= row.week <= instance.horizon_weeks:
            weeks[row.week][row.activity_id] = row
    violations, witness = [], []
    for week, rows in sorted(weeks.items()):
        parents = {a: a for a in rows}
        def find(a):
            while parents[a] != a:
                parents[a] = parents[parents[a]]
                a = parents[a]
            return a
        def union(a, b):
            a, b = find(a), find(b)
            if a != b: parents[max(a,b)] = min(a,b)
        different = []
        for left, right in combinations(sorted(rows), 2):
            if time.monotonic() >= deadline:
                return [{"rule": "safety_unknown", "detail": "Physical-night validation budget exhausted; no feasibility conclusion."}], []
            a, b = instance.activities[left], instance.activities[right]
            if (a.contract_number, a.activity_type) == (b.contract_number, b.activity_type):
                if rows[left].access_night == rows[right].access_night: union(left, right)
                else: different.append((left, right, "distinct local access nights"))
            common = work[left] & work[right]
            shared = {loc for loc in common if labels.get((left, week, loc)) is not None
                      and labels.get((left, week, loc)) == labels.get((right, week, loc))}
            if shared: union(left, right)
            if common - shared:
                different.append((left, right, f"different possessions at {sorted(common - shared)}"))
            hits = ((protected[left] & (work[right] | protected[right]))
                    | (protected[right] & work[left]))
            if hits and not (shared and legal_mix(instance, [left, right])):
                different.append((left, right, f"overlapping work/protection at {sorted(hits)}"))
        graph = {find(a): set() for a in rows}
        week_bad = False
        for left, right, reason in different:
            lroot, rroot = find(left), find(right)
            if lroot == rroot:
                week_bad = True
                violations.append({"rule": "closure", "detail": f"Week {week}: {left}/{right} forced onto the same physical night by local access/sharing, but require different nights: {reason}."})
            else:
                graph[lroot].add(rroot); graph[rroot].add(lroot)
        if week_bad: continue
        try:
            # Components are independent; avoid recursion depth scaling with the
            # total number of unrelated activities in hidden inputs.
            remaining = set(graph); colors = {}
            while remaining:
                seed = min(remaining); component = {seed}; queue = [seed]
                while queue:
                    for neighbor in graph[queue.pop()]:
                        if neighbor not in component: component.add(neighbor); queue.append(neighbor)
                remaining -= component
                result = _color_nights({n: graph[n] for n in component}, deadline)
                if result is None:
                    violations.append({"rule": "closure", "detail": f"Week {week}: no assignment within seven physical nights for activities {sorted(a for a in rows if find(a) in component)}."})
                    week_bad = True
                    break
                colors.update(result)
        except (TimeoutError, RecursionError):
            violations.append({"rule": "safety_unknown", "detail": f"Week {week}: physical-night search budget exhausted; no feasibility conclusion."})
            continue
        if not week_bad:
            # Independently check the returned graph-color witness before export.
            if any(colors[a] == colors[b] for a in graph for b in graph[a]):
                raise RuntimeError("Invalid physical-night witness")
            witness.extend({"activity_id": a, "week": week, "physical_night": colors[find(a)]} for a in sorted(rows))
    return violations, [] if violations else witness
