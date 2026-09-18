from __future__ import annotations
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from app.ps1.models import Disruption, JobStatus, ReplanRun, Scenario, ScenarioRun, SolveJob
from app.ps1.replanning import audit_disruption, solution_diff
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

    def create(self, files, source):
        self.cleanup(); instance = parse_instance(files); now = datetime.now(UTC)
        job = SolveJob(uuid4().hex, JobStatus.QUEUED, now, now + timedelta(minutes=JOB_TTL_MINUTES), source, instance, {s: ScenarioRun() for s in Scenario})
        with self._lock:
            self._jobs[job.job_id] = job; self._events[job.job_id] = threading.Event()
        self._executor.submit(self._run, job.job_id)
        return job

    def create_public(self):
        return self.create({n: (PUBLIC_DATA_DIR / n).read_bytes() for n in EXPECTED_FILES}, "public")

    def get(self, job_id):
        self.cleanup()
        with self._lock: return self._jobs.get(job_id)

    def create_replan(self, job_id, scenario, disruption):
        job = self.get(job_id)
        if not job: return None
        with self._lock:
            run = job.scenarios[scenario]
            if run.status != JobStatus.COMPLETED or not run.solution or not run.solution.validation.feasible:
                raise ValueError(f"Scenario {scenario.value} must be completed and feasible before re-planning.")
            replan_id = uuid4().hex
            replan = ReplanRun(replan_id, scenario, run.solution.solution_revision, run.solution, disruption)
            job.replans[replan_id] = replan
        self._executor.submit(self._run_replan, job_id, replan_id)
        return replan

    def get_replan(self, job_id, replan_id):
        job = self.get(job_id)
        return job.replans.get(replan_id) if job else None

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

    def _run_replan(self, job_id, replan_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or replan_id not in job.replans: return
            replan = job.replans[replan_id]
            replan.status = JobStatus.RUNNING; replan.message = "Re-planning around the disruption."
        try:
            solution = solve_scenario(job.instance, replan.scenario, self.first_seconds,
                                      incumbent=replan.baseline_solution, disruption=replan.disruption)
            audit = audit_disruption(job.instance, solution, replan.disruption)
            if not audit["feasible"]:
                raise SolveFailure("disruption_validation_failed", str(audit["hard_violations"][:3]))
            diff = solution_diff(job.instance, replan.baseline_solution, solution, replan.disruption)
            with self._lock:
                if job_id not in self._jobs: return
                replan.solution = solution; replan.disruption_audit = audit; replan.diff = diff
                replan.status = JobStatus.COMPLETED; replan.message = "Validated revised schedule available."
        except SolveFailure as error:
            with self._lock:
                replan.status = JobStatus.FAILED; replan.error = str(error); replan.message = "No revised schedule was found."
        except Exception as error:
            with self._lock:
                replan.status = JobStatus.FAILED; replan.error = f"{type(error).__name__}: re-planning failed."


job_manager = JobManager()
