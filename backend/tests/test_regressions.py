import csv
import io
import itertools
import threading
from dataclasses import replace
from datetime import timedelta
from collections import Counter
import pytest
from .test_ps1 import instance, DATA
from app.ps1.models import AccessAssignment, OccupancyAssignment, ContractResult, Scenario, ScenarioSolution
from app.ps1.parser import parse_instance, EXPECTED_FILES, InstanceValidationError
from app.ps1.solver import solve_scenario, SolveFailure
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import validate_solution, validate_exported_csvs
from app.ps1.exporter import scenario_csvs, solutions_zip
from app.ps1.scoring import week_end


@pytest.fixture
def tiny(instance):
    a = instance.activities['A001']; c = instance.contracts[a.contract_number]
    c = replace(c, nature_of_activity='Non-live (Others)', access_type='C', contract_priority=2,
                planned_completion_date=week_end(instance, 2), number_of_workfronts=2)
    a = replace(a, total_accesses=3, planned_start_date=instance.horizon_start, predecessor_activity_id=None, activity_priority=1)
    return replace(instance, horizon_weeks=4, contracts={c.contract_number:c}, activities={a.activity_id:a},
                   supply={k:replace(v,supply_capacity=4) for k,v in instance.supply.items()})


def manual(i, scenario, placements, group='g'):
    access=[]; occupancy=[]; seq=Counter()
    for aid,week,eclo in placements:
        seq[aid]+=1; access.append(AccessAssignment(aid,seq[aid],week,eclo,1))
        occupancy.extend(OccupancyAssignment(aid,week,loc,group) for loc in activity_locations(i,i.activities[aid]))
    results=[]
    for cid,c in i.contracts.items():
        weeks=[r.week for r in access if i.activities[r.activity_id].contract_number==cid]
        if weeks:
            end=week_end(i,max(weeks));results.append(ContractResult(scenario.value,cid,end,max(0,(end-c.planned_completion_date).days)))
    s=ScenarioSolution(scenario,access,occupancy,results,None)
    s.validation=validate_exported_csvs(i,scenario,scenario_csvs(s))
    return s


@pytest.mark.parametrize('mutation,tag', [('dates','results'),('unknown','activity'),('sequence','access_seq'),('eclo','eclo'),('duplicate','weekly_activity'),('occupancy','occupancy'),('result_duplicate','results')])
def test_export_mutations(tiny,mutation,tag):
    aid=next(iter(tiny.activities));s=manual(tiny,Scenario.B,[(aid,1,1),(aid,2,1)])
    assert s.validation.feasible
    if mutation=='dates': s.results=[replace(s.results[0],simulated_completion_date=tiny.horizon_start,overrun_days=0)]
    if mutation=='unknown': s.accesses[0]=replace(s.accesses[0],activity_id='UNKNOWN')
    if mutation=='sequence': s.accesses[0]=replace(s.accesses[0],access_seq=-99)
    if mutation=='eclo': s.accesses[0]=replace(s.accesses[0],eclo=2)
    if mutation=='duplicate': s.accesses.append(s.accesses[0])
    if mutation=='occupancy': s.occupancy.append(s.occupancy[0])
    if mutation=='result_duplicate': s.results.append(s.results[0])
    r=validate_exported_csvs(tiny,Scenario.B,scenario_csvs(s))
    assert not r.feasible and tag in {v['rule'] for v in r.hard_violations}
    assert 'objective_score' not in r.soft_scores and 'formula_version' not in r.soft_scores


def test_b_uses_actual_dates(tiny):
    aid=next(iter(tiny.activities));s=manual(tiny,Scenario.B,[(aid,1,0),(aid,2,0),(aid,3,0)])
    s.results=[replace(r,overrun_days=0) for r in s.results]
    r=validate_exported_csvs(tiny,Scenario.B,scenario_csvs(s))
    assert {'planned_date','results'} <= {v['rule'] for v in r.hard_violations}


@pytest.mark.parametrize('kind,count,valid',[('PM',2,False),('PC',2,False),('C',5,False),('C',4,True)])
def test_group_mix(tiny,kind,count,valid):
    a=next(iter(tiny.activities.values()));c=next(iter(tiny.contracts.values()))
    i=replace(tiny,contracts={c.contract_number:replace(c,access_type=kind,number_of_workfronts=5)},
              activities={str(n):replace(a,activity_id=str(n),total_accesses=1) for n in range(count)})
    r=manual(i,Scenario.A,[(aid,1,0) for aid in i.activities]).validation
    assert ('legal_mix' not in {v['rule'] for v in r.hard_violations})==valid


def test_surplus_yield_is_legal(tiny):
    aid=next(iter(tiny.activities));i=replace(tiny,activities={aid:replace(tiny.activities[aid],total_accesses=2)})
    assert manual(i,Scenario.B,[(aid,1,1),(aid,2,0)]).validation.feasible


