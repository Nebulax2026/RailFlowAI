"""One bounded solver process, with independently checked incumbent recovery."""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from app.ps1.models import AccessAssignment, ContractResult, OccupancyAssignment, Scenario, ScenarioSolution
from app.ps1.strategy import SearchResult
from app.ps1.validator import OUTPUT_HEADERS

HEADERS = OUTPUT_HEADERS


def read_solution(instance, directory, scenario=Scenario.A):
    files = {name: (directory / name).read_bytes() for name in HEADERS}
    from app.ps1.validator import validate_exported_csvs
    report = validate_exported_csvs(instance, scenario, files)
    if not report.feasible:
        raise ValueError("Worker checkpoint failed independent CSV validation.")
    tables = {name: list(csv.DictReader(io.StringIO(content.decode()))) for name, content in files.items()}
    accesses = [AccessAssignment(r["activity_id"], int(r["access_seq"]), int(r["week"]), int(r["eclo"]), int(r["access_night"])) for r in tables["SCHEDULE_ACCESS.csv"]]
    occupancy = [OccupancyAssignment(r["activity_id"], int(r["week"]), r["location_id"], r["co_share_group"]) for r in tables["SCHEDULE_OCCUPANCY.csv"]]
    results = [ContractResult(r["scenario"], r["contract_number"], date.fromisoformat(r["simulated_completion_date"]), int(r["overrun_days"])) for r in tables["RESULTS.csv"]]
    return ScenarioSolution(scenario, accesses, occupancy, results, report,
                            [f"CSV outputs validated against the documented Scenario {scenario.value} safety policy.",
                             "Official validator is not publicly supplied; policy parity remains unconfirmed."])


def run_worker(instance, files, config, cancelled, on_update, scenario=Scenario.A):
    best, diagnostics, last_checkpoint = None, {}, None
    accepted_trajectory = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="railflow-strategy-") as temporary:
        root = Path(temporary)
        inputs, output = root / "input", root / "output"
        inputs.mkdir(); output.mkdir()
        for name, content in files.items():
            (inputs / name).write_bytes(content)
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config))
        with (root / "worker.log").open("w+") as log:
            process = subprocess.Popen([sys.executable, "-m", "app.ps1.strategy_cli", "--input", str(inputs),
                                        "--output", str(output), "--config", str(config_path), "--scenario", scenario.value],
                                       cwd=Path(__file__).resolve().parents[3], stdout=log, stderr=log)
            terminated_at = None
            try:
                while True:
                    alive = process.poll() is None
                    manifest = output / "checkpoint.json"
                    if manifest.exists():
                        content = manifest.read_text()
                        if content != last_checkpoint:
                            saved = json.loads(content)
                            last_checkpoint = content
                            try:
                                candidate = read_solution(instance, output / saved["directory"], scenario)
                            except ValueError:
                                # A strategy's older safety model is not a bypass
                                # of the application-wide exported-CSV validator.
                                candidate = None
                            if candidate is not None:
                                best, diagnostics = candidate, saved["diagnostics"]
                                accepted_trajectory.append({"seconds": time.monotonic() - started, "objective": best.validation.soft_scores["objective_score"]})
                                diagnostics = {**diagnostics, "objective": best.validation.soft_scores["objective_score"], "trajectory": list(accepted_trajectory), "time_to_first_feasible": accepted_trajectory[0]["seconds"]}
                                on_update(best, diagnostics)
                    if not alive:
                        break
                    expired = time.monotonic() - started > config["time_limit_seconds"] + 3
                    if (cancelled() or expired) and terminated_at is None:
                        process.terminate(); terminated_at = time.monotonic()
                    elif terminated_at is not None and time.monotonic() - terminated_at > 2:
                        process.kill()
                    time.sleep(0.15)
                report_path = output / "diagnostics.json"
                if report_path.exists():
                    diagnostics = json.loads(report_path.read_text())
                elif cancelled():
                    diagnostics = {**diagnostics, "status": "cancelled_with_feasible" if best else "cancelled_without_solution"}
                else:
                    diagnostics = {**diagnostics, "status": "feasible" if best else "no_solution_within_budget",
                                   "worker_interrupted": True}
                if best is None and diagnostics.get("status") in {"optimal_for_policy", "feasible", "cancelled_with_feasible"}:
                    diagnostics["status"] = "no_solution_within_budget"
                    diagnostics["validation_note"] = "No checkpoint passed the current application CSV validator."
                diagnostics["objective"] = best.validation.soft_scores["objective_score"] if best else None
                diagnostics["trajectory"] = accepted_trajectory
                diagnostics["time_to_first_feasible"] = accepted_trajectory[0]["seconds"] if accepted_trajectory else None
                diagnostics["worker_elapsed_seconds"] = time.monotonic() - started
                return SearchResult(best, diagnostics)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()


