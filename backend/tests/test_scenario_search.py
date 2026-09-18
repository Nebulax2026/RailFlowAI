from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from .test_ps1 import instance
from .test_regressions import tiny
from app.main import app
from app.api import ps1 as api
from app.ps1 import jobs
from app.ps1.exporter import scenario_csvs
from app.ps1.jobs import JobManager
from app.ps1.models import JobStatus, Scenario
from app.ps1.scenario_a.search import SearchConfig, SearchResult
from app.ps1.scenario_a import worker
from app.ps1.scenario_search import solve
from app.ps1.validator import validate_exported_csvs


@pytest.mark.parametrize("strategy", ["greedy", "integrated", "random_lns", "alns"])
@pytest.mark.parametrize("scenario", [Scenario.B, Scenario.C])
def test_four_methods_respect_bc_rules_and_score(tiny, strategy, scenario):
    result = solve(tiny, scenario, SearchConfig(strategy=strategy, time_limit_seconds=2))
    assert result.solution
    report = validate_exported_csvs(tiny, scenario, scenario_csvs(result.solution))
    assert report.feasible
    assert result.diagnostics["objective"] == report.soft_scores["objective_score"]
    if strategy != "greedy":
        # Exhaustive single-activity oracle in test_regressions: 2 ECLO
        # accesses before week 3 give the optimum of 10 in both B and C.
        assert result.diagnostics["objective"] == 10
        assert result.diagnostics["global_lower_bound"] == 10
    if scenario == Scenario.B:
        assert all(r.overrun_days == 0 for r in result.solution.results)


@pytest.mark.parametrize("strategy", ["greedy", "integrated", "random_lns", "alns"])
def test_b_no_schedule_is_not_reported_as_zero_score(tiny, strategy):
    aid = next(iter(tiny.activities))
    impossible = replace(tiny, activities={aid: replace(tiny.activities[aid], total_accesses=10)})
    result = solve(impossible, Scenario.B, SearchConfig(strategy=strategy, time_limit_seconds=1))
    assert result.solution is None
    assert result.diagnostics["objective"] is None
    assert result.diagnostics["status"] == ("no_solution_within_budget" if strategy == "greedy" else "infeasible_for_policy")


def test_bc_cancel_keeps_csv_valid_incumbent(tiny):
    saved = []
    result = solve(tiny, Scenario.C, SearchConfig(strategy="alns", time_limit_seconds=2),
                   cancelled=lambda: bool(saved), checkpoint=lambda s, d: saved.append(s))
    assert result.diagnostics["status"] == "cancelled_with_feasible"
    assert result.solution.validation.feasible


def test_api_runs_all_scenarios_and_preserves_partial_results(tiny, monkeypatch):
    manager = JobManager()
    manager._executor.shutdown()
    manager._executor = SimpleNamespace(submit=lambda *args: None)
    monkeypatch.setattr(jobs, "parse_instance", lambda _: tiny)
    monkeypatch.setattr(api, "job_manager", manager)
    calls = []
    def run(inst, files, config, cancelled, on_update, scenario):
        calls.append((scenario, config["strategy"], config["time_limit_seconds"]))
        if scenario == Scenario.A:
            return SearchResult(None, {"status": "no_solution_within_budget"})
        result = solve(inst, scenario, SearchConfig(strategy="greedy", time_limit_seconds=1))
        on_update(result.solution, result.diagnostics)
        return result
    monkeypatch.setattr(worker, "run_worker", run)
    client = TestClient(app)
    created = client.post("/api/ps1/jobs?public=true&algorithm=strategies&strategy=random_lns&time_limit_seconds=5").json()
    assert set(created["scenarios"]) == {"A", "B", "C"}
    manager._run(created["job_id"])
    assert calls == [(s, "random_lns", 5) for s in Scenario]
    job = client.get(f"/api/ps1/jobs/{created['job_id']}").json()
    assert job["status"] == "failed"
    assert job["scenarios"]["A"]["objective_score"] is None
    for s in ("B", "C"):
        detail = client.get(f"/api/ps1/jobs/{created['job_id']}/scenarios/{s}").json()
        assert detail["validation"]["feasible"]
        assert detail["solution_revision"] == 1
        assert detail["activity_details"]
        assert detail["diagnostics"]["strategy"] == "greedy"
    assert client.get(f"/api/ps1/jobs/{created['job_id']}/download").status_code == 200


def test_cancelling_b_marks_c_cancelled_and_retains_b(tiny, monkeypatch):
    manager = JobManager()
    manager._executor.shutdown()
    manager._executor = SimpleNamespace(submit=lambda *args: None)
    monkeypatch.setattr(jobs, "parse_instance", lambda _: tiny)
    job = manager.create({}, "upload", "strategies", {"time_limit_seconds": 5})
    calls = []
    def run(inst, files, config, cancelled, on_update, scenario):
        calls.append(scenario)
        if scenario == Scenario.A: return SearchResult(None, {"status": "no_solution_within_budget"})
        result = solve(tiny, scenario, SearchConfig(strategy="greedy", time_limit_seconds=1))
        on_update(result.solution, result.diagnostics)
        manager.cancel(job.job_id)
        return result
    monkeypatch.setattr(worker, "run_worker", run)
    manager._run(job.job_id)
    assert calls == [Scenario.A, Scenario.B]
    assert job.status == JobStatus.CANCELLED
    assert job.scenarios[Scenario.B].solution.validation.feasible
    assert job.scenarios[Scenario.C].status == JobStatus.CANCELLED