def test_predecessor_eclo_compression(tiny):
    a=next(iter(tiny.activities.values()));c=next(iter(tiny.contracts.values()))
    b=replace(a,activity_id='SUCCESSOR',predecessor_activity_id=a.activity_id)
    i=replace(tiny,activities={a.activity_id:a,b.activity_id:b},contracts={c.contract_number:replace(c,planned_completion_date=week_end(tiny,4))})
    s=solve_scenario(i,Scenario.B,3)
    assert s.validation.feasible
    assert sum(r.eclo for r in s.accesses)==4
    assert max(r.week for r in s.accesses if r.activity_id==a.activity_id)<min(r.week for r in s.accesses if r.activity_id==b.activity_id)


@pytest.mark.parametrize('scenario',list(Scenario))
def test_small_optimum_matches_independent_enumeration(tiny,scenario):
    # Enumerate no access / standard / ECLO for four weeks; single activity,
    # ample capacity, priority 2/activity 1 -> 13 per calendar day late.
    scores=[]
    for choices in itertools.product((0,2,3),repeat=4):
        if sum(choices)<6 or (scenario==Scenario.A and 3 in choices):continue
        weeks=[n+1 for n,v in enumerate(choices) if v];eweeks=[n+1 for n,v in enumerate(choices) if v==3]
        if scenario==Scenario.B and max(weeks)>2:continue
        if scenario==Scenario.C and eweeks and max(eweeks)-min(eweeks)>1:continue
        scores.append((0 if scenario==Scenario.B else 13*max(0,(max(weeks)-2)*7))+(0 if scenario==Scenario.A else 5*len(eweeks)))
    s=solve_scenario(tiny,scenario,3)
    assert s.validation.soft_scores['objective_score']==min(scores)
    assert s.solver_stats['best_score']==min(scores)
    assert s.solver_stats['optimal']
    if scenario==Scenario.C:assert sum(r.eclo for r in s.accesses)==2


def test_c_window_and_b_exemption(tiny):
    aid=next(iter(tiny.activities));cid=next(iter(tiny.contracts))
    i=replace(tiny,contracts={cid:replace(tiny.contracts[cid],planned_completion_date=week_end(tiny,4))})
    assert not manual(i,Scenario.C,[(aid,1,1),(aid,3,1)]).validation.feasible
    assert manual(i,Scenario.C,[(aid,2,1),(aid,3,1)]).validation.feasible
    assert manual(i,Scenario.B,[(aid,1,1),(aid,3,1)]).validation.feasible


def test_midweek_deadline_and_cancellation(tiny):
    aid=next(iter(tiny.activities));cid=next(iter(tiny.contracts))
    i=replace(tiny,activities={aid:replace(tiny.activities[aid],total_accesses=1)},
              contracts={cid:replace(tiny.contracts[cid],planned_completion_date=tiny.horizon_start+timedelta(days=2))})
    with pytest.raises(SolveFailure) as caught:solve_scenario(i,Scenario.B,1)
    assert caught.value.reason=='infeasible'
    event=threading.Event();event.set()
    with pytest.raises(SolveFailure) as caught:solve_scenario(tiny,Scenario.C,1,cancel_event=event)
    assert caught.value.reason=='cancelled'


def test_buffer_boundary_and_mirroring(instance):
    a=instance.activities['A001'];cid=a.contract_number
    a=replace(a,start_location_id='SEC:ALP:S01_S02:EB',end_location_id='SEC:ALP:S01_S02:EB')
    i=replace(instance,contracts={**instance.contracts,cid:replace(instance.contracts[cid],nature_of_activity='Live')})
    protected=closure_locations(i,a)
    assert {'SEC:ALP:S02_S03:EB','SEC:ALP:S03_S04:EB','PLAT:ALP:S04:EB','SEC:ALP:S01_S02:WB','PLAT:ALP:S01:WB'}<=protected
    assert 'SEC:ALP:S04_H01:EB' not in protected
    assert not any(':BET:' in loc for loc in protected)


def test_protection_reservations_and_sharing(tiny):
    a=next(iter(tiny.activities.values()));c=next(iter(tiny.contracts.values()))
    a=replace(a,total_accesses=1);b=replace(a,activity_id='B')
    i=replace(tiny,activities={a.activity_id:a,'B':b},contracts={c.contract_number:replace(c,nature_of_activity='Non-live (Consist)')},supply={k:replace(v,supply_capacity=1) for k,v in tiny.supply.items()})
    shared=manual(i,Scenario.A,[(a.activity_id,1,0),('B',1,0)])
    assert shared.validation.feasible
    shared.occupancy=[replace(r,co_share_group=r.activity_id) for r in shared.occupancy]
    r=validate_exported_csvs(i,Scenario.A,scenario_csvs(shared))
    assert 'closure' in {v['rule'] for v in r.hard_violations}
    assert manual(i,Scenario.A,[(a.activity_id,1,0),('B',2,0)]).validation.feasible


