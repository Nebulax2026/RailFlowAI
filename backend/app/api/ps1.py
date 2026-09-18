from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.ps1.exporter import scenario_csvs, solutions_zip
from app.ps1.jobs import job_manager
from app.ps1.models import Disruption, JobStatus, Scenario, SolveJob
from app.ps1.parser import EXPECTED_FILES, InstanceValidationError
from app.ps1.evidence import activity_details
from app.ps1.assistant import answer_question, enforce_query_rate

router = APIRouter()
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 16_000_000


class ReplanRequest(BaseModel):
    location_id: str
    start_week: int = Field(ge=1)
    end_week: int = Field(ge=1)
    capacity: int = Field(ge=0)
    reason: str = Field(pattern="^(urgent_maintenance|defect|access_restriction|other)$")


class AssistantRequest(BaseModel):
    scenario: Scenario
    question: str = Field(min_length=1, max_length=500)
    replan_id: str | None = None


@router.post("/jobs", status_code=202)
async def create_job(files: list[UploadFile] | None = File(default=None), public: bool = False) -> dict:
    try:
        if public:
            job = job_manager.create_public()
        else:
            if not files:
                raise HTTPException(status_code=422, detail="Upload all eight PS1 CSV files or set public=true.")
            payload: dict[str, bytes] = {}
            total = 0
            for upload in files:
                filename = upload.filename or ""
                if filename in payload:
                    raise HTTPException(status_code=422, detail=f"Duplicate upload: {filename}.")
                content = await upload.read(MAX_FILE_BYTES + 1)
                if len(content) > MAX_FILE_BYTES:
                    raise HTTPException(status_code=413, detail=f"{filename} exceeds 2 MB.")
                total += len(content)
                if total > MAX_TOTAL_BYTES:
                    raise HTTPException(status_code=413, detail="Combined upload exceeds 16 MB.")
                payload[filename] = content
            job = job_manager.create(payload, "upload")
    except InstanceValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors) from error
    return _job_payload(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _job_payload(_require_job(job_id))


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    job = job_manager.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Solve job not found or expired.")
    return _job_payload(job)


@router.get("/jobs/{job_id}/scenarios/{scenario}")
def get_scenario(job_id: str, scenario: Scenario) -> dict:
    job = _require_job(job_id)
    run = job.scenarios[scenario]
    if not run.solution:
        raise HTTPException(status_code=409, detail=run.error or f"Scenario {scenario.value} is not complete.")
    solution = run.solution
    files = scenario_csvs(solution)
    return {
        "scenario": scenario.value,
        "status": run.status.value,
        "validation": asdict(solution.validation),
        "explanations": solution.explanations,
        "results": [asdict(item) for item in solution.results],
        "accesses": [asdict(item) for item in solution.accesses],
        "occupancy": [asdict(item) for item in solution.occupancy],
        "downloads": list(files),
        "phase": run.phase,
        "termination_reason": run.termination_reason,
        "solution_revision": solution.solution_revision,
        "solver_stats": run.solver_stats,
        "score_breakdown": solution.validation.detail["score_breakdown"],
        "activity_details": activity_details(job.instance, solution),
        "locations": [{"location_id": item.location_id, "capacity": item.supply_capacity}
                      for item in sorted(job.instance.supply.values(), key=lambda item: item.location_id)],
    }


@router.post("/jobs/{job_id}/scenarios/{scenario}/replans", status_code=202)
def create_replan(job_id: str, scenario: Scenario, request: ReplanRequest) -> dict:
    job = _require_job(job_id)
    supply = job.instance.supply.get(request.location_id)
    if not supply:
        raise HTTPException(status_code=422, detail="Unknown disruption location_id.")
    if request.start_week > request.end_week or request.end_week > job.instance.horizon_weeks:
        raise HTTPException(status_code=422, detail="Disruption weeks must be ordered and inside the planning horizon.")
    if request.capacity >= supply.supply_capacity:
        raise HTTPException(status_code=422, detail="Disruption capacity must be lower than nominal supply.")
    try:
        replan = job_manager.create_replan(job_id, scenario, Disruption(**request.model_dump()))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not replan:
        raise HTTPException(status_code=404, detail="Solve job not found or expired.")
    return _replan_payload(job, replan, include_solution=False)


@router.get("/jobs/{job_id}/scenarios/{scenario}/replans/{replan_id}")
def get_replan(job_id: str, scenario: Scenario, replan_id: str) -> dict:
    job = _require_job(job_id); replan = job_manager.get_replan(job_id, replan_id)
    if not replan or replan.scenario != scenario:
        raise HTTPException(status_code=404, detail="Re-plan not found or expired.")
    return _replan_payload(job, replan, include_solution=True)


@router.get("/jobs/{job_id}/scenarios/{scenario}/replans/{replan_id}/files/{filename}")
def download_replan_file(job_id: str, scenario: Scenario, replan_id: str, filename: str) -> Response:
    _require_job(job_id); replan = job_manager.get_replan(job_id, replan_id)
    if not replan or replan.scenario != scenario:
        raise HTTPException(status_code=404, detail="Re-plan not found or expired.")
    if (replan.status != JobStatus.COMPLETED or not replan.solution
            or not replan.solution.validation.feasible or not replan.disruption_audit.get("feasible")):
        raise HTTPException(status_code=409, detail="A fully validated revised output is not available.")
    files = scenario_csvs(replan.solution)
    if filename not in files: raise HTTPException(status_code=404, detail="Unknown scenario output file.")
    return Response(files[filename], media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="revised-{filename}"'})


@router.post("/jobs/{job_id}/assistant/query")
def schedule_query(job_id: str, request: AssistantRequest) -> dict:
    job = _require_job(job_id)
    if not enforce_query_rate(job_id): raise HTTPException(status_code=429, detail="Schedule Assistant rate limit exceeded.")
    diff = None
    if request.replan_id:
        replan = job.replans.get(request.replan_id)
        if not replan or replan.scenario != request.scenario or not replan.solution:
            raise HTTPException(status_code=409, detail="The requested revised schedule is not available.")
        solution = replan.solution; diff = replan.diff
    else:
        solution = job.scenarios[request.scenario].solution
        if not solution: raise HTTPException(status_code=409, detail="The requested baseline schedule is not available.")
    return answer_question(job.instance, solution, request.question.strip(), diff)


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str) -> Response:
    job = _require_job(job_id)
    solutions = [run.solution for run in job.scenarios.values() if run.solution and run.solution.validation.feasible]
    if not solutions:
        raise HTTPException(status_code=409, detail="No validated scenario outputs are available.")
    return Response(
        solutions_zip(solutions),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="railflow-{job.job_id[:8]}-results.zip"'},
    )


@router.get("/jobs/{job_id}/scenarios/{scenario}/files/{filename}")
def download_scenario_file(job_id: str, scenario: Scenario, filename: str, revision: int | None = None) -> Response:
    job = _require_job(job_id)
    solution = job.scenarios[scenario].solution
    if not solution or not solution.validation.feasible:
        raise HTTPException(status_code=409, detail="A validated scenario output is not available.")
    if revision is not None and revision != solution.solution_revision:
        raise HTTPException(status_code=409, detail="A newer result is available. Refresh the scenario before downloading.")
    files = scenario_csvs(solution)
    if filename not in files:
        raise HTTPException(status_code=404, detail="Unknown scenario output file.")
    return Response(files[filename], media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _require_job(job_id: str) -> SolveJob:
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Solve job not found or expired.")
    return job


def _job_payload(job: SolveJob) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "source": job.source,
        "created_at": job.created_at,
        "expires_at": job.expires_at,
        "error": job.error,
        "instance": {
            "lines": len(job.instance.lines),
            "stations": len(job.instance.stations),
            "sectors": len(job.instance.sectors),
            "locations": len(job.instance.supply),
            "contracts": len(job.instance.contracts),
            "activities": len(job.instance.activities),
            "total_accesses": sum(item.total_accesses for item in job.instance.activities.values()),
            "horizon_start": job.instance.horizon_start,
            "horizon_weeks": job.instance.horizon_weeks,
        },
        "scenarios": {
            scenario.value: {
                "status": run.status.value,
                "progress": run.progress,
                "message": run.message,
                "error": run.error,
                "feasible": run.solution.validation.feasible if run.solution else None,
                "objective_score": run.solution.validation.soft_scores.get("objective_score") if run.solution else None,
                "phase": run.phase,
                "termination_reason": run.termination_reason,
                "solution_revision": run.solution.solution_revision if run.solution else 0,
                "solver_stats": run.solver_stats,
                "scores": run.solution.validation.soft_scores if run.solution else None,
            }
            for scenario, run in job.scenarios.items()
        },
    }


def _replan_payload(job, replan, include_solution):
    payload = {"replan_id": replan.replan_id, "scenario": replan.scenario.value,
               "baseline_revision": replan.baseline_revision, "status": replan.status.value,
               "message": replan.message, "error": replan.error,
               "disruption": asdict(replan.disruption), "expires_at": job.expires_at,
               "disruption_audit": replan.disruption_audit, "diff": replan.diff}
    if include_solution and replan.solution:
        solution = replan.solution
        payload["solution"] = {"validation": asdict(solution.validation),
                               "results": [asdict(item) for item in solution.results],
                               "accesses": [asdict(item) for item in solution.accesses],
                               "occupancy": [asdict(item) for item in solution.occupancy],
                               "solver_stats": solution.solver_stats,
                               "score_breakdown": solution.validation.detail["score_breakdown"],
                               "activity_details": activity_details(job.instance, solution)}
    return payload
