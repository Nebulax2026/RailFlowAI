# Public four-method / three-scenario smoke run

2026-09-18; seed 42; 15 seconds per scenario; 1 worker; serial subprocesses.

All 12 runs returned CSVs accepted by their configured validator. This is a functional check, not a multi-seed ranking. A uses local-witnessed-sharing-v1; B/C use local-protection-reservations-v1. Neither checker is the organizer executable.

| Method | A | B | C |
| --- | ---: | ---: | ---: |
| greedy | 672.0 | 72 | 67.2 |
| integrated | 110.6 | 30 | 52.2 |
| random_lns | 661.5 | 30 | 67.2 |
| alns | 40.6 | 40 | 25.2 |

Full-model lower bounds matched the best cost in B integrated, B random LNS and C ALNS. Other runs found feasible outputs without a proof of optimality. Raw diagnostics retain phase and operator outcomes; restricted LNS bounds are not global bounds.

Reproduce from the repository root:

```sh
backend/.venv/bin/python scripts/check_strategy_matrix.py --output benchmarks/strategy-matrix/reproduction --seconds 15 --seed 42
```
