from __future__ import annotations
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from app.ps1.models import JobStatus, Scenario, ScenarioRun, SolveJob
from app.ps1.exporter import scenario_csvs
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.solver import solve_scenario, SolveFailure
from app.ps1.validator import validate_exported_csvs

JOB_TTL_MINUTES = 60
PUBLIC_DATA_DIR = Path(__file__).resolve().parents[3] / "PS1" / "01_data"


class JobManager:
    def __init__(self, first_seconds=30, improve_seconds=90):
        self._jobs = {}; self._events = {}; self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ps1-solver")
        self.first_seconds = first_seconds; self.improve_seconds = improve_seconds

    def create(self, files: dict[str, bytes], source: str, algorithm: str = "legacy", solver_config: dict | None = None) -> SolveJob:
        self.cleanup()
        instance = parse_instance(files)
        now = datetime.now(UTC)
        job = SolveJob(
            job_id=uuid4().hex,
            status=JobStatus.QUEUED,
            created_at=now,
            expires_at=now + timedelta(minutes=JOB_TTL_MINUTES),
            source=source,
            instance=instance,
            scenarios={scenario: ScenarioRun() for scenario in ([Scenario.A] if algorithm == "scenario_a" else Scenario)},
            algorithm=algorithm, solver_config=solver_config or {},
            input_files=files if algorithm != "legacy" else {},
        )
        with self._lock:
            self._jobs[job.job_id] = job; self._events[job.job_id] = threading.Event()
        self._executor.submit(self._run, job.job_id)
        return job

    def create_public(self, algorithm: str = "legacy", solver_config: dict | None = None) -> SolveJob:
        files = {name: (PUBLIC_DATA_DIR / name).read_bytes() for name in EXPECTED_FILES}
        return self.create(files, "public", algorithm, solver_config)

    def get(self, job_id):
        self.cleanup()
        with self._lock: return self._jobs.get(job_id)

    def cancel(self, job_id):
        self.cleanup()
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                job.cancel_requested = True; self._events[job_id].set()
                if job.status == JobStatus.QUEUED: self._finish_cancel(job)
            return job

    def cleanup(self):
        with self._lock:
            for job_id in [k for k, v in self._jobs.items() if v.expires_at <= datetime.now(UTC)]:
                self._events.pop(job_id).set(); del self._jobs[job_id]

    def _finish_cancel(self, job):
        job.status = JobStatus.CANCELLED
        for run in job.scenarios.values():
            if run.phase != "finished":
                run.status = JobStatus.CANCELLED; run.phase = "finished"; run.termination_reason = "cancelled"
                run.message = "Cancelled; validated result retained." if run.solution else "Cancelled without a result."

    def _publish(self, job, scenario, solution):
        report = validate_exported_csvs(job.instance, scenario, scenario_csvs(solution))
        if not report.feasible: raise SolveFailure("validation_failed", str(report.hard_violations[:3]))
        with self._lock:
            if job.job_id not in self._jobs: return
            run = job.scenarios[scenario]
            if run.solution and report.soft_scores['objective_score'] >= run.solution.validation.soft_scores['objective_score']: return
            solution.validation = report
            solution.solution_revision = (run.solution.solution_revision if run.solution else 0) + 1
            run.solution = solution; run.solver_stats = dict(solution.solver_stats)
            run.message = "Validated schedule available; searching for improvements."

    def _run(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.cancel_requested: return
            event = self._events[job_id]; job.status = JobStatus.RUNNING
        if job.algorithm != "legacy":
            self._run_scenario_a(job)
            return
        for phase, budget in (("first_search", self.first_seconds), ("improving", self.improve_seconds)):
            for scenario in Scenario:
                with self._lock:
                    if event.is_set(): self._finish_cancel(job); return
                    run = job.scenarios[scenario]
                    if run.termination_reason in {"optimal", "infeasible", "validation_failed", "error"}: continue
                    run.status = JobStatus.RUNNING; run.phase = phase; run.progress = 10 if phase == "first_search" else 50
                    run.message = "Searching for a complete schedule." if not run.solution else "Improving validated schedule."
                    previous_elapsed = run.solver_stats.get('elapsed_seconds', 0)
                    previous_first = run.solver_stats.get('first_feasible_seconds')
                try:
                    solution = solve_scenario(job.instance, scenario, budget, incumbent=run.solution,
                                              on_solution=lambda s, sc=scenario: self._publish(job, sc, s), cancel_event=event)
                    self._publish(job, scenario, solution)
                    with self._lock:
                        run.solver_stats = dict(solution.solver_stats)
                        run.solver_stats['elapsed_seconds'] += previous_elapsed
                        if previous_first is not None: run.solver_stats['first_feasible_seconds'] = previous_first
                        elif run.solver_stats.get('first_feasible_seconds') is not None: run.solver_stats['first_feasible_seconds'] += previous_elapsed
                        run.termination_reason = solution.solver_stats['termination_reason']; run.error = None
                except SolveFailure as error:
                    run.termination_reason = error.reason; run.error = str(error)
                    run.solver_stats = {**run.solver_stats, 'elapsed_seconds': previous_elapsed + budget}
                except Exception as error:
                    run.termination_reason = "error"; run.error = f"{type(error).__name__}: scheduling failed."
                with self._lock:
                    if event.is_set(): self._finish_cancel(job); return
                    final = phase == "improving" or run.termination_reason in {"optimal", "infeasible", "validation_failed", "error"}
                    run.phase = "finished" if final else "waiting_improvement"
                    run.progress = 100 if final else 35
                    run.status = (JobStatus.COMPLETED if run.solution else JobStatus.FAILED) if final else JobStatus.QUEUED
                    run.message = ("Optimality proved." if run.termination_reason == "optimal" else "Validated schedule retained; optimum not proved.") if run.solution else (run.error or "No validated schedule found.")
        with self._lock:
            job.status = JobStatus.COMPLETED if all(r.solution for r in job.scenarios.values()) else JobStatus.FAILED
            if job.status == JobStatus.FAILED: job.error = "Some scenarios have no validated output; available scenarios remain downloadable."

    def _run_scenario_a(self, job: SolveJob) -> None:
        # The old scenario_a API remains A-only; strategies runs A/B/C.
        from app.ps1.scenario_a.worker import run_worker
        event = self._events[job.job_id]
        try:
            for scenario, run in job.scenarios.items():
                if event.is_set():
                    with self._lock: self._finish_cancel(job)
                    return
                with self._lock:
                    run.status = JobStatus.RUNNING
                    run.phase = "first_search"
                    run.progress = 5
                    run.message = f"Searching for a complete Scenario {scenario.value} schedule."

                def update(solution, diagnostics):
                    with self._lock:
                        if job.job_id not in self._jobs: return
                        if solution and (not run.solution or solution.validation.soft_scores["objective_score"] < run.solution.validation.soft_scores["objective_score"]):
                            solution.solution_revision = (run.solution.solution_revision if run.solution else 0) + 1
                            run.solution = solution
                        run.diagnostics = diagnostics
                        run.phase = "improving" if run.solution else "first_search"
                        run.solver_stats = {
                            "elapsed_seconds": diagnostics.get("elapsed_seconds"),
                            "first_feasible_seconds": diagnostics.get("time_to_first_feasible"),
                            "optimal": diagnostics.get("status") == "optimal_for_policy",
                        }
                        if run.solution:
                            run.solution.solver_stats = dict(run.solver_stats)
                            score = run.solution.validation.soft_scores["objective_score"]
                            run.message = f"Validated incumbent: {score:g}. Improving within the time budget."
                        run.progress = min(95, max(10, int(100 * diagnostics.get("elapsed_seconds", 0) / job.solver_config["time_limit_seconds"])))
                try:
                    result = run_worker(job.instance, job.input_files, job.solver_config, event.is_set, update, scenario)
                    update(result.solution, result.diagnostics)
                    with self._lock:
                        if event.is_set():
                            self._finish_cancel(job)
                            return
                        run.phase = "finished"
                        run.termination_reason = result.diagnostics.get("status")
                        run.progress = 100
                        if run.termination_reason == "input_or_model_error":
                            run.status = JobStatus.FAILED
                            run.error = result.diagnostics.get("error", "Input or model error.")
                            run.message = run.error
                        elif run.solution:
                            run.status = JobStatus.COMPLETED
                            run.message = "Optimal under the configured policy." if run.termination_reason == "optimal_for_policy" else "Validated schedule found; optimality not proven."
                        else:
                            run.status = JobStatus.FAILED
                            run.error = ("Infeasible under the configured safety policy; official feasibility is unconfirmed."
                                         if run.termination_reason == "infeasible_for_policy" else "No complete valid schedule found within the time budget. Try a longer run.")
                            run.message = run.error
                except Exception as error:
                    with self._lock:
                        run.status = JobStatus.FAILED
                        run.phase = "finished"
                        run.termination_reason = "error"
                        run.error = str(error)
                        run.message = f"Scenario {scenario.value} worker failed."
            with self._lock:
                job.status = JobStatus.COMPLETED if all(r.status == JobStatus.COMPLETED for r in job.scenarios.values()) else JobStatus.FAILED
                if job.status == JobStatus.FAILED:
                    job.error = "Some scenarios have no validated output; available results remain downloadable."
        finally:
            job.input_files = {}


job_manager = JobManager()