@pytest.mark.parametrize('mode',['short_row','invalid_flag','duplicate_parameter','bad_date','disconnected'])
def test_input_diagnostics(mode):
    files={n:(DATA/n).read_bytes() for n in EXPECTED_FILES}
    if mode=='short_row':files['01_LINES.csv']+=b'X\n'
    if mode=='invalid_flag':files['02_STATIONS.csv']=files['02_STATIONS.csv'].replace(b'S01,ALP,1,0',b'S01,ALP,1,perhaps')
    if mode=='duplicate_parameter':files['06_PARAMETERS.csv']+=b'horizon_weeks,30\n'
    if mode=='bad_date':files['08_ACTIVITY_DETAILS.csv']=files['08_ACTIVITY_DETAILS.csv'].replace(b'2027-05-24',b'not-a-date')
    if mode=='disconnected':files['03_SECTORS.csv']=files['03_SECTORS.csv'].replace(b',ALP,S01,S02,',b',ALP,S01,S03,')
    with pytest.raises(InstanceValidationError) as caught:parse_instance(files)
    assert '.csv' in str(caught.value)


@pytest.mark.parametrize('payload',[b'\xff',b'wrong\n',b'activity_id,access_seq,week,eclo,access_night\nA,1\n'])
def test_malformed_exports_never_crash(tiny,payload):
    aid=next(iter(tiny.activities));s=manual(tiny,Scenario.B,[(aid,1,1),(aid,2,1)]);files=scenario_csvs(s);files['SCHEDULE_ACCESS.csv']=payload
    assert not validate_exported_csvs(tiny,Scenario.B,files).feasible


def test_extreme_invalid_week_never_crashes(tiny):
    aid=next(iter(tiny.activities));s=manual(tiny,Scenario.B,[(aid,1,1),(aid,2,1)])
    s.accesses[0]=replace(s.accesses[0],week=10**100)
    r=validate_exported_csvs(tiny,Scenario.B,scenario_csvs(s))
    assert not r.feasible and 'horizon' in {v['rule'] for v in r.hard_violations}


def test_live_cross_line_eclo_windows(tiny):
    a=next(iter(tiny.activities.values()));c=next(iter(tiny.contracts.values()))
    a=replace(a,activity_id='LIVE',total_accesses=3,start_location_id='SEC:ALP:H01_H02:EB',end_location_id='SEC:ALP:H01_H02:EB')
    b=replace(a,activity_id='BETA',contract_number='OTHER',total_accesses=1,start_location_id='SEC:BET:S11_S12:EB',end_location_id='SEC:BET:S11_S12:EB')
    i=replace(tiny,activities={'LIVE':a,'BETA':b},contracts={c.contract_number:replace(c,nature_of_activity='Live'), 'OTHER':replace(c,contract_number='OTHER')})
    r=manual(i,Scenario.C,[('LIVE',1,1),('LIVE',2,1),('BETA',4,1)]).validation
    assert any(v['rule']=='eclo_continuity' and 'BET' in v['detail'] for v in r.hard_violations)


def test_buffer_work_collision_and_separate_local_possessions(tiny):
    a=next(iter(tiny.activities.values()));c=next(iter(tiny.contracts.values()))
    a=replace(a,activity_id='LEFT',total_accesses=1,start_location_id='SEC:ALP:S01_S02:EB',end_location_id='SEC:ALP:S01_S02:EB')
    b=replace(a,activity_id='RIGHT',start_location_id='SEC:ALP:S03_S04:EB',end_location_id='SEC:ALP:S03_S04:EB')
    i=replace(tiny,activities={'LEFT':a,'RIGHT':b},contracts={c.contract_number:replace(c,nature_of_activity='Non-live (Consist)')},supply={k:replace(v,supply_capacity=1) for k,v in tiny.supply.items()})
    r=manual(i,Scenario.A,[('LEFT',1,0),('RIGHT',1,0)]).validation
    assert any(v['rule']=='closure' and 'S02_S03' in v['detail'] for v in r.hard_violations)
    roomy=replace(i,supply={k:replace(v,supply_capacity=2) for k,v in i.supply.items()})
    assert manual(roomy,Scenario.A,[('LEFT',1,0),('RIGHT',1,0)]).validation.feasible


def test_workfront_is_independent_of_location(tiny):
    a=next(iter(tiny.activities.values()));c=next(iter(tiny.contracts.values()))
    a=replace(a,total_accesses=1);b=replace(a,activity_id='B')
    i=replace(tiny,activities={a.activity_id:a,'B':b},contracts={c.contract_number:replace(c,number_of_workfronts=1)})
    s=manual(i,Scenario.A,[(a.activity_id,1,0),('B',1,0)])
    assert 'workfront' in {v['rule'] for v in s.validation.hard_violations}
    s.accesses[1]=replace(s.accesses[1],access_night=2)
    assert validate_exported_csvs(i,Scenario.A,scenario_csvs(s)).feasible


def test_non_live_never_crosses_interchange(tiny):
    a=next(iter(tiny.activities.values()))
    a=replace(a,start_location_id='SEC:ALP:H01_H02:EB',end_location_id='SEC:ALP:H01_H02:EB')
    assert not any(':BET:' in loc for loc in closure_locations(tiny,a))
