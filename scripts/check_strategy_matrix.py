"""Serial public-data smoke benchmark for all four methods and three scenarios."""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ps1.exporter import scenario_csvs
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.search import SearchConfig
from app.ps1.scenario_a.worker import run_worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = {n: (ROOT / "PS1/01_data" / n).read_bytes() for n in EXPECTED_FILES}
    instance = parse_instance(files)
    rows = []
    for strategy in ("greedy", "integrated", "random_lns", "alns"):
        for scenario in Scenario:
            config = asdict(SearchConfig(strategy=strategy, time_limit_seconds=args.seconds, seed=args.seed))
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
                       policy=result.diagnostics.get("policy"), phases=result.diagnostics.get("phases"))
            rows.append(row)
            (args.output / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(json.dumps(row), flush=True)
    return 0 if all(r["feasible"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
