from __future__ import annotations

from dataclasses import asdict
from typing import Literal
import json

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.ps1.exporter import scenario_csvs, solutions_zip
from app.ps1.jobs import job_manager
from app.ps1.models import Scenario, SolveJob
from app.ps1.parser import EXPECTED_FILES, InstanceValidationError
from app.ps1.evidence import activity_details
from app.ps1.benchmark import benchmark_manager, catalog

router = APIRouter()
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 16_000_000


@router.get("/benchmark/datasets")
def benchmark_datasets() -> dict:
    return {"datasets": [
        {key: row[key] for key in ("case_id", "scenario", "profile", "split", "activities",
                                   "contracts", "horizon_weeks", "predecessor_links", "live_activities")}
        for row in catalog()
    ], "count": 30, "per_scenario": 10,
        "provenance": "Synthetic, with internally validated feasible witness schedules; not organizer hidden data."}


@router.get("/benchmark/datasets/download/{scenario}")
def download_benchmark_datasets(scenario: Scenario) -> Response:
    from app.ps1.benchmark import SUITE
    return Response((SUITE / f"scenario_{scenario.value}_inputs.zip").read_bytes(),
                    media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="scenario-{scenario.value}-10-datasets.zip"'})


@router.post("/benchmark/runs", status_code=202)
def create_benchmark(method: Literal["legacy", "greedy", "integrated", "random_lns", "alns", "all"] = "all",
                     time_limit_seconds: float = Query(default=15, ge=5, le=120),
                     seed: int = Query(default=42, ge=0, le=2147483647)) -> dict:
    return benchmark_manager.create(method, time_limit_seconds, seed)


@router.get("/benchmark/runs/{run_id}")
def get_benchmark(run_id: str) -> dict:
    run = benchmark_manager.get(run_id)
    if not run: raise HTTPException(status_code=404, detail="Benchmark run not found or expired.")
    return run


@router.delete("/benchmark/runs/{run_id}")
def cancel_benchmark(run_id: str) -> dict:
    run = benchmark_manager.cancel(run_id)
    if not run: raise HTTPException(status_code=404, detail="Benchmark run not found or expired.")
    return run


@router.get("/benchmark/runs/{run_id}/report")
def benchmark_report(run_id: str) -> Response:
    run = benchmark_manager.get(run_id)
    if not run: raise HTTPException(status_code=404, detail="Benchmark run not found or expired.")
    return Response(json.dumps(run, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="dataset-benchmark.json"'})


@router.post("/jobs", status_code=202)
async def create_job(files: list[UploadFile] | None = File(default=None), public: bool = False,
                     algorithm: Literal["legacy", "scenario_a", "strategies"] = "legacy",
                     strategy: Literal["integrated", "alns", "random_lns", "greedy"] = "alns",
                     time_limit_seconds: float = Query(default=15, ge=5, le=120),
                     seed: int = Query(default=42, ge=0, le=2147483647)) -> dict:
    config = None
    if algorithm != "legacy":
        from app.ps1.scenario_a.search import SearchConfig
        config = asdict(SearchConfig(strategy=strategy, time_limit_seconds=time_limit_seconds, seed=seed))
    try:
        if public:
            job = job_manager.create_public(algorithm, config)
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
            job = job_manager.create(payload, "upload", algorithm, config)
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
    if scenario not in job.scenarios:
        raise HTTPException(status_code=404, detail="This run only includes Scenario A.")
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
        "score_breakdown": solution.validation.detail.get("score_breakdown", {
            "delay": solution.validation.soft_scores.get("priority_weighted_score", 0),
            "excess_supply": 0, "eclo": 0,
        }),
        "activity_details": activity_details(job.instance, solution) if "location_usage" in solution.validation.detail else [],
        "diagnostics": run.diagnostics,
    }


@router.get("/jobs/{job_id}/diagnostics")
def download_diagnostics(job_id: str) -> Response:
    job = _require_job(job_id)
    return Response(json.dumps({s.value: run.diagnostics for s, run in job.scenarios.items()}, indent=2),
                    media_type="application/json", headers={"Content-Disposition": 'attachment; filename="solver-diagnostics.json"'})


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
    if scenario not in job.scenarios:
        raise HTTPException(status_code=404, detail="This run only includes Scenario A.")
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
        "algorithm": job.algorithm,
        "solver_config": job.solver_config,
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
                "diagnostics": run.diagnostics,
            }
            for scenario, run in job.scenarios.items()
        },
    }
