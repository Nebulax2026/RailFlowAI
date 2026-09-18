# Shared 30-dataset batch: Greedy, five seconds per scenario

Each of the 30 common inputs was run under A, B and C (90 serial runs), with
seed 42 under the earlier one-worker configuration. Greedy does not use
CP-SAT workers, so the worker setting had no effect on these scores. The CSV
validator accepted 28/30 A results and all
30 B/C results. The two A misses (D14 and D30) ended with
`no_solution_within_budget`; each input has a separately validated witness.
These are search failures, not invalid output schedules.

| Scenario | Valid / total | Average valid score | Worst valid score |
|---|---:|---:|---:|
| A | 28/30 | 52.4 | 1200.0 |
| B | 30/30 | 5.367 | 28 |
| C | 30/30 | 5.367 | 28.0 |

The [raw result](shared-30-greedy-5s-seed42.json) includes every dataset and
scenario row. Reproduce it with:

```sh
backend/.venv/bin/python scripts/benchmark_dataset_suite.py --method greedy --seconds 5 --seed 42 --output benchmarks/dataset-suite/shared-reproduction.json
```

## Previous scenario-specific suite

This result used the previous 10-input-per-scenario suite. Its input IDs no longer
exist in the current 30 shared dataset suite; do not compare these averages with
new runs. The JSON is retained as a historical record.

Seed 42; one worker; 30 serial runs; all scores below are from validated CSVs. This is one run on this machine, not a hidden-set estimate.

| Scenario | Valid / total | Average score | Worst valid score |
|---|---:|---:|---:|
| A | 10/10 | 1147.13 | 2399.5 |
| B | 10/10 | 625.8 | 1358 |
| C | 10/10 | 1357.56 | 4273.6 |

The raw JSON contains every case score, elapsed time, status, runtime and method configuration. Datasets and witness schedules are in `datasets/scenario-suite-v1/`; witnesses were never solver hints.

Reproduce:

```sh
backend/.venv/bin/python scripts/benchmark_dataset_suite.py --method greedy --seconds 5 --seed 42 --output benchmarks/dataset-suite/reproduction.json
```
