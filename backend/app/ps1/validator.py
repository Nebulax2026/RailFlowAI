from __future__ import annotations
import csv
import io
from collections import Counter, defaultdict
from datetime import date
from app.ps1.models import AccessAssignment, ContractResult, OccupancyAssignment, Scenario, ValidationReport
from app.ps1.topology import activity_locations, affected_lines
from app.ps1.safety import POLICY_VERSION, legal_mix, possession_usage, safety_assignment, weekly_closure_errors
from app.ps1.scoring import FORMULA_VERSION, contract_delay_coefficient, week_end

OUTPUT_HEADERS = {
    "SCHEDULE_ACCESS.csv": ("activity_id", "access_seq", "week", "eclo", "access_night"),
    "SCHEDULE_OCCUPANCY.csv": ("activity_id", "week", "location_id", "co_share_group"),
    "RESULTS.csv": ("scenario", "contract_number", "simulated_completion_date", "overrun_days"),
}


def validate_exported_csvs(instance, scenario, files):
    try:
        tables = {}
        if set(files) != set(OUTPUT_HEADERS): raise ValueError("Expected exactly three official CSV files.")
        for name, headers in OUTPUT_HEADERS.items():
            reader = csv.DictReader(io.StringIO(files[name].decode("utf-8-sig")), strict=True)
            if tuple(reader.fieldnames or ()) != headers: raise ValueError(f"Invalid headers in {name}.")
            tables[name] = list(reader)
            for number, row in enumerate(tables[name], 2):
                if None in row or any(v is None or not v.strip() for v in row.values()):
                    raise ValueError(f"{name} row {number}: missing value or wrong field count.")
        accesses = [AccessAssignment(r['activity_id'], int(r['access_seq']), int(r['week']), int(r['eclo']), int(r['access_night'])) for r in tables['SCHEDULE_ACCESS.csv']]
        occupancy = [OccupancyAssignment(r['activity_id'], int(r['week']), r['location_id'], r['co_share_group']) for r in tables['SCHEDULE_OCCUPANCY.csv']]
        results = [ContractResult(r['scenario'], r['contract_number'], date.fromisoformat(r['simulated_completion_date']), int(r['overrun_days'])) for r in tables['RESULTS.csv']]
    except (UnicodeError, csv.Error, ValueError, TypeError, KeyError) as error:
        return ValidationReport(scenario.value, False, [{"rule": "schema", "severity": "hard", "detail": str(error)}], {}, {})
    return validate_solution(instance, scenario, accesses, occupancy, results)


