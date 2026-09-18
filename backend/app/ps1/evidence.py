from collections import defaultdict
from dataclasses import asdict
from app.ps1.topology import protection_details
from app.ps1.scoring import week_end, delay_coefficient


def activity_details(instance, solution):
    groups = defaultdict(set)
    for row in solution.occupancy: groups[row.location_id, row.week, row.co_share_group].add(row.activity_id)
    nights = {(r["activity_id"], r["week"]): r["physical_night"] for r in solution.validation.detail.get("physical_night_assignment", [])}
    output = []
    for aid, activity in instance.activities.items():
        rows = [r for r in solution.accesses if r.activity_id == aid]
        contract = instance.contracts[activity.contract_number]
        end = week_end(instance, max(r.week for r in rows))
        peers = sorted({peer for row in solution.occupancy if row.activity_id == aid
                        for peer in groups[row.location_id, row.week, row.co_share_group] if peer != aid})
        predecessor_rows = [r for r in solution.accesses if r.activity_id == activity.predecessor_activity_id]
        output.append({"activity_id": aid, "contract_number": activity.contract_number,
                       "line": instance.supply[activity.start_location_id].line_code,
                       "access_type": contract.access_type, "required_workload": activity.total_accesses,
                       "delivered_workload": sum(2 + r.eclo for r in rows) / 2,
                       "planned_start_date": str(activity.planned_start_date), "planned_completion_date": str(contract.planned_completion_date),
                       "completion_date": str(end), "overrun_days": max(0, (end - contract.planned_completion_date).days),
                       "delay_cost": max(0, (end - contract.planned_completion_date).days) * delay_coefficient(contract, activity) / 10,
                       "predecessor": activity.predecessor_activity_id,
                       "predecessor_finish_week": max((r.week for r in predecessor_rows), default=None),
                       "accesses": [{**asdict(r), "physical_night": nights.get((aid, r.week))} for r in rows], "co_workers": peers,
                       "protection": protection_details(instance, activity),
                       "possessions": [asdict(r) for r in solution.occupancy if r.activity_id == aid],
                       "evidence_note": "Observed assignments and constraints; no counterfactual cause of delay is inferred."})
    return output
