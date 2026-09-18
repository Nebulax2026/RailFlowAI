"""Revalidate all shared dataset witnesses under the current application policy."""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ps1.benchmark import SUITE, catalog
from app.ps1.models import Scenario
from app.ps1.safety import POLICY_VERSION
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.validation import validate_csvs
from app.ps1.validator import OUTPUT_HEADERS, validate_exported_csvs


def main():
    cases = {}
    for entry in catalog():
        folder = SUITE / entry["input_path"]
        instance = parse_instance({name: (folder / name).read_bytes() for name in EXPECTED_FILES})
        scenarios = {}
        for scenario in Scenario:
            witness = folder.parent / "witness" / scenario.value
            files = {name: (witness / name).read_bytes() for name in OUTPUT_HEADERS}
            report = validate_exported_csvs(instance, scenario, files)
            row = {"feasible": report.feasible, "hard_violation_count": len(report.hard_violations),
                   "violation_sample": report.hard_violations[:3],
                   "violations_sha256": hashlib.sha256(json.dumps(report.hard_violations, sort_keys=True).encode()).hexdigest(),
                   "objective_score": report.soft_scores.get("objective_score")}
            if scenario == Scenario.A:
                independent = validate_csvs(instance, files)
                row["independent_a_feasible"] = independent.feasible
            scenarios[scenario.value] = row
        cases[entry["case_id"]] = scenarios
    passed = sum(row["feasible"] for scenarios in cases.values() for row in scenarios.values())
    output = {"policy": POLICY_VERSION, "dataset_count": len(cases),
              "scenario_checks": len(cases) * len(Scenario), "feasible_checks": passed,
              "cases": cases}
    destination = ROOT / "benchmarks/dataset-suite/current-validation.json"
    destination.write_text(json.dumps(output, indent=2) + "\n")
    print(f"{passed}/{output['scenario_checks']} current-policy witnesses valid; {destination}")
    return 0 if passed == output["scenario_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
