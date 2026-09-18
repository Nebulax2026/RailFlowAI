from __future__ import annotations

import json
import sys
import platform
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ps1.exporter import scenario_csvs, solutions_zip, validation_summary  # noqa: E402
from app.ps1.models import Scenario  # noqa: E402
from app.ps1.parser import EXPECTED_FILES, parse_instance  # noqa: E402
from app.ps1.solver import solve_scenario  # noqa: E402
from app.ps1.validator import validate_exported_csvs  # noqa: E402


def main() -> None:
    source = ROOT / "PS1" / "01_data"
    destination = ROOT / "submission" / "public-results"
    instance = parse_instance({name: (source / name).read_bytes() for name in EXPECTED_FILES})
    solutions = {}
    summary = {}
    benchmark = {"platform": platform.platform(), "python": platform.python_version(), "runs": {}}
    compatibility_path = destination / "compatibility_report.json"
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8")) if compatibility_path.exists() else {}
    sample_dir = ROOT / "PS1" / "03_submission_sample"
    sample_files = {n: (sample_dir / n).read_bytes() for n in ("SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv")}
    compatibility["organizer_sample"] = validation_summary(validate_exported_csvs(instance, Scenario.A, sample_files))
    for scenario in Scenario:
        old_dir = destination / f"scenario_{scenario.value}"
        if old_dir.exists() and f"previous_{scenario.value}" not in compatibility:
            old_files = {n: (old_dir / n).read_bytes() for n in sample_files}
            compatibility[f"previous_{scenario.value}"] = validation_summary(validate_exported_csvs(instance, scenario, old_files))
    for report in compatibility.values():
        report['detail'] = {k:v for k,v in report['detail'].items() if k in ('safety_policy','nights_scheduled','eclo_nights','score_breakdown')}
    for phase, seconds in (("first", 30), ("improve", 90)):
        for scenario in Scenario:
            previous = solutions.get(scenario)
            if previous and previous.solver_stats.get("optimal"): continue
            start = time.monotonic()
            solution = solve_scenario(instance, scenario, time_limit_seconds=seconds, incumbent=previous)
            benchmark["runs"].setdefault(scenario.value, []).append({"phase": phase, **solution.solver_stats, "wall_seconds": time.monotonic() - start})
            solution.solution_revision = (previous.solution_revision if previous else 0) + 1
            solutions[scenario] = solution
            print(f"{phase} {scenario.value}: score {solution.validation.soft_scores['objective_score']}, {solution.solver_stats}", flush=True)
    for scenario, solution in solutions.items():
        files = scenario_csvs(solution)
        solution.validation = validate_exported_csvs(instance, scenario, files)
        if not solution.validation.feasible:
            raise RuntimeError(f"Scenario {scenario.value} failed export validation: {solution.validation.hard_violations}")
        scenario_dir = destination / f"scenario_{scenario.value}"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (scenario_dir / filename).write_bytes(content)
        summary[scenario.value] = validation_summary(solution.validation)

    summary_bytes = json.dumps(summary, indent=2, default=str).encode("utf-8")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "validation_summary.json").write_bytes(summary_bytes)
    (destination / "RailFlowAI-public-results.zip").write_bytes(solutions_zip(list(solutions.values())))
    (destination / "benchmark.json").write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    (destination / "compatibility_report.json").write_text(json.dumps(compatibility, indent=2, default=str), encoding="utf-8")
    print(f"Generated validated outputs in {destination}")


if __name__ == "__main__":
    main()
