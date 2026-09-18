from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.ps1.models import JobStatus, Scenario, ScenarioRun, SolveJob
from app.ps1.exporter import scenario_csvs
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.solver import solve_scenario
from app.ps1.validator import validate_exported_csvs

JOB_TTL_MINUTES = 60
PUBLIC_DATA_DIR = Path(__file__).resolve().parents[3] / "PS1" / "01_data"


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, SolveJob] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ps1-solver")

    def create(self, files: dict[str, bytes], source: str) -> SolveJob:
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
            scenarios={scenario: ScenarioRun() for scenario in Scenario},
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._executor.submit(self._run, job.job_id)
        return job

    def create_public(self) -> SolveJob:
        files = {name: (PUBLIC_DATA_DIR / name).read_bytes() for name in EXPECTED_FILES}
        return self.create(files, "public")

    def get(self, job_id: str) -> SolveJob | None:
        self.cleanup()
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> SolveJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.cancel_requested = True
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
            return job

    def cleanup(self) -> None:
        now = datetime.now(UTC)
        with self._lock:
            expired = [job_id for job_id, job in self._jobs.items() if job.expires_at <= now]
            for job_id in expired:
                del self._jobs[job_id]

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.cancel_requested:
                return
            job.status = JobStatus.RUNNING
        completed = 0
        for scenario in Scenario:
            with self._lock:
                if job.cancel_requested:
                    job.status = JobStatus.CANCELLED
                    for pending in job.scenarios.values():
                        if pending.status == JobStatus.QUEUED:
                            pending.status = JobStatus.CANCELLED
                            pending.message = "Cancelled before solving."
                    return
                run = job.scenarios[scenario]
                run.status = JobStatus.RUNNING
                run.progress = 10
                run.message = f"Optimising Scenario {scenario.value}."
            try:
                solution = solve_scenario(job.instance, scenario)
                solution.validation = validate_exported_csvs(job.instance, scenario, scenario_csvs(solution))
                with self._lock:
                    run.solution = solution
                    run.progress = 100
                    run.status = JobStatus.COMPLETED if solution.validation.feasible else JobStatus.FAILED
                    run.message = "Feasible schedule validated." if solution.validation.feasible else "Schedule contains hard violations."
                    if not solution.validation.feasible:
                        run.error = f"{len(solution.validation.hard_violations)} hard violations detected."
                completed += int(solution.validation.feasible)
            except Exception as error:  # A failed scenario should not suppress the other policy runs.
                with self._lock:
                    run.status = JobStatus.FAILED
                    run.progress = 100
                    run.error = str(error)
                    run.message = "Solver failed."
        with self._lock:
            if completed == len(Scenario):
                job.status = JobStatus.COMPLETED
            else:
                job.status = JobStatus.FAILED
                job.error = f"{completed} of {len(Scenario)} scenarios completed with a feasible schedule."


job_manager = JobManager()
