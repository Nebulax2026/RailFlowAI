# Shared 30-dataset batch under physical-night safety v3

Each of the 30 common inputs was run under A, B and C (90 serial runs), with
seed 42 and a five-second limit. Greedy does not use CP-SAT workers. Each
input has a separately validated A/B/C witness under the current policy.
Missing Greedy scores mean no valid schedule was found within the budget;
they are not invalid published CSVs or infeasibility proofs.

| Scenario | Valid / total | Average valid score | Worst valid score |
|---|---:|---:|---:|
| A | 4/30 | 0.0 | 0.0 |
| B | 7/30 | 136.429 | 560 |
| C | 7/30 | 15.0 | 75.0 |

The [raw current result](v3-shared-greedy-5s-seed42.json) includes every
dataset and scenario row. The [witness audit](current-validation.json) records
all 90 current-policy checks. Reproduce the benchmark with:

```sh
backend/.venv/bin/python scripts/benchmark_dataset_suite.py --method greedy --seconds 5 --seed 42 --output benchmarks/dataset-suite/new-greedy-run.json
```

## Historical results

The [earlier shared-suite run](shared-30-greedy-5s-seed42.json) used a prior
dataset revision and safety policy. It recorded 28/30 valid A results and
30/30 for B/C, with means 52.4, 5.367, and 5.367. It cannot be reproduced
with the current inputs and validator.

### Previous scenario-specific suite

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

Its raw JSON is retained as a historical record; the old inputs are no longer
in the current suite.
