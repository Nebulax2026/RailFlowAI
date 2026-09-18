# Synthetic dataset batch: Greedy, five seconds per case

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
