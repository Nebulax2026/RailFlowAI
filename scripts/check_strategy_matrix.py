"""Serial public-data smoke benchmark for all four methods and three scenarios."""
import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import ortools

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ps1.exporter import scenario_csvs
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.search import SearchConfig
from app.ps1.scenario_a.worker import run_worker


def write_report(output):
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    rows = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    lines = ["# Public-data algorithm measurements", "",
             f"Budget: {metadata['seconds']:g}s per scenario; {metadata['workers']} CP-SAT workers; seed {metadata['seed']}; sequential runs.",
             "Each method/scenario was run once.", "",
             "| Method | Scenario | Validated score | First valid result (s) | Total wall time (s) | Outcome |",
             "|---|---|---:|---:|---:|---|"]
    def number(value):
        return "—" if value is None else f"{value:.2f}"
    for row in rows:
        diagnostics = json.loads((output / row['strategy'] / row['scenario'] / "diagnostics.json").read_text())
        note = diagnostics.get("validation_note")
        outcome = ("Optimal under implemented policy" if row['status'] == 'optimal_for_policy' else "Validated result") if row['feasible'] else (
            "Rejected by application CSV validator" if note else
            row['status'])
        lines.append(f"| {row['strategy']} | {row['scenario']} | {number(row['objective'])} | {number(row['first_feasible_seconds'])} | {number(row['elapsed_seconds'])} | {outcome} |")
    lines += ["", "Scores are comparable within a scenario; lower is better. Missing scores are not zero.",
              "Total wall time includes worker startup, parsing, search, and parent-side validation. First-result time is the first checkpoint accepted by the application validator.",
              "A rejected candidate is not evidence of infeasibility or merely a time-budget failure.", "",
              "All methods use the same closure policy and exported-CSV validator. Do not compare model bounds across different search methods.",
              "Earlier planner results with a different time budget are not a same-budget baseline. One seed on one public instance does not establish an overall algorithm ranking.", "",
              "Artifacts: summary.csv, summary.json, metadata.json, and per-method/scenario diagnostics. Validated results also include the three submission CSVs and validation.json.", ""]
    (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=8)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = {n: (ROOT / "PS1/01_data" / n).read_bytes() for n in EXPECTED_FILES}
    instance = parse_instance(files)
    metadata = dict(seconds=args.seconds, workers=args.workers, seed=args.seed,
                    platform=platform.platform(), python=platform.python_version(),
                    ortools=ortools.__version__, python_hash_seed=os.getenv("PYTHONHASHSEED"),
                    commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    git_status=subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
                    input_sha256={n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
                    note="Serial single-seed public-data measurement; all methods use the same closure policy and exported-CSV validator.")
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (args.output / "working-tree.patch").write_bytes(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT))
    rows = []
    for strategy in ("integrated", "random_lns", "alns"):
        for scenario in Scenario:
            config = asdict(SearchConfig(strategy=strategy, time_limit_seconds=args.seconds, seed=args.seed, workers=args.workers))
            result = run_worker(instance, files, config, lambda: False, lambda *_: None, scenario)
            directory = args.output / strategy / scenario.value
            directory.mkdir(parents=True)
            (directory / "diagnostics.json").write_text(json.dumps(result.diagnostics, indent=2) + "\n")
            if result.solution:
                for name, content in scenario_csvs(result.solution).items():
                    (directory / name).write_bytes(content)
                (directory / "validation.json").write_text(json.dumps(asdict(result.solution.validation), indent=2) + "\n")
            row = dict(strategy=strategy, scenario=scenario.value, config=config,
                       feasible=bool(result.solution and result.solution.validation.feasible),
                       status=result.diagnostics.get("status"), objective=result.diagnostics.get("objective"),
                       elapsed_seconds=result.diagnostics.get("worker_elapsed_seconds"),
                       first_feasible_seconds=result.diagnostics.get("time_to_first_feasible"),
                       global_lower_bound=result.diagnostics.get("global_lower_bound"),
                       absolute_gap=result.diagnostics.get("absolute_gap"),
                       validation_note=result.diagnostics.get("validation_note"),
                       policy=result.diagnostics.get("policy"), phases=result.diagnostics.get("phases"))
            rows.append(row)
            (args.output / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
            fields = ["strategy", "scenario", "feasible", "status", "objective", "first_feasible_seconds",
                      "elapsed_seconds", "global_lower_bound", "absolute_gap", "policy", "validation_note"]
            with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader(); writer.writerows(rows)
            print(json.dumps(row), flush=True)
    write_report(args.output)
    return 0 if all(r["feasible"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
