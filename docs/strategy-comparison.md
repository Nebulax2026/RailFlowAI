# Three selectable search methods, three scenarios

Start `npm run dev`, open http://localhost:3000, choose a **Search method**
(including Existing planner), then click **Load public dataset** or upload the
eight CSV files and click **Run A, B and C**.

Each of Integrated CP-SAT, Random LNS and Adaptive LNS runs A, B and C
sequentially. **Time per scenario** applies separately: 15 seconds means up
to about 45 seconds of search for the job, plus worker startup/export overhead.
One active subprocess keeps the three scenarios sequential. Solver workers
default to automatic CPU-based selection (1/2/4/8, capped at 8); see
[worker configuration](scenario-a-usage.md). Existing planner and replanning
also select workers automatically. Seed and method apply to all three scenarios.

The **Scenario scores** table shows validated scores, workload completion,
overrun, excess slots and ECLO for all three. Click a scenario to inspect its
schedule and search diagnostics. B/C additionally expose main's activity and
location evidence. A failed or timed-out scenario has no fabricated score;
the remaining scenarios still run. Cancel stops the active run, cancels queued
scenarios, and retains all validated outputs. ZIP contains available scenario
CSVs, validation and a revision manifest; Search report contains per-scenario
diagnostics.

## Implementation and scope

- All methods use main's integrated possession model, the observed weekly
  closure policy, and the same exported-CSV validator. B enforces planned
  dates and permits excess supply; C permits delay, at most one excess slot, and ECLO
  within each affected line's two-week window.
- Integrated search optimizes the whole model. Random LNS releases random
  activities. Adaptive LNS selects delay/ECLO-cost, spatial bottleneck, sharing,
  predecessor, contract and diversification neighborhoods by observed reward.
  Repairs preserve original hard constraints and fix weeks/ECLO outside the
  neighborhood. Local nights and cohort membership stay free for all repairs.
- C Adaptive LNS also uses an `eclo_window` neighborhood, tried on its first
  repair and subsequently selected by observed reward. It releases costly work
  together with existing ECLO users on the affected lines, shared partners and
  predecessor/successor chains. Cross-line Live work propagates the release to
  both lines so fixed ECLO decisions cannot pin the old window. CP-SAT jointly
  chooses new weeks and ECLO under the original two-week constraints. This
  closure can exceed the requested neighborhood fraction. The operator does
  not change Existing planner, Integrated CP-SAT or Random LNS into
  adaptive search; select **Adaptive LNS** to use it.
- Global lower bounds come only from whole-model optimization; repair bounds
  are never reported as global. The last validated incumbent survives timeout.

Main's safety policy is conservative and not an organizer-certified checker.
Scores use different
objectives between scenarios, so a smaller B score than A is not an algorithm
quality comparison. The ALNS UI default was chosen using A experiments; B/C
superiority is not established by the smoke benchmark.

## API and CLI

```sh
curl -X POST 'http://127.0.0.1:8000/api/ps1/jobs?public=true&algorithm=strategies&strategy=alns&time_limit_seconds=15&seed=42'

# CLI: one scenario, one new output directory per invocation.
cd backend
.venv/bin/python -m app.ps1.scenario_a.cli --scenario B --strategy random_lns \
  --seconds 15 --workers auto --seed 42 --output ../submission/my-b-run
```

`algorithm=legacy` (also the default) runs A, B and C sequentially. Each gets one uninterrupted search of up to 120 seconds, publishes validated incumbents immediately, and finishes when the primary optimum is proved. It skips the optional earlier-placement tie-break search so a proven score can advance to the next scenario promptly.
`algorithm=scenario_a` remains the backwards-compatible A-only API.

## Reproduce the public smoke benchmark

```sh
backend/.venv/bin/python scripts/check_strategy_matrix.py \
  --output benchmarks/strategy-matrix/reproduction --seconds 15 --seed 42
```

This serial run exercises all 9 selectable-method/scenario combinations with the same
budget, seed and worker count. Each output is read back by its scenario's
validator. The output contains CSVs, diagnostics, validation and `summary.json`.
It is a functional smoke benchmark, not a multi-seed performance ranking.

The [recorded public run](../benchmarks/strategy-matrix/RESULTS.md) returned
validated outputs for all recorded combinations. The existing backend suite (82
tests) and 15 added B/C and job-integration tests passed, as did frontend
lint/type checking.
Chrome smoke checks also passed: A/B/C score rows and detail navigation,
public/uploaded input, full ALNS run, cancellation retaining output, ZIP
download, mobile layout and switching back to the existing planner.

## Thirty dataset average

The [synthetic suite](../datasets/scenario-suite-v1/README.md) has 30 shared inputs,
each with a feasible witness for A, B and C. The UI offers **Run selected method · 90
runs** and **Compare all 4 methods · 360 runs**. Both run serially with the
same configured time and eight CP-SAT workers per run. The Existing planner
uses one bounded pass per dataset, matching the time budget used for the other
methods. A single-input Existing planner run uses one uninterrupted search of up to
120 seconds per scenario, in A/B/C order. The average uses validated finished runs only and displays
the valid, finished and total counts. Failed or cancelled cases never
contribute zero to a mean. The JSON download contains each individual result.

The datasets are generated from feasible witness schedules, with synthetic
supply chosen to cover those witnesses. They test parsing, safety and search
across varied workloads; they do not reproduce the distribution of unseen
organizer inputs. Witness schedules are stored separately and are never given
to the batch solver as hints.

For a saved result outside the browser:

```sh
backend/.venv/bin/python scripts/benchmark_dataset_suite.py \
  --method integrated --seconds 5 --seed 42 \
  --output benchmarks/dataset-suite/new-integrated-run.json
```

`--method all` runs all four methods on all 30 inputs under each scenario.
At five seconds per run this can take more than 30 minutes, and at 15 seconds
per run up to about 90 minutes plus setup. The all-method run has not been used to select a winner;
the UI displays observed results when the user starts it.

The [raw batch result](../benchmarks/dataset-suite/RESULTS.md) records every
run and distinguishes older dataset revisions. The full 360-run comparison
remains an on-demand operation.
