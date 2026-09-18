"""Serial, cancellable A/B/C runs over 30 common test datasets."""
from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.ps1.jobs import job_manager
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.search import SearchConfig
from app.ps1.scenario_a.worker import run_worker

SUITE = Path(__file__).resolve().parents[3] / "datasets" / "scenario-suite-v1"
METHODS = ("legacy", "integrated", "random_lns", "alns")
BENCHMARK_WORKERS = 8


def catalog():
    return json.loads((SUITE / "manifest.json").read_text())


class BenchmarkManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._runs = {}
        # Share the one-slot queue with ordinary solve jobs. Each CP-SAT run
        # may use eight workers, but solver processes never run concurrently.
        self._executor = job_manager._executor

    def create(self, method, seconds, seed, case_ids=None):
        if method not in (*METHODS, "all"):
            raise ValueError("Unknown benchmark method.")
        entries = catalog()
        if case_ids is not None:
            requested = set(case_ids)
            if not requested or requested - {r["case_id"] for r in entries}:
                raise ValueError("Unknown or empty dataset selection.")
            entries = [r for r in entries if r["case_id"] in requested]
        methods = METHODS if method == "all" else (method,)
        rows = [dict(method=m, scenario=scenario.value, case_id=e["case_id"],
                     status="queued", score=None, elapsed_seconds=None,
                     termination_reason=None, error=None)
                for e in entries for m in methods for scenario in Scenario]
        now = datetime.now(UTC)
        run = dict(id=uuid4().hex, status="queued", created_at=now.isoformat(),
                   expires_at=(now+timedelta(seconds=len(rows)*(seconds+5)+3600)).isoformat(),
                   method=method, seconds=seconds, seed=seed, cp_sat_workers=BENCHMARK_WORKERS, rows=rows,
                   cancelled=threading.Event(), error=None)
        with self._lock:
            self._cleanup()
            self._runs[run["id"]] = run
            self._executor.submit(self._run, run["id"])
        return self.snapshot(run["id"])

    def _cleanup(self):
        for key, run in list(self._runs.items()):
            if datetime.fromisoformat(run["expires_at"]) <= datetime.now(UTC):
                run["cancelled"].set()
                del self._runs[key]

    def get(self, run_id):
        with self._lock:
            self._cleanup()
            return self.snapshot(run_id) if run_id in self._runs else None

    def snapshot(self, run_id):
        run = self._runs[run_id]
        rows = [dict(row) for row in run["rows"]]
        summary = []
        methods = METHODS if run["method"] == "all" else (run["method"],)
        for method in methods:
            for scenario in Scenario:
                subset = [r for r in rows if r["method"] == method and r["scenario"] == scenario.value]
                finished = [r for r in subset if r["status"] in ("completed", "failed", "cancelled")]
                valid = [r for r in finished if r["score"] is not None]
                summary.append(dict(method=method, scenario=scenario.value,
                                    total=len(subset), finished=len(finished), valid=len(valid),
                                    mean_score=round(sum(r["score"] for r in valid)/len(valid), 3) if valid else None,
                                    worst_score=max((r["score"] for r in valid), default=None)))
        return dict(id=run_id, status=run["status"], method=run["method"],
                    seconds=run["seconds"], seed=run["seed"], cp_sat_workers=run["cp_sat_workers"],
                    created_at=run["created_at"], expires_at=run["expires_at"],
                    error=run["error"], rows=rows, summary=summary)

    def cancel(self, run_id):
        with self._lock:
            self._cleanup()
            run = self._runs.get(run_id)
            if not run: return None
            if run["status"] in ("queued", "running"):
                run["cancelled"].set()
                run["status"] = "cancelled"
                for row in run["rows"]:
                    if row["status"] == "queued": row["status"] = "cancelled"
            return self.snapshot(run_id)

    def _run(self, run_id):
        with self._lock:
            run = self._runs.get(run_id)
            if not run or run["cancelled"].is_set(): return
            run["status"] = "running"
            rows = run["rows"]
        entries = {e["case_id"]: e for e in catalog()}
        try:
            for row in rows:
                if run["cancelled"].is_set(): break
                with self._lock: row["status"] = "running"
                started = time.monotonic()
                try:
                    entry = entries[row["case_id"]]
                    folder = SUITE / entry["input_path"]
                    files = {name: (folder / name).read_bytes() for name in EXPECTED_FILES}
                    instance = parse_instance(files)
                    strategy = "integrated" if row["method"] == "legacy" else row["method"]
                    config = SearchConfig(strategy=strategy, time_limit_seconds=run["seconds"],
                                          workers=BENCHMARK_WORKERS, seed=run["seed"])

                    def update(solution, diagnostics):
                        if solution:
                            with self._lock:
                                score = solution.validation.soft_scores["objective_score"]
                                if row["score"] is None or score < row["score"]:
                                    row["score"] = score
                    result = run_worker(instance, files, vars(config), run["cancelled"].is_set, update,
                                        Scenario(row["scenario"]), legacy=row["method"] == "legacy")
                    with self._lock:
                        if result.solution:
                            row["score"] = result.solution.validation.soft_scores["objective_score"]
                        row["status"] = "cancelled" if run["cancelled"].is_set() else "completed" if row["score"] is not None else "failed"
                        row["termination_reason"] = result.diagnostics.get("status")
                        row["error"] = result.diagnostics.get("error")
                except Exception as error:
                    with self._lock:
                        row["status"] = "cancelled" if run["cancelled"].is_set() else "failed"
                        row["termination_reason"] = "worker_error"
                        row["error"] = f"{type(error).__name__}: {error}"
                finally:
                    with self._lock: row["elapsed_seconds"] = round(time.monotonic()-started, 3)
            with self._lock:
                if not run["cancelled"].is_set():
                    run["status"] = "completed" if all(r["score"] is not None for r in rows) else "partial"
        except Exception as error:
            with self._lock:
                run["status"] = "failed"
                run["error"] = f"{type(error).__name__}: {error}"


benchmark_manager = BenchmarkManager()
