# Four search methods, three scenarios

Start `npm run dev`, open http://localhost:3000, select **Strategy comparison**,
choose a **Search method**, then click **Load public dataset** or upload the
eight CSV files and click **Run A, B and C**.

Each of Greedy, Integrated CP-SAT, Random LNS and Adaptive LNS now runs A, B and
C sequentially. **Time per scenario** applies separately: 15 seconds means up
to about 45 seconds of search for the job, plus worker startup/export overhead.
One solver worker and one active subprocess prevent the three runs from
competing for CPU. Seed and method apply to all three scenarios.

The **Scenario scores** table shows validated scores, workload completion,
overrun, excess slots and ECLO for all three. Click a scenario to inspect its
schedule and search diagnostics. B/C additionally expose main's activity and
location evidence. A failed or timed-out scenario has no fabricated score;
the remaining scenarios still run. Cancel stops the active run, cancels queued
scenarios, and retains all validated outputs. ZIP contains available scenario
CSVs, validation and a revision manifest; Search report contains per-scenario
diagnostics.

## Implementation and scope

- A retains the previously implemented solver and `local-witnessed-sharing-v1`
  policy. Its algorithm and objective have not been replaced.
- B/C reuse main's integrated possession model and
  `local-protection-reservations-v1` CSV validator. B enforces planned dates and
  permits excess supply; C permits delay, at most one excess slot, and ECLO
  within each affected line's two-week window.
- B/C Greedy is a constructive topological scheduler with legal shared cohorts,
  contract workfront checks and optional ECLO. It does not call CP-SAT and its
  failure does not prove infeasibility.
- B/C integrated search optimizes the whole model. Random LNS releases random
  activities. Adaptive LNS selects delay/ECLO-cost, spatial bottleneck, sharing,
  predecessor, contract and diversification neighborhoods by observed reward.
  Repairs preserve original hard constraints and fix weeks/ECLO outside the
  neighborhood. Local nights and cohort membership stay free for all repairs.
- Global lower bounds come only from whole-model optimization; repair bounds
  are never reported as global. The last validated incumbent survives timeout.

Main's safety policy is conservative and not an organizer-certified checker.
A and B/C currently have different documented sharing interpretations; see
[validator comparison](validator-main-review.md). Scores also use different
objectives between scenarios, so a smaller B score than A is not an algorithm
quality comparison. The ALNS UI default was chosen using A experiments; B/C
superiority is not established by the smoke benchmark.

## API and CLI

```sh
curl -X POST 'http://127.0.0.1:8000/api/ps1/jobs?public=true&algorithm=strategies&strategy=alns&time_limit_seconds=15&seed=42'

# CLI: one scenario, one new output directory per invocation.
cd backend
.venv/bin/python -m app.ps1.scenario_a.cli --scenario B --strategy random_lns \
  --seconds 15 --workers 1 --seed 42 --output ../submission/my-b-run
```

`algorithm=legacy` (also the default) keeps main's two-pass A/B/C planner.
`algorithm=scenario_a` remains the backwards-compatible A-only API.

## Reproduce the public smoke benchmark

```sh
backend/.venv/bin/python scripts/check_strategy_matrix.py \
  --output benchmarks/strategy-matrix/reproduction --seconds 15 --seed 42
```

This serial run exercises all 12 method/scenario combinations with the same
budget, seed and worker count. Each output is read back by its scenario's
validator. The output contains CSVs, diagnostics, validation and `summary.json`.
It is a functional smoke benchmark, not a multi-seed performance ranking.

The [recorded public run](../benchmarks/strategy-matrix/RESULTS.md) returned
validated outputs for all 12 combinations. The existing backend suite (82
tests) and 15 added B/C and job-integration tests passed, as did frontend
lint/type checking.
Chrome smoke checks also passed: A/B/C score rows and detail navigation,
public/uploaded input, full ALNS run, cancellation retaining output, ZIP
download, mobile layout and switching back to the existing planner.
