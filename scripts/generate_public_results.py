from __future__ import annotations

import json
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ps1.exporter import scenario_csvs  # noqa: E402
from app.ps1.models import Scenario  # noqa: E402
from app.ps1.parser import EXPECTED_FILES, parse_instance  # noqa: E402
from app.ps1.solver import solve_scenario  # noqa: E402
from app.ps1.validator import validate_exported_csvs  # noqa: E402


def main() -> None:
    source = ROOT / "PS1" / "01_data"
    destination = ROOT / "submission" / "public-results"
    instance = parse_instance({name: (source / name).read_bytes() for name in EXPECTED_FILES})
    solutions = []
    summary = {}
    for scenario in Scenario:
        solution = solve_scenario(instance, scenario, time_limit_seconds=30)
        files = scenario_csvs(solution)
        solution.validation = validate_exported_csvs(instance, scenario, files)
        if not solution.validation.feasible:
            raise RuntimeError(f"Scenario {scenario.value} failed export validation: {solution.validation.hard_violations}")
        scenario_dir = destination / f"scenario_{scenario.value}"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (scenario_dir / filename).write_bytes(content)
        solutions.append((scenario, files))
        summary[scenario.value] = asdict(solution.validation)

    summary_bytes = json.dumps(summary, indent=2, default=str).encode("utf-8")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "validation_summary.json").write_bytes(summary_bytes)
    with zipfile.ZipFile(destination / "RailFlowAI-public-results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for scenario, files in solutions:
            for filename, content in files.items():
                archive.writestr(f"scenario_{scenario.value}/{filename}", content)
        archive.writestr("validation_summary.json", summary_bytes)
    print(f"Generated validated outputs in {destination}")


if __name__ == "__main__":
    main()
