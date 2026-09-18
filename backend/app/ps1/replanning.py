from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict

from app.ps1.safety import possession_usage


def audit_disruption(instance, solution, disruption):
    usage = possession_usage(instance, solution.accesses, solution.occupancy)
    rows = [item for item in usage if item["location_id"] == disruption.location_id
            and disruption.start_week <= item["week"] <= disruption.end_week]
    violations = [item for item in rows if item["work_possessions"] > disruption.capacity]
    return {
        "feasible": not violations,
        "hard_violations": [{"rule": "disruption_capacity", "severity": "hard",
                             "detail": f'{item["location_id"]} week {item["week"]}: '
                                       f'{item["work_possessions"]} exceeds emergency cap {disruption.capacity}.'}
                            for item in violations],
        "checked_location_weeks": disruption.end_week - disruption.start_week + 1,
        "observed_usage": rows,
    }


def solution_diff(instance, baseline, revised, disruption):
    before = defaultdict(list); after = defaultdict(list)
    for row in baseline.accesses: before[row.activity_id].append((row.week, row.eclo, row.access_night))
    for row in revised.accesses: after[row.activity_id].append((row.week, row.eclo, row.access_night))
    direct = {row.activity_id for row in baseline.occupancy
              if row.location_id == disruption.location_id
              and disruption.start_week <= row.week <= disruption.end_week}
    descendants = set(direct)
    changed = True
    while changed:
        changed = False
        for aid, activity in instance.activities.items():
            if activity.predecessor_activity_id in descendants and aid not in descendants:
                descendants.add(aid); changed = True
    activity_changes = []
    unchanged = 0
    for aid in sorted(instance.activities):
        old = sorted(before[aid]); new = sorted(after[aid])
        if old == new:
            unchanged += 1; continue
        category = "direct_disruption" if aid in direct else "predecessor_impact" if aid in descendants else "optimizer_rebalance"
        activity_changes.append({"activity_id": aid, "contract_number": instance.activities[aid].contract_number,
                                 "before": [{"week": w, "eclo": e, "access_night": n} for w, e, n in old],
                                 "after": [{"week": w, "eclo": e, "access_night": n} for w, e, n in new],
                                 "reason": category})
    old_results = {r.contract_number: r for r in baseline.results}; new_results = {r.contract_number: r for r in revised.results}
    contract_changes = [{"contract_number": cid,
                         "before_completion": str(old_results[cid].simulated_completion_date),
                         "after_completion": str(new_results[cid].simulated_completion_date),
                         "before_overrun": old_results[cid].overrun_days, "after_overrun": new_results[cid].overrun_days,
                         "overrun_delta": new_results[cid].overrun_days - old_results[cid].overrun_days}
                        for cid in sorted(old_results)
                        if old_results[cid].simulated_completion_date != new_results[cid].simulated_completion_date]
    old_score = baseline.validation.soft_scores["objective_score"]
    new_score = revised.validation.soft_scores["objective_score"]
    return {"summary": {"moved_activities": len(activity_changes),
                         "preserved_percent": round(100 * unchanged / max(1, len(instance.activities)), 1),
                         "contracts_impacted": len(contract_changes), "score_delta": new_score - old_score,
                         "baseline_score": old_score, "revised_score": new_score},
            "activity_changes": activity_changes, "contract_changes": contract_changes,
            "directly_affected_activities": sorted(direct)}
