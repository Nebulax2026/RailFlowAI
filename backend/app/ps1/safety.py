"""Local protection reservations; labels never denote network-wide nights.

Sharing protection requires a legal clique with a common work location and
agreement at every overlapping work location. Other footprints reserve separate
slots. This conservative interpretation is versioned and tested against the pack.
"""
from collections import defaultdict
from app.ps1.topology import activity_locations, closure_locations


def legal_mix(instance, members):
    kinds = [instance.contracts[instance.activities[a].contract_number].access_type for a in members]
    return len(kinds) <= 4 and kinds.count("PC") <= 1 and ("PM" not in kinds or len(kinds) == 1)


def possession_usage(instance, accesses, occupancy):
    work = {a: set(activity_locations(instance, item)) for a, item in instance.activities.items()}
    protection = {a: closure_locations(instance, item) for a, item in instance.activities.items()}
    labels = {(r.activity_id, r.week, r.location_id): r.co_share_group for r in occupancy}
    weeks = defaultdict(set)
    groups = defaultdict(lambda: defaultdict(set))
    for r in accesses:
        if r.activity_id in work: weeks[r.week].add(r.activity_id)
    for r in occupancy:
        if r.activity_id in work and r.location_id in instance.supply:
            groups[(r.location_id, r.week)][r.co_share_group].add(r.activity_id)
    reservations = defaultdict(list)
    for week, ids in weeks.items():
        cohorts = []
        for aid in sorted(ids):
            for cohort in cohorts:
                if not legal_mix(instance, [*cohort, aid]): continue
                if not set.intersection(*(work[a] for a in [*cohort, aid])): continue
                if all(all(labels.get((aid, week, loc)) is not None and labels.get((aid, week, loc)) == labels.get((other, week, loc))
                           for loc in work[aid] & work[other]) for other in cohort):
                    cohort.append(aid)
                    break
            else: cohorts.append([aid])
        for cohort in cohorts:
            protected = set.union(*(protection[a] for a in cohort)) - set.union(*(work[a] for a in cohort))
            for loc in protected: reservations[(loc, week)].append(cohort)
    output = []
    for loc, week in sorted(set(groups) | set(reservations)):
        g = groups[(loc, week)]; protected = reservations[(loc, week)]
        output.append({"location_id": loc, "week": week, "used": len(g) + len(protected),
                       "work_possessions": len(g), "protection_possessions": len(protected),
                       "capacity": instance.supply[loc].supply_capacity,
                       "activities": sorted(set.union(set(), *(set(v) for v in g.values()), *(set(v) for v in protected))),
                       "groups": {k: sorted(v) for k, v in g.items()}, "protection_groups": protected})
    return output
