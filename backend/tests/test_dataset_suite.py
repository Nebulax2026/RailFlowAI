import io
import json
import zipfile
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.api import ps1 as api
from app.ps1.benchmark import BenchmarkManager, SUITE, catalog
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.search import SearchConfig, SearchResult
from app.ps1.scenario_a.validation import validate_csvs
from app.ps1.scenario_a.worker import run_worker
from app.ps1.validator import OUTPUT_HEADERS, validate_exported_csvs
from app.ps1 import benchmark as benchmark_module


def test_all_30_inputs_and_historical_witness_audit_and_zips():
    entries = catalog()
    audit = json.loads((SUITE.parents[1] / "benchmarks/dataset-suite/current-validation.json").read_text())["cases"]
    assert len(entries) == 30
    assert {s: sum(r["scenario"] == s for r in entries) for s in "ABC"} == {"A": 10, "B": 10, "C": 10}
    assert {r["profile"]["name"] for r in entries} == {
        "small", "mixed", "priority_pressure", "interchange_congestion", "long_spans",
        "live_closures", "precedence_chains", "contract_contention", "compressed_horizon", "large_mixed"}
    for row in entries:
        folder = SUITE / row["input_path"]
        instance = parse_instance({n: (folder / n).read_bytes() for n in EXPECTED_FILES})
        files = {n: (folder.parent / "witness" / n).read_bytes() for n in OUTPUT_HEADERS}
        report = validate_exported_csvs(instance, Scenario(row["scenario"]), files)
        assert report.feasible == audit[row["case_id"]]["feasible"]
        assert report.hard_violations == audit[row["case_id"]]["hard_violations"]
        if not report.feasible:
            assert {v["rule"] for v in report.hard_violations} == {"closure"}
            assert "objective_score" not in report.soft_scores
        if row["scenario"] == "A": assert validate_csvs(instance, files).feasible
    assert sum(row["feasible"] for row in audit.values()) == 3
    with zipfile.ZipFile(SUITE / "all_30_inputs.zip") as archive:
        assert len(archive.namelist()) == 30 * 8
        assert len(set(archive.namelist())) == 240


def test_batch_average_counts_valid_zero_but_excludes_failed_and_pending(monkeypatch):
    manager = BenchmarkManager()
    manager._executor = SimpleNamespace(submit=lambda *args: None)
    created = manager.create("greedy", 5, 42, ["A01_small", "B01_small", "C01_small"])
    assert created["workers_per_case"] == 8
    assert [row["status"] for row in created["rows"]] == ["queued"] * 3
    scores = {"A": 0.0, "C": 25.2}
    def fake_run(instance, files, config, cancelled, on_update, scenario, legacy=False):
        assert config["workers"] == 8
        if scenario.value not in scores:
            return SearchResult(None, {"status": "no_solution_within_budget"})
        solution = SimpleNamespace(validation=SimpleNamespace(soft_scores={"objective_score": scores[scenario.value]}))
        on_update(solution, {})
        return SearchResult(solution, {"status": "feasible"})
    monkeypatch.setattr(benchmark_module, "run_worker", fake_run)
    manager._run(created["id"])
    finished = manager.get(created["id"])
    assert finished["status"] == "partial"
    assert [(s["scenario"], s["valid"], s["mean_score"]) for s in finished["summary"]] == [
        ("A", 1, 0.0), ("B", 0, None), ("C", 1, 25.2)]
    assert finished["summary"][1]["finished"] == 1
    assert finished["rows"][1]["status"] == "failed"


def test_batch_api_and_queued_cancellation(monkeypatch):
    manager = BenchmarkManager()
    manager._executor = SimpleNamespace(submit=lambda *args: None)
    monkeypatch.setattr(api, "benchmark_manager", manager)
    client = TestClient(app)
    assert client.get("/api/ps1/benchmark/datasets").json()["count"] == 30
    assert client.post("/api/ps1/benchmark/runs?method=unknown").status_code == 422
    created = client.post("/api/ps1/benchmark/runs?method=all&time_limit_seconds=5").json()
    assert len(created["rows"]) == 150
    assert len(created["summary"]) == 15
    assert client.get(f"/api/ps1/benchmark/runs/{created['id']}").status_code == 200
    cancelled = client.delete(f"/api/ps1/benchmark/runs/{created['id']}").json()
    assert cancelled["status"] == "cancelled"
    assert all(row["status"] == "cancelled" for row in cancelled["rows"])
    assert client.get(f"/api/ps1/benchmark/runs/{created['id']}/report").status_code == 200
    response = client.get("/api/ps1/benchmark/datasets/download/A")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 80


def test_existing_planner_uses_bounded_worker_and_main_validator():
    entry = catalog()[0]
    folder = SUITE / entry["input_path"]
    files = {n: (folder / n).read_bytes() for n in EXPECTED_FILES}
    instance = parse_instance(files)
    result = run_worker(instance, files, vars(SearchConfig(strategy="integrated", time_limit_seconds=5, workers=1)),
                        lambda: False, lambda *_: None, Scenario.A, legacy=True)
    assert result.solution and result.solution.validation.feasible
    assert result.diagnostics["strategy"] == "legacy"
    assert result.diagnostics["config"]["workers"] == 1
