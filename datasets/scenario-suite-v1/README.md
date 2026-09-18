# Synthetic common A/B/C dataset suite

30 common datasets. Each input directory contains eight official-schema CSVs and is evaluated under A, B and C.
Each witness is a verified feasible example, not an optimal answer. Do not pass witnesses as hints when measuring a solver.
Every input has A, B and C feasible witnesses under readme-physical-night-v3. A witnesses pass both current internal validators; B/C witnesses pass main's validator. Official validator unavailable.
All datasets are synthetic, built on the bundled network; these are not organizer hidden datasets or a guarantee of hidden-set performance.

## Use

Unzip all_30_inputs.zip. Upload the eight CSVs from one case to the frontend, which runs A, B and C on that same input.
For isolated evaluation, use the CLI with --scenario A, B or C and --input pointing at that case's input folder.
Cases 01–15 are designated development; 16–30 evaluation. This is a provisional split, not a statistically independent hidden evaluation.
Supply and workfront limits were derived from generated witness demand. This construction bias is intentional to certify feasibility, not evidence of realistic difficulty.

## Contents

| Case | Split | Activities | Contracts | Weeks | Links | Live | A/B/C witness cost |
|---|---|---:|---:|---:|---:|---:|---:|
| D01_small | development | 18 | 9 | 20 | 1 | 4 | 0.0/0/0.0 |
| D02_mixed | development | 36 | 14 | 30 | 4 | 9 | 0.0/0/0.0 |
| D03_priority_pressure | development | 54 | 16 | 30 | 7 | 9 | 0.0/0/0.0 |
| D04_interchange_congestion | development | 60 | 16 | 30 | 8 | 18 | 0.0/0/0.0 |
| D05_long_spans | development | 48 | 15 | 30 | 7 | 9 | 0.0/0/0.0 |
| D06_live_closures | development | 54 | 17 | 30 | 8 | 25 | 0.0/0/0.0 |
| D07_precedence_chains | development | 60 | 14 | 36 | 40 | 14 | 0.0/0/0.0 |
| D08_contract_contention | development | 72 | 11 | 30 | 13 | 9 | 0.0/0/0.0 |
| D09_compressed_horizon | development | 72 | 16 | 16 | 21 | 22 | 0.0/0/0.0 |
| D10_large_mixed | development | 108 | 22 | 40 | 41 | 40 | 0.0/0/0.0 |
| D11_small | development | 18 | 11 | 20 | 1 | 2 | 0.0/0/0.0 |
| D12_mixed | development | 36 | 14 | 30 | 8 | 6 | 0.0/0/0.0 |
| D13_priority_pressure | development | 54 | 16 | 30 | 3 | 9 | 0.0/0/0.0 |
| D14_interchange_congestion | development | 60 | 18 | 30 | 7 | 13 | 0.0/0/0.0 |
| D15_long_spans | development | 48 | 14 | 30 | 2 | 12 | 0.0/0/0.0 |
| D16_live_closures | evaluation | 54 | 16 | 30 | 11 | 32 | 0.0/0/0.0 |
| D17_precedence_chains | evaluation | 60 | 15 | 36 | 32 | 10 | 0.0/0/0.0 |
| D18_contract_contention | evaluation | 72 | 10 | 30 | 19 | 9 | 0.0/0/0.0 |
| D19_compressed_horizon | evaluation | 72 | 15 | 16 | 16 | 12 | 0.0/0/0.0 |
| D20_large_mixed | evaluation | 108 | 23 | 40 | 45 | 30 | 0.0/0/0.0 |
| D21_small | evaluation | 18 | 11 | 20 | 1 | 2 | 0.0/0/0.0 |
| D22_mixed | evaluation | 36 | 13 | 30 | 7 | 4 | 0.0/0/0.0 |
| D23_priority_pressure | evaluation | 54 | 16 | 30 | 4 | 11 | 0.0/0/0.0 |
| D24_interchange_congestion | evaluation | 60 | 17 | 30 | 4 | 15 | 0.0/0/0.0 |
| D25_long_spans | evaluation | 48 | 14 | 30 | 6 | 13 | 0.0/0/0.0 |
| D26_live_closures | evaluation | 54 | 17 | 30 | 6 | 26 | 0.0/0/0.0 |
| D27_precedence_chains | evaluation | 60 | 14 | 36 | 39 | 9 | 0.0/0/0.0 |
| D28_contract_contention | evaluation | 72 | 10 | 30 | 12 | 9 | 0.0/0/0.0 |
| D29_compressed_horizon | evaluation | 72 | 15 | 16 | 18 | 19 | 0.0/0/0.0 |
| D30_large_mixed | evaluation | 108 | 22 | 40 | 41 | 34 | 0.0/0/0.0 |

## Reproduce

```sh
backend/.venv/bin/python scripts/generate_scenario_datasets.py --output datasets/scenario-suite-reproduction --seed 20260918
```
