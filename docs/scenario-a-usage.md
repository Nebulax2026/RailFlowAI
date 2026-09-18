# Using the separate Scenario A optimizer

Run `npm run dev` at the repository root and open http://localhost:3000. Choose
Existing planner or one of the four other methods from the same selector; see
[current UI instructions](strategy-comparison.md). The A-only API and CLI
described below remain available.

An `algorithm=scenario_a` API run includes only A. Its default is **ALNS, 15 seconds, seed 42**, selected using the two-seed public tuning experiment. Integrated CP-SAT remains selectable; the library/CLI without a configuration file defaults to that reference model. The run reports the best independently validated cost, full-model lower bound, absolute gap and time to first feasible. A valid incumbent becomes downloadable while search continues. **Stop search** preserves it. The ZIP contains only `scenario_A/` CSVs plus validation; the separate **Search report** contains configurations, timings, bounds, trajectory and operator statistics. Bounds and validation refer to the documented safety policy, not an unavailable official validator.

Python 3.11+ (tested with 3.12.14), OR-Tools 9.15.6755 and the pinned `backend/requirements.txt` are required. Workers default to `"auto"` in JSON and `--workers auto` in the CLI. At solve time, available logical CPUs select 1 worker for up to 2 CPUs, 2 for up to 4, 4 for up to 8, and 8 above that. Detection considers process CPU count/affinity where available and Linux cgroup v1/v2 quotas, including visible parent quotas. Unknown CPU counts fall back to 1. This is a conservative starting policy, not a guarantee of optimal performance or memory availability. Explicit integers 1–8 override detection; benchmarks use 8 workers. Diagnostics record the resolved integer in `config.workers`. Wall-clock limits can still produce different stopping points under machine load, even with one worker.

```sh
# From the repository root; choose a new output directory per invocation.
cd backend
.venv/bin/python -m app.ps1.scenario_a.cli \
  --input ../PS1/01_data --output ../submission/my-scenario-a-run \
  --config ../config/scenario-a.json --seconds 30 --workers 1 --seed 42

# Explicit ALNS experiment using the same integrated hard constraints.
.venv/bin/python -m app.ps1.scenario_a.cli \
  --input ../PS1/01_data --output ../submission/my-alns-run \
  --strategy alns --seconds 30 --workers 1 --seed 42
```

Each output directory includes the three official-schema CSVs, `validation.json`, `diagnostics.json`, and atomic incumbent checkpoints. No debugging columns are added to CSVs. On interruption, `checkpoint.json` points to the last complete validated generation. The API runs new searches in a separate process and validates these files again before exposing them.

API example:

```sh
curl -X POST 'http://127.0.0.1:8000/api/ps1/jobs?public=true&algorithm=scenario_a&strategy=integrated&time_limit_seconds=30&seed=42'
```

Omitting `algorithm` retains the original API behavior. Use `algorithm=strategies` to run all three scenarios with the selected method. The UI/API allow 5–120 seconds (UI presets start at 15); CLI allows 0.2–600 seconds. Uploaded inputs for the new worker are stored in a temporary directory only for that run and removed afterwards; results remain in the existing in-memory job lifetime.

## Reproduce the comparison

```sh
# The committed verified witness generates known-feasible variants;
# it is never supplied as an optimization hint in the benchmark.
backend/.venv/bin/python scripts/benchmark_scenario_a.py \
  --output benchmarks/scenario-a/reproduction \
  --witness submission/scenario-a-tuning-integrated \
  --seeds 11,29 --budgets 5,15
```

The raw JSONL and per-run diagnostics preserve configurations, versions, trajectories and bounds. `comparison.md` reports feasible rates, median and worst feasible costs, gaps, first-feasible time, memory and wall time. The public case is the tuning set. Two heldout variants preserve a known complete feasible schedule (changed target dates/priorities and tightened release dates); a separate case provably exceeds the fixed workload horizon. The selection uses only the public tuning set, with integrated CP-SAT preferred on ties. A 2-seed experiment is limited evidence; it does not establish general superiority.

Initialization can be compared separately using `--cases public --strategies integrated --initialization direct` or `--initialization feasibility`, with the same budgets/seeds and a fresh output path.

See [rule evidence and unresolved semantics](scenario-a-rules.md). The legacy score and the new score should not be compared as if they used the same hard-constraint checker.
