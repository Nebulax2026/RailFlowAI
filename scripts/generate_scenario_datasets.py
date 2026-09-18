"""Generate 30 common PS1 inputs, each witnessed feasible for A, B and C."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ps1.exporter import scenario_csvs, validation_summary
from app.ps1.models import AccessAssignment, ContractResult, OccupancyAssignment, Scenario, ScenarioSolution
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.validation import independent_footprints, validate_csvs
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import OUTPUT_HEADERS, validate_exported_csvs

PROFILES = [
    dict(name="small", activities=18, horizon=20, span=1, group=2, live=.10, links=.10, cluster=False, slack=1, due=0, contracts=10),
    dict(name="mixed", activities=36, horizon=30, span=2, group=3, live=.15, links=.20, cluster=False, slack=0, due=7, contracts=14),
    dict(name="priority_pressure", activities=54, horizon=30, span=2, group=4, live=.15, links=.20, cluster=False, slack=0, due=21, contracts=16),
    dict(name="interchange_congestion", activities=60, horizon=30, span=2, group=4, live=.20, links=.15, cluster=True, slack=0, due=14, contracts=16),
    dict(name="long_spans", activities=48, horizon=30, span=4, group=3, live=.15, links=.20, cluster=False, slack=0, due=10, contracts=14),
    dict(name="live_closures", activities=54, horizon=30, span=2, group=3, live=.50, links=.20, cluster=True, slack=0, due=14, contracts=16),
    dict(name="precedence_chains", activities=60, horizon=36, span=2, group=3, live=.15, links=.80, cluster=False, slack=0, due=14, contracts=14),
    dict(name="contract_contention", activities=72, horizon=30, span=2, group=4, live=.10, links=.20, cluster=False, slack=0, due=7, contracts=7),
    dict(name="compressed_horizon", activities=72, horizon=16, span=2, group=4, live=.20, links=.35, cluster=True, slack=0, due=14, contracts=14),
    dict(name="large_mixed", activities=108, horizon=40, span=3, group=4, live=.25, links=.45, cluster=False, slack=0, due=21, contracts=22),
]


def encode(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def table(content):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def generate(source, scenario, index, seed):
    profile = PROFILES[index]
    rng = random.Random(seed)
    files = dict(source)
    start = date(2027, 1, 4) + timedelta(weeks=index * 4)
    horizon = profile["horizon"]
    files["06_PARAMETERS.csv"] = encode(EXPECTED_FILES["06_PARAMETERS.csv"], [
        {"key": "horizon_start", "value": str(start)}, {"key": "horizon_weeks", "value": horizon}])
    sectors = defaultdict(list)
    for row in table(files["03_SECTORS.csv"]): sectors[row["line_code"]].append(row)
    for values in sectors.values(): values.sort(key=lambda r: int(r["seq"]))
    lines = sorted(sectors)
    # A known C witness respects a single two-week ECLO window per line.
    window_start = max(2, horizon // 2)
    windows = {line: {window_start + offset, window_start + offset + 1} for offset, line in enumerate(lines)}
    contracts, activities, placements, cohorts = [], [], {}, []
    cohort_weeks = Counter()
    contract_pools = defaultdict(list)

    def contract_for(kind, nature):
        activity_type = "Renewal" if nature != "Non-live (Others)" else "Construction"
        key = kind, nature, activity_type
        pool = contract_pools[key]
        if not pool or (len(contracts) < profile["contracts"] and rng.random() < .45):
            cid = f"C{len(contracts)+1:03d}"
            row = dict(contract_number=cid, contract_description=f"Synthetic {profile['name']} programme {cid}",
                       contract_award_date=str(start-timedelta(days=rng.randint(60, 240))),
                       activity_type=activity_type, nature_of_activity=nature,
                       contract_priority=rng.choices([1, 2, 3], [3, 3, 4])[0],
                       contract_completion_date=str(start+timedelta(weeks=horizon+4)),
                       planned_completion_date=str(start+timedelta(weeks=horizon)-timedelta(days=1)),
                       number_of_workfronts=1, access_type=kind,
                       number_of_maximum_access_per_week=2 if nature == "Live" else 3)
            contracts.append(row); pool.append(row)
            return row
        return rng.choice(pool)

    while len(activities) < profile["activities"]:
        count = min(rng.randint(1, profile["group"]), profile["activities"]-len(activities))
        if rng.random() < .12: kinds = ["PM"]
        else: kinds = ["PC" if rng.random() < .55 else "C"] + ["C"] * (count-1)
        line = rng.choice(lines); bound = rng.choice(["EB", "WB"])
        route = sectors[line]
        anchor = next(i for i, r in enumerate(route) if r["from_station_id"] == "H01") if profile["cluster"] else rng.randrange(len(route))
        n = rng.randint(1, min(6, horizon // 3))
        # A cohort occupies one anonymous physical night. Keep at most seven
        # cohorts per week so the current cross-contract safety validator can
        # always color them without relying on accidental spatial separation.
        available = [w for w in range(1, horizon+1) if cohort_weeks[w] < 7]
        if len(available) < n:
            raise ValueError(f"{profile['name']}: insufficient physical nights for the witness")
        candidate_windows = [available[max(0, i-n+1):i+1] for i in range(n-1, len(available))]
        local = rng.choice(candidate_windows)
        weeks = sorted(local)
        for week in weeks: cohort_weeks[week] += 1
        group = f"g{len(cohorts)+1:03d}"
        members = []
        left = max(0, anchor-rng.randrange(profile["span"]))
        right = min(len(route)-1, anchor+rng.randrange(profile["span"]))
        for kind in kinds:
            if kind == "PM": nature = "Live"
            elif rng.random() < profile["live"]: nature = "Live"
            else: nature = rng.choice(["Non-live (Consist)", "Non-live (Others)"])
            contract = contract_for(kind, nature)
            aid = f"A{len(activities)+1:03d}"
            extra = []
            for w in weeks:
                affected = lines if nature == "Live" and any(r["from_station_id"] == "H01" for r in route[left:right+1]) else [line]
                allowed = scenario == Scenario.B or (scenario == Scenario.C and all(w in windows[l] for l in affected))
                extra.append(int(allowed and rng.random() < (.55 if scenario == Scenario.B else .8)))
            workload = (2*len(weeks)+sum(extra)) // 2
            release = max(1, weeks[0]-rng.randint(0, 3))
            predecessor = ""
            if rng.random() < profile["links"]:
                earlier = [a for a, schedule in placements.items() if max(w for w, _ in schedule) < weeks[0]]
                if earlier:
                    # Prefer the latest eligible predecessor to form longer paths.
                    predecessor = max(earlier, key=lambda a: (max(w for w, _ in placements[a]), a))
            activities.append(dict(activity_id=aid, contract_number=contract["contract_number"],
                                   activity_type=contract["activity_type"],
                                   start_location_id=route[left]["sector_id"]+":"+bound,
                                   end_location_id=route[right]["sector_id"]+":"+bound,
                                   total_accesses=workload, planned_start_date=str(start+timedelta(weeks=release-1)),
                                   predecessor_activity_id=predecessor, activity_priority=rng.randint(1, 3)))
            placements[aid] = list(zip(weeks, extra)); members.append(aid)
        cohorts.append((group, members))

    activity_map = {a["activity_id"]: a for a in activities}
    contract_groups = defaultdict(set)
    group_fronts = Counter()
    for group, members in cohorts:
        for week, _ in placements[members[0]]:
            for aid in members:
                contract = activity_map[aid]["contract_number"]
                contract_groups[contract, week].add(group)
                group_fronts[contract, week, group] += 1
    group_nights = {}
    for key, groups in contract_groups.items():
        for night, group in enumerate(sorted(groups), 1):
            group_nights[key[0], key[1], group] = night
    group_of = {aid: group for group, members in cohorts for aid in members}
    for c in contracts:
        aids = [a["activity_id"] for a in activities if a["contract_number"] == c["contract_number"]]
        last = max(w for a in aids for w, _ in placements[a])
        c["number_of_maximum_access_per_week"] = max(1, max((len(groups) for (cid, _), groups in contract_groups.items() if cid == c["contract_number"]), default=0))
        c["number_of_workfronts"] = max(1, max((count for (cid, _, _), count in group_fronts.items() if cid == c["contract_number"]), default=0))
        actual_finish = start+timedelta(days=last*7-1)
        # The common zero-ECLO witness must meet B's fixed completion date;
        # the same CSV input can then be evaluated independently under A/C.
        due = actual_finish+timedelta(days=rng.choice([0, 0, 2, 7]))
        c["planned_completion_date"] = str(due)
    files["07_PROJECT_DETAILS.csv"] = encode(EXPECTED_FILES["07_PROJECT_DETAILS.csv"], contracts)
    files["08_ACTIVITY_DETAILS.csv"] = encode(EXPECTED_FILES["08_ACTIVITY_DETAILS.csv"], activities)
    instance = parse_instance(files)
    work = {aid: set(activity_locations(instance, a)) for aid, a in instance.activities.items()}
    footprints = {aid: work[aid] | closure_locations(instance, a) for aid, a in instance.activities.items()}
    if scenario == Scenario.A:
        # Cover both current internal interpretations, including Live buffers
        # reaching the interchange in the independent A validator.
        for aid in instance.activities:
            actual, reserve = independent_footprints(instance, aid)
            footprints[aid].update(actual | reserve)
    occupancy, used = [], Counter()
    for group, members in cohorts:
        for week, _ in placements[members[0]]:
            for loc in set.union(*(footprints[a] for a in members)): used[loc, week] += 1
            for aid in members:
                occupancy.extend(OccupancyAssignment(aid, week, loc, group) for loc in sorted(work[aid]))
    supply = table(files["04_LOCATION_SUPPLY.csv"])
    for row in supply:
        peak = max((used[row["location_id"], w] for w in range(1, horizon+1)), default=0)
        if scenario == Scenario.A: capacity = max(1, peak+profile["slack"])
        elif scenario == Scenario.B: capacity = 1 + int(profile["slack"] or rng.random() < .20)
        else: capacity = max(1, peak-int(not profile["slack"] and rng.random() < .75))+profile["slack"]
        row["supply_capacity"] = capacity
    files["04_LOCATION_SUPPLY.csv"] = encode(EXPECTED_FILES["04_LOCATION_SUPPLY.csv"], supply)
    instance = parse_instance(files)
    accesses = []
    for aid, schedule in sorted(placements.items()):
        a = instance.activities[aid]; c = instance.contracts[a.contract_number]
        for seq, (week, eclo) in enumerate(schedule, 1):
            night = group_nights[c.contract_number, week, group_of[aid]]
            accesses.append(AccessAssignment(aid, seq, week, eclo, night))
    results = []
    for cid, c in instance.contracts.items():
        last = max(r.week for r in accesses if instance.activities[r.activity_id].contract_number == cid)
        end = start+timedelta(days=last*7-1)
        results.append(ContractResult(scenario.value, cid, end, max(0, (end-c.planned_completion_date).days)))
    witness = ScenarioSolution(scenario, accesses, occupancy, results, None)
    witness_files = scenario_csvs(witness)
    validation = validate_exported_csvs(instance, scenario, witness_files)
    if not validation.feasible: raise ValueError(f"{scenario}/{profile['name']}: {validation.hard_violations[:3]}")
    independent = validate_csvs(instance, witness_files) if scenario == Scenario.A else None
    if independent and not independent.feasible: raise ValueError(f"Independent A check: {independent.hard_violations[:3]}")
    metadata = dict(profile=profile, seed=seed,
                    split="development" if index < 5 else "evaluation",
                    generator="synthetic-common-witness-v3", feasibility="validated_witness_exists_for_A_B_C",
                    optimality="not_proved", official_validator_available=False,
                    activities=len(activities), contracts=len(contracts), horizon_weeks=horizon,
                    total_workload=sum(a.total_accesses for a in instance.activities.values()),
                    predecessor_links=sum(bool(a.predecessor_activity_id) for a in instance.activities.values()),
                    live_activities=sum(instance.contracts[a.contract_number].nature_of_activity == "Live" for a in instance.activities.values()),
                    access_type_counts=dict(Counter(instance.contracts[a.contract_number].access_type for a in instance.activities.values())),
                    supply_range=[min(s.supply_capacity for s in instance.supply.values()), max(s.supply_capacity for s in instance.supply.values())],
                    witness_eclo_A=validation.soft_scores["eclo_nights_total"],
                    witness_excess_A=validation.soft_scores["excess_access_nights_total"],
                    input_sha256={n: hashlib.sha256(v).hexdigest() for n, v in files.items()})
    reports = {"main": validation_summary(validation)}
    if independent: reports["independent_A"] = validation_summary(independent)
    return files, witness_files, metadata, reports


def archive(path, entries):
    # Stable ZIP timestamps keep the entire generated suite reproducible.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/scenario-suite-v1")
    parser.add_argument("--seed", type=int, default=20260918)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = {n: (ROOT / "PS1/01_data" / n).read_bytes() for n in EXPECTED_FILES}
    manifest, all_entries = [], {}
    for number in range(30):
        index = number % len(PROFILES)
        profile = PROFILES[index]
        seed = args.seed+number
        inputs, witness, metadata, _ = generate(source, Scenario.A, index, seed)
        case_id = f"D{number+1:02d}_{profile['name']}"
        directory = args.output / "cases" / case_id
        (directory / "input").mkdir(parents=True)
        for name, data in inputs.items():
            (directory / "input" / name).write_bytes(data)
            all_entries[f"{case_id}/{name}"] = data
        reread = parse_instance({n: (directory / "input" / n).read_bytes() for n in EXPECTED_FILES})
        scores = {}
        for scenario in Scenario:
            scenario_witness = dict(witness)
            results = table(witness["RESULTS.csv"])
            for row in results: row["scenario"] = scenario.value
            scenario_witness["RESULTS.csv"] = encode(OUTPUT_HEADERS["RESULTS.csv"], results)
            witness_dir = directory / "witness" / scenario.value
            witness_dir.mkdir(parents=True)
            for name, data in scenario_witness.items(): (witness_dir / name).write_bytes(data)
            csvs = {n: (witness_dir / n).read_bytes() for n in OUTPUT_HEADERS}
            report = validate_exported_csvs(reread, scenario, csvs)
            if not report.feasible: raise ValueError(f"{case_id}/{scenario.value}: {report.hard_violations[:3]}")
            scenario_reports = {"main": validation_summary(report)}
            if scenario == Scenario.A:
                independent = validate_csvs(reread, csvs)
                if not independent.feasible: raise ValueError(f"{case_id}/independent A: {independent.hard_violations[:3]}")
                scenario_reports["independent_A"] = validation_summary(independent)
            (witness_dir / "validation.json").write_text(json.dumps(scenario_reports, indent=2)+"\n")
            scores[scenario.value] = report.soft_scores["objective_score"]
        metadata.update(case_id=case_id, input_path=str(directory.relative_to(args.output) / "input"),
                        witness_scores=scores, scenarios=[s.value for s in Scenario],
                        split="development" if number < 15 else "evaluation")
        (directory / "metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
        manifest.append(metadata)
        print(f"{case_id}: {metadata['activities']} activities, A/B/C witnesses valid", flush=True)
    archive(args.output / "all_30_inputs.zip", all_entries)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    lines = ["# Synthetic common A/B/C dataset suite", "", "30 common datasets. Each input directory contains eight official-schema CSVs and is evaluated under A, B and C.",
             "Each witness is a verified feasible example, not an optimal answer. Do not pass witnesses as hints when measuring a solver.",
             "Every input has A, B and C feasible witnesses under readme-physical-night-v3. A witnesses pass both current internal validators; B/C witnesses pass main's validator. Official validator unavailable.",
             "All datasets are synthetic, built on the bundled network; these are not organizer hidden datasets or a guarantee of hidden-set performance.",
             "", "## Use", "", "Unzip all_30_inputs.zip. Upload the eight CSVs from one case to the frontend, which runs A, B and C on that same input.",
             "For isolated evaluation, use the CLI with --scenario A, B or C and --input pointing at that case's input folder.",
             "Cases 01–15 are designated development; 16–30 evaluation. This is a provisional split, not a statistically independent hidden evaluation.",
             "Supply and workfront limits were derived from generated witness demand. This construction bias is intentional to certify feasibility, not evidence of realistic difficulty.",
             "", "## Contents", "", "| Case | Split | Activities | Contracts | Weeks | Links | Live | A/B/C witness cost |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in manifest:
        lines.append(f"| {row['case_id']} | {row['split']} | {row['activities']} | {row['contracts']} | {row['horizon_weeks']} | {row['predecessor_links']} | {row['live_activities']} | {row['witness_scores']['A']}/{row['witness_scores']['B']}/{row['witness_scores']['C']} |")
    lines += ["", "## Reproduce", "", "```sh", f"backend/.venv/bin/python scripts/generate_scenario_datasets.py --output datasets/scenario-suite-reproduction --seed {args.seed}", "```", ""]
    (args.output / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
