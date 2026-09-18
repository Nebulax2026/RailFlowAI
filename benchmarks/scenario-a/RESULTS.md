# Measured Scenario A results

Environment: Apple M5, 10 logical CPUs, 32 GiB RAM; macOS 26.6.2 arm64; Python 3.12.14; OR-Tools 9.15.6755. Each optimizer used **one worker**, and benchmark subprocesses ran serially. All times are wall time; the raw files include process overhead and peak process RSS. Model costs and bounds apply to `local-witnessed-sharing-v1`, not the unavailable official evaluator.

The comparison contains **64 runs**: four methods × two seeds (11, 29) × two budgets (5, 15 seconds) × four cases. All **48 runs on the three known-feasible inputs** returned independently validated complete schedules. The 12 CP-SAT-based runs on the deliberately impossible input proved policy infeasibility. The four greedy runs on that input reported only failure to find a solution, not a proof.

## Cost at 15 seconds

Entries are median / worst feasible cost over both seeds. Every entry here had 2/2 valid runs.

| Method | Public tuning | Heldout dates/priorities | Heldout release dates |
|---|---:|---:|---:|
| Greedy | 672.0 / 672.0 | 9162.0 / 9162.0 | 701.4 / 701.4 |
| Integrated CP-SAT | 314.3 / 436.1 | 7744.9 / 7774.8 | 549.15 / 701.4 |
| CP-SAT + random related LNS | 337.4 / 627.2 | 7749.0 / 7752.0 | 182.35 / 186.9 |
| CP-SAT + adaptive LNS | **45.15 / 47.6** | **7730.5 / 7746.0** | 455.7 / 627.2 |

ALNS is the UI/config default based **only on the public tuning split**, not on heldout selection. It is not best on every input: random LNS is substantially better on the release-date variant. Short runs are sensitive to seed and machine load. This small study does not establish general superiority, and increasing time does not guarantee the same intermediate trajectory on another machine.

Full five-second results, first-feasible times, memory, wall times and gaps: [comparison table](2026-09-18/comparison.md). Raw runs and trajectories: [JSONL](2026-09-18/raw-results.jsonl). Selection rationale: [selection.json](2026-09-18/selection.json).

## Initialization comparison

Two further integrated runs per initialization use the public input, the same seeds and a 15-second budget:

| Initialization | Seed 11 cost | Seed 29 cost | Feasible |
|---|---:|---:|---:|
| Direct objective search | 2671.2 | 6692.7 | 2/2 |
| Short feasibility phase, then objective | 3784.2 | 3994.9 | 2/2 |
| Greedy feasible hint, then objective | 436.1 | 192.5 | 2/2 |

The greedy hint remains enabled. These experiments are stored in [direct initialization](initialization-direct/raw-results.jsonl) and [feasibility initialization](initialization-feasibility/raw-results.jsonl). The hint row is from the original comparison, under the same limits.

## Longer reference run and policy caveat

A separate 30-second integrated reference run, seed 42, returned **40.6**, with full-model bound **40.6**, in 18.34 seconds. This proves optimality **for the configured conservative policy only**. Its three CSVs, independent validation, bounds and trajectory are in [`submission/scenario-a-tuning-integrated`](../../submission/scenario-a-tuning-integrated) (repository-relative path: `submission/scenario-a-tuning-integrated`). This reference schedule is used solely to establish feasible benchmark variants; the benchmark never supplies it as a hint.

The organizer sample is advertised as feasible, but our policy reports 18 reservation conflicts on it. See [the complete sample audit](official-sample-audit.json) and [the unresolved semantics](../../docs/scenario-a-rules.md). Neither a lower score under the legacy checker nor a proof under this new policy establishes official competition performance.

Reproduction commands and output formats: [usage guide](../../docs/scenario-a-usage.md).
