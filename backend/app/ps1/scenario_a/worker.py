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
from app.ps1.scenario_a.search import SearchResult
from app.ps1.scenario_a.validation import HEADERS, validate_csvs


def read_solution(instance, directory, scenario=Scenario.A, legacy=False):
    files = {name: (directory / name).read_bytes() for name in HEADERS}
    from app.ps1.validator import validate_exported_csvs
    report = validate_csvs(instance, files) if scenario == Scenario.A and not legacy else validate_exported_csvs(instance, scenario, files)
    if not report.feasible:
        raise ValueError("Worker checkpoint failed independent CSV validation.")
    tables = {name: list(csv.DictReader(io.StringIO(content.decode()))) for name, content in files.items()}
    accesses = [AccessAssignment(r["activity_id"], int(r["access_seq"]), int(r["week"]), int(r["eclo"]), int(r["access_night"])) for r in tables["SCHEDULE_ACCESS.csv"]]
    occupancy = [OccupancyAssignment(r["activity_id"], int(r["week"]), r["location_id"], r["co_share_group"]) for r in tables["SCHEDULE_OCCUPANCY.csv"]]
    results = [ContractResult(r["scenario"], r["contract_number"], date.fromisoformat(r["simulated_completion_date"]), int(r["overrun_days"])) for r in tables["RESULTS.csv"]]
    return ScenarioSolution(scenario, accesses, occupancy, results, report,
                            [f"CSV outputs validated against the documented Scenario {scenario.value} safety policy.",
                             "Official validator is not publicly supplied; policy parity remains unconfirmed."])


def run_worker(instance, files, config, cancelled, on_update, scenario=Scenario.A, legacy=False):
    best, diagnostics, last_checkpoint = None, {}, None
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="railflow-scenario-a-") as temporary:
        root = Path(temporary)
        inputs, output = root / "input", root / "output"
        inputs.mkdir(); output.mkdir()
        for name, content in files.items():
            (inputs / name).write_bytes(content)
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config))
        with (root / "worker.log").open("w+") as log:
            process = subprocess.Popen([sys.executable, "-m", "app.ps1.scenario_a.cli", "--input", str(inputs),
                                        "--output", str(output), "--config", str(config_path), "--scenario", scenario.value] + (["--legacy"] if legacy else []),
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
                            candidate = read_solution(instance, output / saved["directory"], scenario, legacy)
                            best, diagnostics = candidate, saved["diagnostics"]
                            on_update(best, diagnostics)
                            last_checkpoint = content
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
                diagnostics["worker_elapsed_seconds"] = time.monotonic() - started
                return SearchResult(best, diagnostics)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
