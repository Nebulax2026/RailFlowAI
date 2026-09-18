# Scenario A benchmark

All costs use the documented policy and independent CSV validation. Invalid runs have no cost. Medians/worst costs cover feasible runs only; read them with the success counts. No official validator was available.

| Case | Seconds | Strategy | Feasible | Median cost | Worst cost | Median gap | First feasible (s) | Wall (s) | Peak RSS MB |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| heldout_dates | 5 | alns | 2/2 | 7749.00 | 7752.00 | 1696.00 | 0.03 | 4.84 | 379.88 |
| heldout_dates | 5 | greedy | 2/2 | 9162.00 | 9162.00 | 3109.00 | 0.03 | 0.24 | 86.25 |
| heldout_dates | 5 | integrated | 2/2 | 9162.00 | 9162.00 | 1920.35 | 0.03 | 4.83 | 336.08 |
| heldout_dates | 5 | random_lns | 2/2 | 7764.50 | 7777.00 | 1711.50 | 0.03 | 4.87 | 344.64 |
| heldout_dates | 15 | alns | 2/2 | 7730.50 | 7746.00 | 256.80 | 0.03 | 14.25 | 441.61 |
| heldout_dates | 15 | greedy | 2/2 | 9162.00 | 9162.00 | 3109.00 | 0.03 | 0.24 | 86.34 |
| heldout_dates | 15 | integrated | 2/2 | 7744.90 | 7774.80 | 29.90 | 0.03 | 13.02 | 342.53 |
| heldout_dates | 15 | random_lns | 2/2 | 7749.00 | 7752.00 | 275.30 | 0.04 | 14.26 | 401.03 |
| heldout_release | 5 | alns | 2/2 | 411.25 | 653.10 | 383.60 | 0.03 | 4.83 | 307.22 |
| heldout_release | 5 | greedy | 2/2 | 701.40 | 701.40 | 676.20 | 0.03 | 0.24 | 86.52 |
| heldout_release | 5 | integrated | 2/2 | 694.40 | 701.40 | 657.30 | 0.03 | 4.83 | 286.69 |
| heldout_release | 5 | random_lns | 2/2 | 389.55 | 538.30 | 361.90 | 0.03 | 4.85 | 317.12 |
| heldout_release | 15 | alns | 2/2 | 455.70 | 627.20 | 418.60 | 0.03 | 14.26 | 339.41 |
| heldout_release | 15 | greedy | 2/2 | 701.40 | 701.40 | 676.20 | 0.03 | 0.24 | 86.31 |
| heldout_release | 15 | integrated | 2/2 | 549.15 | 701.40 | 512.05 | 0.03 | 9.20 | 294.78 |
| heldout_release | 15 | random_lns | 2/2 | 182.35 | 186.90 | 145.25 | 0.03 | 14.24 | 342.73 |
| infeasible | 5 | alns | 0/2 | — | — | — | — | 0.44 | 158.05 |
| infeasible | 5 | greedy | 0/2 | — | — | — | — | 0.19 | 84.16 |
| infeasible | 5 | integrated | 0/2 | — | — | — | — | 0.44 | 157.84 |
| infeasible | 5 | random_lns | 0/2 | — | — | — | — | 0.45 | 158.89 |
| infeasible | 15 | alns | 0/2 | — | — | — | — | 0.44 | 158.02 |
| infeasible | 15 | greedy | 0/2 | — | — | — | — | 0.19 | 84.20 |
| infeasible | 15 | integrated | 0/2 | — | — | — | — | 0.45 | 157.89 |
| infeasible | 15 | random_lns | 0/2 | — | — | — | — | 0.44 | 158.06 |
| public | 5 | alns | 2/2 | 381.85 | 636.30 | 356.65 | 0.03 | 4.85 | 347.05 |
| public | 5 | greedy | 2/2 | 672.00 | 672.00 | 646.80 | 0.03 | 0.23 | 86.39 |
| public | 5 | integrated | 2/2 | 672.00 | 672.00 | 645.40 | 0.03 | 4.82 | 321.80 |
| public | 5 | random_lns | 2/2 | 352.45 | 627.20 | 327.25 | 0.04 | 4.84 | 347.69 |
| public | 15 | alns | 2/2 | 45.15 | 47.60 | 15.75 | 0.03 | 14.29 | 394.09 |
| public | 15 | greedy | 2/2 | 672.00 | 672.00 | 646.80 | 0.03 | 0.23 | 86.45 |
| public | 15 | integrated | 2/2 | 314.30 | 436.10 | 273.70 | 0.03 | 14.23 | 334.64 |
| public | 15 | random_lns | 2/2 | 337.40 | 627.20 | 308.00 | 0.03 | 14.27 | 389.52 |
