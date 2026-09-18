from dataclasses import replace
from datetime import UTC, datetime, timedelta
import threading
import time

import pytest
from fastapi.testclient import TestClient

from .test_regressions import tiny
from .test_ps1 import instance
from app.ps1.assistant import answer_question
from app.main import app
from app.ps1.jobs import job_manager
from app.ps1.models import Disruption, JobStatus, Scenario, ScenarioRun, SolveJob
from app.ps1.replanning import audit_disruption, solution_diff
from app.ps1.solver import solve_scenario
from app.ps1.topology import activity_locations


@pytest.mark.parametrize("scenario", list(Scenario))
def test_disruption_is_a_hard_cap_for_every_policy(tiny, scenario):
    aid = next(iter(tiny.activities))
    instance = replace(tiny, activities={aid: replace(tiny.activities[aid], total_accesses=1)})
    baseline = solve_scenario(instance, scenario, 3)
    location = activity_locations(instance, instance.activities[aid])[0]
    disruption = Disruption(location, 1, 1, 0, "urgent_maintenance")
    revised = solve_scenario(instance, scenario, 3, incumbent=baseline, disruption=disruption)
    audit = audit_disruption(instance, revised, disruption)
    assert revised.validation.feasible
    assert audit["feasible"]
    assert not any(row.activity_id == aid and row.week == 1 for row in revised.accesses)


def test_replan_freezes_past_and_reports_diff(tiny):
    baseline = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities)); location = activity_locations(tiny, tiny.activities[aid])[0]
    disruption = Disruption(location, 2, 2, 0, "defect")
    revised = solve_scenario(tiny, Scenario.A, 3, incumbent=baseline, disruption=disruption)
    old_past = [(r.activity_id, r.week, r.eclo, r.access_night) for r in baseline.accesses if r.week < 2]
    new_past = [(r.activity_id, r.week, r.eclo, r.access_night) for r in revised.accesses if r.week < 2]
    assert old_past == new_past
    diff = solution_diff(tiny, baseline, revised, disruption)
    assert diff["summary"]["moved_activities"] >= 1
    assert diff["activity_changes"][0]["reason"] == "direct_disruption"


def test_schedule_assistant_intents(tiny):
    solution = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities)); location = activity_locations(tiny, tiny.activities[aid])[0]
    questions = [
        (f"What is the downstream risk from {aid}?", "downstream_risk"),
        (f"Capacity at {location} week 1", "capacity_status"),
        (f"Who co-shares with {aid}?", "co_share_status"),
        ("Handover brief for week 1", "handover_brief"),
    ]
    for question, intent in questions:
        response = answer_question(tiny, solution, question)
        assert response["intent"] == intent
        assert response["answer"]


def test_move_reason_is_grounded_in_replan_diff(tiny):
    baseline = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities)); location = activity_locations(tiny, tiny.activities[aid])[0]
    disruption = Disruption(location, 2, 2, 0, "defect")
    revised = solve_scenario(tiny, Scenario.A, 3, incumbent=baseline, disruption=disruption)
    diff = solution_diff(tiny, baseline, revised, disruption)
    response = answer_question(tiny, revised, f"Why was {aid} moved?", diff)
    assert response["intent"] == "activity_move_reason"
    assert aid in response["evidence"]


def test_assistant_new_intents_are_deterministic_and_grounded(tiny, monkeypatch):
    monkeypatch.setattr("app.ps1.assistant._parse_with_gemini", lambda q: (None, "deterministic"))
    baseline = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities)); location = activity_locations(tiny, tiny.activities[aid])[0]
    revised = solve_scenario(tiny, Scenario.A, 3, incumbent=baseline,
                             disruption=Disruption(location, 2, 2, 0, "defect"))
    diff = solution_diff(tiny, baseline, revised, Disruption(location, 2, 2, 0, "defect"))
    contract = tiny.activities[aid].contract_number
    scenarios = {Scenario.A: ScenarioRun(status=JobStatus.COMPLETED, solution=baseline),
                 Scenario.B: ScenarioRun(), Scenario.C: ScenarioRun()}
    checks = [
        ("Compare scenarios A, B and C", "scenario_comparison", baseline, None),
        (f"What is the milestone risk for {contract}?", "milestone_risk", baseline, None),
        ("What changed in this replan?", "replan_impact_summary", revised, diff),
        (f"Reduce {location} capacity to 0 in week 2", "disruption_preview", baseline, None),
    ]
    for question, intent, solution, candidate_diff in checks:
        response = answer_question(tiny, solution, question, candidate_diff, scenarios)
        assert response["intent"] == intent
        assert response["mode"] == "deterministic"
        assert response["evidence"]
        assert response.get("data") is not None


