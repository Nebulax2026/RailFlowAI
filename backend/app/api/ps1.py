from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.ps1.exporter import scenario_csvs, solutions_zip
from app.ps1.jobs import job_manager
from app.ps1.models import Scenario, SolveJob
from app.ps1.parser import EXPECTED_FILES, InstanceValidationError

router = APIRouter()
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 16_000_000


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
    }


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
def download_scenario_file(job_id: str, scenario: Scenario, filename: str) -> Response:
    job = _require_job(job_id)
    solution = job.scenarios[scenario].solution
    if not solution or not solution.validation.feasible:
        raise HTTPException(status_code=409, detail="A validated scenario output is not available.")
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
            }
            for scenario, run in job.scenarios.items()
        },
    }
