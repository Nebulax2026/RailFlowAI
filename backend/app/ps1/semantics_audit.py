"""Diagnostic only: test a proposed global-night interpretation of local groups.

This is not an official validation rule. If an activity occupies its whole span
on one night, same groups imply equal nights and different groups at one site
imply different nights. A pair cannot satisfy both implications simultaneously.
No topology, supply, solver state or global interpretation of label names is used.
"""
from collections import defaultdict
from itertools import combinations


def direct_night_contradictions(occupancy):
    sites = defaultdict(list)
    for row_number, row in enumerate(occupancy, 2):
        sites[row.week, row.location_id].append((row_number, row))
    pairs = defaultdict(dict)
    for (week, location), rows in sorted(sites.items()):
        for (ln, left), (rn, right) in combinations(rows, 2):
            if left.activity_id == right.activity_id:
                continue
            pair = tuple(sorted((left.activity_id, right.activity_id)))
            relation = "same_night" if left.co_share_group == right.co_share_group else "different_nights"
            pairs[week, pair].setdefault(relation, {
                "location_id": location,
                "csv_rows": [ln, rn],
                "members": [
                    {"activity_id": left.activity_id, "group": left.co_share_group},
                    {"activity_id": right.activity_id, "group": right.co_share_group},
                ],
            })
    return [
        {"week": week, "activities": list(pair), **evidence}
        for (week, pair), evidence in sorted(pairs.items())
        if len(evidence) == 2
    ]