def validate_solution(instance, scenario, accesses, occupancy, results):
    violations = []
    def fail(rule, detail): violations.append({"rule": rule, "severity": "hard", "detail": detail})
    by_activity = defaultdict(list); nights = defaultdict(set); fronts = defaultdict(set)
    for row in accesses:
        if row.activity_id not in instance.activities:
            fail("activity", f"Unknown activity {row.activity_id}."); continue
        activity = instance.activities[row.activity_id]; contract = instance.contracts[activity.contract_number]
        if not 1 <= row.week <= instance.horizon_weeks:
            fail("horizon", f"{row.activity_id}: week {row.week}."); continue
        by_activity[row.activity_id].append(row)
        if row.eclo not in (0, 1): fail("eclo", f"{row.activity_id}: eclo must be 0 or 1.")
        if scenario == Scenario.A and row.eclo: fail("eclo", f"{row.activity_id}: A forbids ECLO.")
        if not 1 <= row.access_night <= contract.number_of_maximum_access_per_week: fail("weekly_allocation", f"{row.activity_id}: night {row.access_night}.")
        key = (activity.contract_number, activity.activity_type, row.week)
        nights[key].add(row.access_night); fronts[(*key, row.access_night)].add(row.activity_id)
    completion = {}; delivered = 0
    for aid, activity in instance.activities.items():
        rows = by_activity[aid]; units = sum(2 + r.eclo for r in rows if r.eclo in (0, 1))
        delivered += min(units, 2 * activity.total_accesses)
        if units < 2 * activity.total_accesses: fail("workload", f"{aid}: delivered {units / 2} of {activity.total_accesses}.")
        if sorted(r.access_seq for r in rows) != list(range(1, len(rows) + 1)): fail("access_seq", f"{aid}: access_seq must be positive, unique and contiguous.")
        if len({r.week for r in rows}) != len(rows): fail("weekly_activity", f"{aid}: duplicate activity/week.")
        if [r.week for r in sorted(rows, key=lambda r: r.access_seq)] != sorted(r.week for r in rows): fail("access_seq", f"{aid}: access_seq is not chronological.")
        earliest = max(1, (activity.planned_start_date - instance.horizon_start).days // 7 + 1)
        if rows and min(r.week for r in rows) < earliest: fail("planned_start", f"{aid}: starts before week {earliest}.")
        predecessor = by_activity.get(activity.predecessor_activity_id, [])
        if rows and predecessor and max(r.week for r in predecessor) >= min(r.week for r in rows): fail("predecessor", f"{aid}: predecessor {activity.predecessor_activity_id} has not finished.")
        if rows:
            end = week_end(instance, max(r.week for r in rows)); contract = instance.contracts[activity.contract_number]
            completion[activity.contract_number] = max(end, completion.get(activity.contract_number, end))
    for key, members in fronts.items():
        if len(members) > instance.contracts[key[0]].number_of_workfronts: fail("workfront", f"{key}: {sorted(members)} exceed workfronts.")
    for key, values in nights.items():
        if len(values) > instance.contracts[key[0]].number_of_maximum_access_per_week: fail("weekly_allocation", f"{key}: too many nights.")
    expected = {(r.activity_id, r.week, loc) for aid, rows in by_activity.items() if aid in instance.activities for r in rows for loc in activity_locations(instance, instance.activities[aid])}
    actual = Counter((r.activity_id, r.week, r.location_id) for r in occupancy)
    for key, count in actual.items():
        if count != 1: fail("occupancy", f"Duplicate occupancy {key}.")
    for key in sorted(expected - actual.keys()): fail("occupancy", f"Missing occupancy {key}.")
    for key in sorted(actual.keys() - expected): fail("occupancy", f"Unexpected occupancy {key}.")
    groups = defaultdict(set)
    for row in occupancy:
        if not row.co_share_group.strip(): fail("occupancy", f"{row.activity_id}: empty group.")
        if row.activity_id in instance.activities: groups[(row.location_id, row.week, row.co_share_group)].add(row.activity_id)
    for key, members in groups.items():
        if not legal_mix(instance, members): fail("legal_mix", f"{key}: illegal group {sorted(members)}.")
    usage = possession_usage(instance, accesses, occupancy); excess = 0
    for item in usage:
        work_over = max(0, item['work_possessions'] - item['capacity'])
        excess += work_over
        allowance = 1 if scenario == Scenario.C else 0
        if scenario != Scenario.B and work_over > allowance:
            fail("capacity", f"{item['location_id']} week {item['week']}: {item['work_possessions']} work possessions exceed supply {item['capacity']} and allowance {allowance}.")
    safety_errors, night_witness = safety_assignment(instance, accesses, occupancy)
    safety_errors = weekly_closure_errors(instance, accesses, occupancy) + safety_errors
    if safety_errors:
        night_witness = []
    for item in safety_errors: fail(item['rule'], item['detail'])
    eclo_weeks = defaultdict(list)
    for aid, rows in by_activity.items():
        if aid not in instance.activities: continue
        for row in rows:
            if row.eclo == 1:
                for line in affected_lines(instance, instance.activities[aid]): eclo_weeks[line].append(row.week)
    if scenario == Scenario.C:
        for line, weeks in eclo_weeks.items():
            if max(weeks) - min(weeks) > 1: fail("eclo_continuity", f"{line}: ECLO spans weeks {min(weeks)}–{max(weeks)}.")
    result_counts = Counter(r.contract_number for r in results)
    for row in results:
        if row.scenario != scenario.value: fail("scenario", f"Wrong scenario {row.scenario}.")
        if row.contract_number not in instance.contracts: fail("results", f"Unknown contract {row.contract_number}."); continue
        end = completion.get(row.contract_number); contract = instance.contracts[row.contract_number]
        if end != row.simulated_completion_date or (end and row.overrun_days != max(0, (end - contract.planned_completion_date).days)):
            fail("results", f"{row.contract_number}: completion/overrun differs from actual access schedule.")
    overruns = {}; priority = {str(p): 0 for p in (1, 2, 3)}
    for cid, contract in instance.contracts.items():
        if result_counts[cid] != 1: fail("results", f"{cid}: expected exactly one result.")
        if cid in completion:
            overruns[cid] = max(0, (completion[cid] - contract.planned_completion_date).days)
            priority[str(contract.contract_priority)] += overruns[cid]
            if scenario == Scenario.B and overruns[cid]: fail("planned_date", f"{cid}: actual completion overruns by {overruns[cid]} days.")
    weighted_tenths = sum(contract_delay_coefficient(instance, cid) * days
                          for cid, days in overruns.items())
    eclo = sum(r.eclo == 1 for r in accesses)
    breakdown = {"delay": 0 if scenario == Scenario.B else weighted_tenths / 10, "excess_supply": 0 if scenario == Scenario.A else 7 * excess, "eclo": 0 if scenario == Scenario.A else 5 * eclo}
    scores = {"overrun_days_total": sum(overruns.values()), "contracts_overrunning": sum(v > 0 for v in overruns.values()),
              "earliness_days_total": sum(max(0, (instance.contracts[c].planned_completion_date - d).days) for c, d in completion.items()),
              "excess_access_nights_total": excess, "eclo_nights_total": eclo, "priority_overrun": priority, "priority_weighted_score": weighted_tenths / 10,
              "completion_percent": round(100 * delivered / max(1, 2 * sum(a.total_accesses for a in instance.activities.values())), 2)}
    if not violations: scores.update(objective_score=sum(breakdown.values()), formula_version=FORMULA_VERSION)
    return ValidationReport(scenario.value, not violations, violations, scores,
                            {"capacity_hotspots": [u for u in usage if u['used'] >= u['capacity']], "location_usage": usage,
                             "nights_scheduled": len(accesses), "eclo_nights": eclo, "score_breakdown": breakdown, "safety_policy": POLICY_VERSION,
                             "safety_coverage": "Weekly closure compatibility inferred from official rejection evidence, plus a reconstructed cross-contract seven-night assignment. Official parity and dated maintenance availability are unconfirmed.",
                             "official_validator_available": False,
                             "unresolved_safety_pairs": [], "physical_night_assignment": night_witness,
                             "safety_status": "unknown" if any(e["rule"] == "safety_unknown" for e in safety_errors) else "failed" if safety_errors else "verified"})
