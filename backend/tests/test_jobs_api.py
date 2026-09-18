import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from .test_regressions import tiny, manual
from .test_ps1 import instance
from app.main import app
from app.ps1.models import Scenario, JobStatus, ScenarioRun, SolveJob
from app.ps1.jobs import JobManager
from app.ps1.solver import SolveFailure
from app.ps1.exporter import solutions_zip
from app.api import ps1 as api
from app.ps1 import jobs


@pytest.fixture
def manager(tiny,monkeypatch):
    manager=JobManager(first_seconds=1,improve_seconds=1)
    manager._executor.shutdown()
    manager._executor=SimpleNamespace(submit=lambda *args:None)
    monkeypatch.setattr(jobs,'parse_instance',lambda _:tiny)
    return manager


def fake_solution(tiny,scenario,week=2):
    aid=next(iter(tiny.activities));i=replace(tiny,activities={aid:replace(tiny.activities[aid],total_accesses=1)})
    s=manual(i,scenario,[(aid,week,0)])
    s.solver_stats={'termination_reason':'time_limit','optimal':False,'elapsed_seconds':0.01,'first_feasible_seconds':0.001}
    return i,s


def test_sequential_search_streams_revisions_without_restarting(manager,tiny,monkeypatch):
    i,_=fake_solution(tiny,Scenario.A)
    monkeypatch.setattr(jobs,'parse_instance',lambda _:i)
    calls=[]
    def solve(inst,scenario,budget,**kwargs):
        calls.append((scenario.value,budget))
        assert budget == 2
        assert kwargs['optimize_early_placement'] is False
        # Multiple revisions arrive during one uninterrupted solve.
        if scenario != Scenario.B:
            _,initial=fake_solution(tiny,scenario,3)
            kwargs['on_solution'](initial)
            assert job.scenarios[scenario].phase == 'improving'
        _,s=fake_solution(tiny,scenario,1)
        kwargs['on_solution'](s)
        return s
    monkeypatch.setattr(jobs,'solve_scenario',solve)
    job=manager.create({},'upload');manager._run(job.job_id)
    assert [s for s,b in calls]==['A','B','C']
    assert job.status==JobStatus.COMPLETED
    assert job.scenarios[Scenario.A].solution.solution_revision==2
    assert job.scenarios[Scenario.B].solution.solution_revision==1
    for run in job.scenarios.values():assert run.solution.validation.feasible


def test_timeout_moves_to_next_scenario_without_restart(manager,tiny,monkeypatch):
    i,_=fake_solution(tiny,Scenario.A)
    monkeypatch.setattr(jobs,'parse_instance',lambda _:i)
    calls=[]
    def solve(inst,scenario,budget,**kwargs):
        calls.append(scenario)
        if scenario == Scenario.A:
            assert job.scenarios[Scenario.B].status == JobStatus.QUEUED
            raise SolveFailure('time_limit', 'No complete schedule within budget')
        _,s=fake_solution(tiny,scenario,1)
        return s
    monkeypatch.setattr(jobs,'solve_scenario',solve)
    job=manager.create({},'upload');manager._run(job.job_id)
    assert calls == list(Scenario)
    assert job.scenarios[Scenario.A].phase == 'finished'
    assert job.scenarios[Scenario.A].termination_reason == 'time_limit'
    assert job.scenarios[Scenario.B].solution and job.scenarios[Scenario.C].solution


def test_partial_failure_and_expiry(manager,tiny,monkeypatch):
    i,_=fake_solution(tiny,Scenario.A);monkeypatch.setattr(jobs,'parse_instance',lambda _:i)
    def solve(inst,scenario,budget,**kwargs):
        if scenario==Scenario.B:raise SolveFailure('infeasible','Deliberate B failure')
        _,s=fake_solution(tiny,scenario);s.solver_stats['termination_reason']='optimal';s.solver_stats['optimal']=True;return s
    monkeypatch.setattr(jobs,'solve_scenario',solve)
    job=manager.create({},'upload');manager._run(job.job_id)
    assert job.status==JobStatus.FAILED
    assert job.scenarios[Scenario.A].solution and job.scenarios[Scenario.C].solution
    job.expires_at=datetime.now(UTC)-timedelta(seconds=1)
    assert manager.get(job.job_id) is None


def test_cancel_retains_validated_result(manager,tiny,monkeypatch):
    i,_=fake_solution(tiny,Scenario.A);monkeypatch.setattr(jobs,'parse_instance',lambda _:i)
    job=manager.create({},'upload')
    def solve(inst,scenario,budget,**kwargs):
        _,s=fake_solution(tiny,scenario);kwargs['on_solution'](s)
        manager.cancel(job.job_id)
        assert kwargs['cancel_event'].is_set()
        return s
    monkeypatch.setattr(jobs,'solve_scenario',solve);manager._run(job.job_id)
    assert job.status==JobStatus.CANCELLED
    assert job.scenarios[Scenario.A].solution.validation.feasible
    assert job.scenarios[Scenario.B].termination_reason=='cancelled'


def test_api_evidence_and_revision_download(manager,tiny,monkeypatch):
    i,s=fake_solution(tiny,Scenario.A);s.solution_revision=3
    monkeypatch.setattr(jobs,'parse_instance',lambda _:i)
    job=manager.create({},'upload');run=job.scenarios[Scenario.A]
    run.solution=s;run.status=JobStatus.RUNNING;run.phase='improving'
    monkeypatch.setattr(api,'job_manager',manager)
    client=TestClient(app)
    detail=client.get(f'/api/ps1/jobs/{job.job_id}/scenarios/A').json()
    assert detail['solution_revision']==3 and detail['activity_details'][0]['delivered_workload']==1
    witness = s.validation.detail['physical_night_assignment']
    assert detail['activity_details'][0]['accesses'][0]['physical_night'] == witness[0]['physical_night']
    assert detail['score_breakdown']=={'delay':0,'excess_supply':0,'eclo':0}
    path=f'/api/ps1/jobs/{job.job_id}/scenarios/A/files/RESULTS.csv'
    assert client.get(path+'?revision=2').status_code==409
    assert client.get(path+'?revision=3').status_code==200
    response=client.get(f'/api/ps1/jobs/{job.job_id}/download')
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert json.loads(z.read('manifest.json'))=={'included_scenarios':['A'],'revisions':{'A':3}}
        assert 'scenario_A/RESULTS.csv' in z.namelist()
    manager.cancel(job.job_id)
    assert client.get(path+'?revision=3').status_code==200


def test_invalid_candidate_cannot_replace_valid_one(manager,tiny,monkeypatch):
    i,s=fake_solution(tiny,Scenario.A);monkeypatch.setattr(jobs,'parse_instance',lambda _:i)
    job=manager.create({},'upload');manager._publish(job,Scenario.A,s)
    bad=replace(s,results=[replace(s.results[0],overrun_days=99)])
    with pytest.raises(SolveFailure):manager._publish(job,Scenario.A,bad)
    assert job.scenarios[Scenario.A].solution is s
