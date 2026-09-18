"""Reproducible stress probes. Time-limit failures are recorded, never hidden."""
import argparse
import json
import platform
import random
import sys
import time
from pathlib import Path
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.models import Scenario
from app.ps1.solver import solve_scenario, SolveFailure
from app.ps1.telemetry import peak_memory_mb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--output', type=Path, default=ROOT / 'submission/public-results/stress_benchmark.json')
    args = parser.parse_args()
    data = ROOT / 'PS1/01_data'
    base = parse_instance({n:(data/n).read_bytes() for n in EXPECTED_FILES})
    rng = random.Random(42)
    congested = replace(base, supply={k:replace(v,supply_capacity=max(0,v.supply_capacity-rng.choice((0,0,1)))) for k,v in base.supply.items()})
    scaled = replace(base, contracts={**base.contracts, **{k+'X':replace(v,contract_number=k+'X') for k,v in base.contracts.items()}},
                     activities={**base.activities, **{k+'X':replace(v,activity_id=k+'X',contract_number=v.contract_number+'X',predecessor_activity_id=v.predecessor_activity_id+'X' if v.predecessor_activity_id else None) for k,v in base.activities.items()}})
    report = {'seed':42,'workers':8,'platform':platform.platform(),'python':platform.python_version(),'seconds_per_scenario':args.seconds,'runs':[]}
    for name, instance in [('congested',congested),('double_demand',scaled)]:
        for scenario in Scenario:
            start=time.monotonic()
            try:
                solution=solve_scenario(instance,scenario,args.seconds,workers=8)
                row={'case':name,'scenario':scenario.value,'activities':len(instance.activities),'feasible':solution.validation.feasible,**solution.solver_stats}
            except SolveFailure as error:
                row={'case':name,'scenario':scenario.value,'activities':len(instance.activities),'feasible':False,'termination_reason':error.reason,'detail':str(error)}
            row.update(wall_seconds=time.monotonic()-start,process_peak_memory_mb=peak_memory_mb())
            report['runs'].append(row)
            print(json.dumps(row),flush=True)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