def test_replan_preview_is_non_mutating_single_use_and_bound_to_baseline(tiny, monkeypatch):
    aid = next(iter(tiny.activities))
    instance = replace(tiny, activities={aid: replace(tiny.activities[aid], total_accesses=1)})
    baseline = solve_scenario(instance, Scenario.A, 3); baseline.solution_revision = 1
    run = ScenarioRun(status=JobStatus.COMPLETED, progress=100, solution=baseline, phase="finished")
    now = datetime.now(UTC); job_id = "assistant-preview-test"
    job = SolveJob(job_id, JobStatus.COMPLETED, now, now + timedelta(minutes=5), "test", instance,
                   {Scenario.A: run, Scenario.B: ScenarioRun(), Scenario.C: ScenarioRun()})
    location = activity_locations(instance, instance.activities[aid])[0]
    with job_manager._lock:
        job_manager._jobs[job_id] = job; job_manager._events[job_id] = threading.Event()
    client = TestClient(app)
    try:
        body = {"location_id": location, "start_week": 1, "end_week": 1, "capacity": 0, "reason": "defect"}
        invalid = client.post(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/preview", json={**body, "end_week": 999})
        assert invalid.status_code == 422
        preview = client.post(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/preview", json=body)
        assert preview.status_code == 200
        assert job.replans == {}
        preview_id = preview.json()["preview_id"]
        from app.api import ps1
        observed = {}
        def fake_chat(*args, **kwargs):
            observed.update(kwargs)
            return {"answer": "Approval confirmed", "approved_preview_id": kwargs["pending_preview"]["preview_id"]}
        monkeypatch.setattr("app.ps1.assistant.chat", fake_chat)
        approval = client.post(f"/api/ps1/jobs/{job_id}/assistant/query", json={
            "scenario": "A", "question": "approve", "pending_preview_id": preview_id})
        assert approval.status_code == 200
        assert observed["pending_preview"]["disruption"] == body
        assert job.replans == {}
        baseline.solution_revision += 1
        stale = client.post(f"/api/ps1/jobs/{job_id}/assistant/query", json={
            "scenario": "A", "question": "approve", "pending_preview_id": preview_id})
        assert stale.status_code == 409
        baseline.solution_revision -= 1
        ps1._replan_previews[preview_id]["expires_at"] = 0
        expired = client.post(f"/api/ps1/jobs/{job_id}/assistant/query", json={
            "scenario": "A", "question": "approve", "pending_preview_id": preview_id})
        assert expired.status_code == 409
        wrong = client.post(f"/api/ps1/jobs/{job_id}/scenarios/B/replans/execute", json={"preview_id": preview_id})
        assert wrong.status_code == 409
        assert job.replans == {}
        fresh = client.post(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/preview", json=body).json()["preview_id"]
        started = client.post(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/execute", json={"preview_id": fresh})
        assert started.status_code == 202
        assert len(job.replans) == 1
        reused = client.post(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/execute", json={"preview_id": fresh})
        assert reused.status_code == 409
    finally:
        with job_manager._lock:
            job_manager._events.pop(job_id, None); job_manager._jobs.pop(job_id, None)


def test_replan_api_download_and_assistant(tiny, monkeypatch):
    def fake_chat(job, scenario, solution, question, history, diff):
        assert scenario is None and solution is None
        return {"answer": "Model answer over all scenarios", "intent": "conversation", "mode": "gemini", "evidence": []}
    monkeypatch.setattr("app.ps1.assistant.chat", fake_chat)
    aid = next(iter(tiny.activities))
    instance = replace(tiny, activities={aid: replace(tiny.activities[aid], total_accesses=1)})
    baseline = solve_scenario(instance, Scenario.A, 3); baseline.solution_revision = 1
    run = ScenarioRun(status=JobStatus.COMPLETED, progress=100, solution=baseline, phase="finished")
    now = datetime.now(UTC); job_id = "bonus-api-test"
    job = SolveJob(job_id, JobStatus.COMPLETED, now, now + timedelta(minutes=5), "test", instance,
                   {Scenario.A: run, Scenario.B: ScenarioRun(), Scenario.C: ScenarioRun()})
    location = activity_locations(instance, instance.activities[aid])[0]
    with job_manager._lock:
        job_manager._jobs[job_id] = job; job_manager._events[job_id] = threading.Event()
    client = TestClient(app)
    try:
        response = client.post(f"/api/ps1/jobs/{job_id}/scenarios/A/replans", json={
            "location_id": location, "start_week": 1, "end_week": 1,
            "capacity": 0, "reason": "urgent_maintenance",
        })
        assert response.status_code == 202
        replan_id = response.json()["replan_id"]
        payload = None
        for _ in range(50):
            payload = client.get(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/{replan_id}").json()
            if payload["status"] in {"completed", "failed"}: break
            time.sleep(0.05)
        assert payload["status"] == "completed"
        assert payload["disruption_audit"]["feasible"]
        download = client.get(f"/api/ps1/jobs/{job_id}/scenarios/A/replans/{replan_id}/files/RESULTS.csv")
        assert download.status_code == 200
        answer = client.post(f"/api/ps1/jobs/{job_id}/assistant/query", json={"question": "Compare all scenarios."})
        assert answer.status_code == 200
        assert answer.json()["mode"] == "gemini"
    finally:
        with job_manager._lock:
            job_manager._events.pop(job_id, None); job_manager._jobs.pop(job_id, None)
