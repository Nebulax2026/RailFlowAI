"""Serial benchmark; run with backend/.venv/bin/python from the repo root."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.validation import HEADERS, validate_csvs


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def cases(output, witness):
    source = {n: (ROOT / "PS1/01_data" / n).read_bytes() for n in EXPECTED_FILES}
    witness_files = {n: (witness / n).read_bytes() for n in HEADERS}
    assert validate_csvs(parse_instance(source), witness_files).feasible
    accesses = list(csv.DictReader(io.StringIO(witness_files["SCHEDULE_ACCESS.csv"].decode())))
    first = {a: min(int(r["week"]) for r in accesses if r["activity_id"] == a) for a in {r["activity_id"] for r in accesses}}
    paths = {}
    for name in ("public", "heldout_dates", "heldout_release", "infeasible"):
        files = dict(source)
        projects = list(csv.DictReader(io.StringIO(files["07_PROJECT_DETAILS.csv"].decode())))
        activities = list(csv.DictReader(io.StringIO(files["08_ACTIVITY_DETAILS.csv"].decode())))
        if name == "heldout_dates":
            for row in projects:
                row["planned_completion_date"] = (date.fromisoformat(row["planned_completion_date"]) - timedelta(days=10)).isoformat()
                row["contract_priority"] = str(int(row["contract_priority"]) % 3 + 1)
            for row in activities:
                row["activity_priority"] = str(int(row["activity_priority"]) % 3 + 1)
        if name == "heldout_release":
            for row in activities:
                earliest = date(2027, 1, 4) + timedelta(weeks=max(0, first[row["activity_id"]] - 2))
                row["planned_start_date"] = max(earliest, date.fromisoformat(row["planned_start_date"])).isoformat()
        if name == "infeasible":
            activities[0]["total_accesses"] = "31"  # One access/week, only 30 weeks.
        files["07_PROJECT_DETAILS.csv"] = csv_bytes(projects)
        files["08_ACTIVITY_DETAILS.csv"] = csv_bytes(activities)
        if name != "infeasible":
            assert validate_csvs(parse_instance(files), witness_files if name == "public" else adjusted_results(witness_files, files)).feasible
        path = output / "instances" / name
        path.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (path / filename).write_bytes(content)
        (path / "provenance.json").write_text(json.dumps({"split": "tuning" if name == "public" else "evaluation",
            "feasibility": "proven impossible by workload/horizon" if name == "infeasible" else "known feasible witness; never supplied as a solver hint",
            "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}, indent=2))
        paths[name] = path
    return paths


def adjusted_results(witness, inputs):
    files = dict(witness)
    contracts = {r["contract_number"]: r for r in csv.DictReader(io.StringIO(inputs["07_PROJECT_DETAILS.csv"].decode()))}
    rows = list(csv.DictReader(io.StringIO(files["RESULTS.csv"].decode())))
    for row in rows:
        row["overrun_days"] = str(max(0, (date.fromisoformat(row["simulated_completion_date"]) - date.fromisoformat(contracts[row["contract_number"]]["planned_completion_date"])).days))
    files["RESULTS.csv"] = csv_bytes(rows)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--seeds", default="11,29")
    parser.add_argument("--budgets", default="5,15")
    parser.add_argument("--cases", default="public,heldout_dates,heldout_release,infeasible")
    parser.add_argument("--strategies", default="integrated,random_lns,alns")
    parser.add_argument("--initialization", default="direct", choices=("direct", "feasibility"))
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    inputs = cases(output, args.witness.resolve())
    runs = []
    raw = output / "raw-results.jsonl"
    if raw.exists():
        raise SystemExit("Use a new output directory to avoid mixing benchmark runs.")
    for name in args.cases.split(","):
        instance = parse_instance({n: (inputs[name] / n).read_bytes() for n in EXPECTED_FILES})
        for budget in map(float, args.budgets.split(",")):
            for seed in map(int, args.seeds.split(",")):
                for strategy in args.strategies.split(","):
                    directory = output / "runs" / f"{name}-{budget:g}s-{seed}-{strategy}"
                    started = time.monotonic()
                    process = subprocess.run([sys.executable, "-m", "app.ps1.scenario_a.cli", "--input", str(inputs[name]),
                        "--output", str(directory), "--strategy", strategy, "--seconds", str(budget), "--seed", str(seed), "--workers", "8", "--initialization", args.initialization],
                        cwd=ROOT / "backend", capture_output=True, text=True, timeout=budget + 15)
                    wall = time.monotonic() - started
                    diagnostics = json.loads((directory / "diagnostics.json").read_text())
                    feasible = all((directory / n).exists() for n in HEADERS)
                    if feasible:
                        validation = validate_csvs(instance, {n: (directory / n).read_bytes() for n in HEADERS})
                        feasible = validation.feasible
                    row = {"case": name, "split": "tuning" if name == "public" else "evaluation", "budget": budget, "seed": seed,
                           "strategy": strategy, "initialization": args.initialization, "feasible": feasible, "cost": validation.soft_scores["objective_score"] if feasible else None,
                           "wall_seconds": wall, "returncode": process.returncode, "diagnostics": diagnostics}
                    runs.append(row)
                    with raw.open("a") as f: f.write(json.dumps(row) + "\n")
                    print(f"{name:16} {budget:4g}s seed {seed:2} {strategy:12} {str(row['cost']):8} {diagnostics['status']}", flush=True)
                    summarize(output, runs)


def summarize(output, runs):
    rows = []
    for key in sorted({(r["case"], r["budget"], r["strategy"]) for r in runs}):
        group = [r for r in runs if (r["case"], r["budget"], r["strategy"]) == key]
        valid = [r for r in group if r["feasible"]]
        rows.append({"case": key[0], "budget": key[1], "strategy": key[2], "feasible": len(valid), "runs": len(group),
                     "median_cost": statistics.median(r["cost"] for r in valid) if valid else None,
                     "worst_cost": max((r["cost"] for r in valid), default=None),
                     "median_first_feasible": statistics.median(r["diagnostics"]["time_to_first_feasible"] for r in valid) if valid else None,
                     "median_wall_seconds": statistics.median(r["wall_seconds"] for r in group),
                     "peak_rss_mb": max((r["diagnostics"].get("peak_rss_mb", 0) for r in group)),
                     "median_gap": statistics.median(r["diagnostics"]["absolute_gap"] for r in valid) if valid else None})
    (output / "summary.json").write_text(json.dumps({"platform": platform.platform(), "python": platform.python_version(), "workers": 8, "concurrent_runs": 1, "rows": rows}, indent=2))
    lines = ["# Scenario A benchmark", "", "All costs use the documented policy and independent CSV validation. Invalid runs have no cost. Medians/worst costs cover feasible runs only; read them with the success counts. No official validator was available.", "", "| Case | Seconds | Strategy | Feasible | Median cost | Worst cost | Median gap | First feasible (s) | Wall (s) | Peak RSS MB |", "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    def fmt(v): return "—" if v is None else f"{v:.2f}"
    for row in rows:
        lines.append(f"| {row['case']} | {row['budget']:g} | {row['strategy']} | {row['feasible']}/{row['runs']} | {fmt(row['median_cost'])} | {fmt(row['worst_cost'])} | {fmt(row['median_gap'])} | {fmt(row['median_first_feasible'])} | {fmt(row['median_wall_seconds'])} | {fmt(row['peak_rss_mb'])} |")
    tuning = [r for r in rows if r["case"] == "public" and r["budget"] == max(x["budget"] for x in rows if x["case"] == "public")]
    if tuning:
        winner = min(tuning, key=lambda r: (-r["feasible"] / r["runs"], r["median_cost"] if r["median_cost"] is not None else float("inf"), r["worst_cost"] if r["worst_cost"] is not None else float("inf"), r["strategy"] != "integrated"))
        (output / "selection.json").write_text(json.dumps({"selected_strategy": winner["strategy"], "basis": "Public tuning set at largest tested budget: feasibility rate, median cost, worst cost; integrated preferred on ties. Heldout results do not tune the selection.", "evidence": winner}, indent=2))
    (output / "comparison.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__": main()
