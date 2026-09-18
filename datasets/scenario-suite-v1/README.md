> Current safety audit: these witnesses were generated under an earlier policy.
> Only 3 of 30 pass `readme-physical-night-v3`; 27 fail physical-night consistency.
> See `benchmarks/dataset-suite/current-validation.json` for exact diagnostics.
> The original inputs and witnesses are preserved for reproducibility. Historical
> feasibility/cost statements below are not current-policy certificates.

# Synthetic A/B/C dataset suite

30 datasets: 10 per scenario. Each input directory contains exactly eight official-schema CSVs.
Each witness is a verified feasible example, not an optimal answer. Do not pass witnesses as hints when measuring a solver.
A witnesses pass both current internal validators; B/C witnesses pass main's validator. Official validator unavailable.
All datasets are synthetic, built on the bundled network; these are not organizer hidden datasets or a guarantee of hidden-set performance.

## Use

Unzip scenario_A_inputs.zip, scenario_B_inputs.zip, scenario_C_inputs.zip or all_30_inputs.zip. Upload the eight CSVs from one case to the frontend.
The frontend runs A/B/C; the scenario in a folder name identifies the scenario whose feasibility was certified. Other scenarios may be infeasible on that input.
For isolated evaluation, use the CLI with --scenario A, B or C and --input pointing at that case's input folder.
Cases 01–05 are designated development; 06–10 evaluation. This is a provisional split, not a statistically independent hidden evaluation.
Supply and workfront limits were derived from generated witness demand. This construction bias is intentional to certify feasibility, not evidence of realistic difficulty.

## Contents

| Case | Split | Activities | Contracts | Weeks | Links | Live | Witness cost |
|---|---|---:|---:|---:|---:|---:|---:|
| A01_small | development | 18 | 11 | 20 | 1 | 4 | 0.0 |
| A02_mixed | development | 36 | 14 | 30 | 6 | 9 | 3299.2 |
| A03_priority_pressure | development | 54 | 16 | 30 | 8 | 16 | 5267.0 |
| A04_interchange_congestion | development | 60 | 16 | 30 | 5 | 22 | 7408.2 |
| A05_long_spans | development | 48 | 14 | 30 | 5 | 13 | 362.8 |
| A06_live_closures | evaluation | 54 | 16 | 30 | 9 | 24 | 5366.8 |
| A07_precedence_chains | evaluation | 60 | 15 | 36 | 39 | 19 | 2127.7 |
| A08_contract_contention | evaluation | 72 | 11 | 30 | 9 | 22 | 685.5 |
| A09_compressed_horizon | evaluation | 72 | 14 | 16 | 21 | 14 | 1315.4 |
| A10_large_mixed | evaluation | 108 | 22 | 40 | 38 | 28 | 10562.3 |
| B01_small | development | 18 | 10 | 20 | 1 | 5 | 180 |
| B02_mixed | development | 36 | 15 | 30 | 7 | 4 | 424 |
| B03_priority_pressure | development | 54 | 16 | 30 | 3 | 10 | 454 |
| B04_interchange_congestion | development | 60 | 16 | 30 | 6 | 14 | 1168 |
| B05_long_spans | development | 48 | 14 | 30 | 7 | 7 | 1610 |
| B06_live_closures | evaluation | 54 | 17 | 30 | 9 | 33 | 1124 |
| B07_precedence_chains | evaluation | 60 | 15 | 36 | 29 | 8 | 1110 |
| B08_contract_contention | evaluation | 72 | 10 | 30 | 19 | 12 | 1361 |
| B09_compressed_horizon | evaluation | 72 | 15 | 16 | 12 | 21 | 1888 |
| B10_large_mixed | evaluation | 108 | 23 | 40 | 38 | 30 | 1940 |
| C01_small | development | 18 | 10 | 20 | 0 | 5 | 25.0 |
| C02_mixed | development | 36 | 15 | 30 | 1 | 8 | 2867.9 |
| C03_priority_pressure | development | 54 | 17 | 30 | 7 | 7 | 11277.5 |
| C04_interchange_congestion | development | 60 | 16 | 30 | 6 | 15 | 3888.5 |
| C05_long_spans | development | 48 | 14 | 30 | 8 | 10 | 3677.5 |
| C06_live_closures | evaluation | 54 | 16 | 30 | 3 | 29 | 3095.3 |
| C07_precedence_chains | evaluation | 60 | 15 | 36 | 38 | 12 | 3325.4 |
| C08_contract_contention | evaluation | 72 | 10 | 30 | 12 | 9 | 990.6 |
| C09_compressed_horizon | evaluation | 72 | 15 | 16 | 25 | 15 | 4372.8 |
| C10_large_mixed | evaluation | 108 | 22 | 40 | 46 | 39 | 12038.3 |

## Reproduce

```sh
backend/.venv/bin/python scripts/generate_scenario_datasets.py --output datasets/scenario-suite-reproduction --seed 20260918
```
