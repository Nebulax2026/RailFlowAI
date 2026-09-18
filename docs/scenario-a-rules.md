# Scenario A rules and model evidence

Source: [organizer PS1 brief](https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement/blob/966c976005db2e3e40a691cff268fdb8f396a5df/PS1/PS1_README.md), revision `966c976005db2e3e40a691cff268fdb8f396a5df`, inspected 2026-09-18. All eight input CSVs, the brief, drawio/SVG diagrams and the three submission sample files have Git blob hashes identical to the local `PS1/` copies. The recursive official repository tree was not truncated. It contains **no executable PS1 validator, scorer or occupancy expander**, despite mentioning `python3 -m trackaccess expand`.

This implementation is an exact integrated model **of the explicit policy below**. It is not a claim of exact equivalence to the unavailable official validator. Official validation results cannot currently be supplied.

| Rule | Evidence | Implementation / certainty |
|---|---|---|
| Every activity completes its workload | §2.4.1 | Exact required count in A, each access yields one unit. Removing surplus accesses cannot increase cost, capacity consumption or dependencies; direct sharing between other activities is unchanged. |
| At most one access per activity/week | §2.4.10 explicitly says so, also demand/sample | Boolean `x[activity,week]`. |
| Earliest assignment | §2.4.2 | Week containing `planned_start_date`; never clamp a late start into the horizon. |
| Predecessors | §2.4.3 | Strictly later week; cross-contract links preserved; cycles rejected. |
| Local contract nights | §2.6 and §2.4.7–8 | `contract_number + activity_type + week`; range 1..input cap; at most input workfronts per night. No link to location slot indices. |
| Location groups | §2.4.5–6 | Local to `location_id + week`; one PM alone, at most one PC and three C, or four C. Distinct groups can occupy different nights **within the same week**. |
| Actual work footprint | §2.1–2 | All traversed tunnel sectors and platform sectors, including both endpoint platforms. Supports SEC and PLAT endpoints on a connected linear line. Missing resources are errors. |
| Buffers | §2.3, §2.4.4, `05_BUFFER_LOCATION.csv` | Radius from input; clips only at actual line boundaries. Buffers include platforms reached by the expanded span. Platform inclusion is **conservative, not confirmed by evaluator code**. |
| Live closure | §2.2, §2.4.4 | Mirror expanded footprint to opposite bound. A Live closure reaching H01–H02 reserves both lines' tunnel and hub platforms on both bounds. Crossing caused only by a buffer reaching the interchange is **conservative/unconfirmed**. |
| Sharing exemption | §2.4.6 | Direct partners must demonstrably share an actual work group somewhere that week before their reservations may share a local slot. Each reservation-sharing pair requires this witness. No transitive waiver to an external activity. Cross-location extent is **not fully specified publicly**. |
| Buffer vs work / buffer vs buffer | §1 non-negotiables and §2.4.4 | External reservations cannot share a slot unless direct sharing is witnessed as above. Their legal local packing is included in supply use. How reservations should draw down input supply is **not confirmed by official tooling**. |
| Supply by week | §2.4.5, §2.5 A, `04_LOCATION_SUPPLY.csv` | Flat `supply_capacity` used in every week; input contains no weekly supply table. No added resources or capacity. |
| Horizon | `06_PARAMETERS.csv`, output weeks in sample | Exactly input `horizon_weeks`; no public extension rule. No implicit extension. An infeasibility proof applies to this horizon and policy. |
| ECLO | §2.5 A | Every output row has `eclo=0`. |
| Completion date | Sample `RESULTS.csv` versus last access week | `horizon_start + (7*last_week - 1) days`; end-of-week convention matches the organizer sample. This convention is inferred, not stated as executable scoring code. |
| Lateness target | §2.5 | Contract `planned_completion_date`, never contractual completion date, never a hard deadline. |
| Score aggregation | Detailed §2.7 and §2.5 worked examples | Sum **per activity**: max(0, activity completion date − contract planned completion date) × contract weight 100/10/1 × activity multiplier 1.3/1.2/1.0. Integer tenths internally. |
| Contract summary | §2.6 RESULTS schema | Maximum activity completion in contract; `overrun_days` recalculated from that date. Contract totals are not substituted for the activity objective. |

## Policy and unresolved conflict

Policy identifier: `local-witnessed-sharing-v1`. `policy.py` prepares footprints and graphs, while `validation.py` walks the station graph independently. Both implement the documented interpretation. The validator's local reservation packing is a separate bounded backtracking algorithm, not an invocation of the optimizer.

The official submission sample is described as feasible by the brief, but this policy finds **18 location/week reservation conflicts**, primarily around buffer platform coverage and Live reservations. The sample's activity-weighted cost is 48.3; its contract-overrun total is 28 days. These are different aggregation units. The sample conflict is recorded in `benchmarks/scenario-a/official-sample-audit.json`; it is **not evidence that the organizer's sample is officially invalid**. It is evidence that this safety interpretation and the unpublished evaluator may differ.

Before claiming official parity, ask the organizer for: (1) the `trackaccess` package/version, (2) platform inclusion at buffer boundaries, (3) whether Live buffers trigger interchange crossover, (4) reservation capacity accounting, and (5) the exact cross-location scope of a sharing exemption. Until then the UI and reports explicitly scope validation, bounds and optimality to this policy. We do not relax these checks just to make the sample pass.

## Integrated model

There is one Boolean per reachable activity/week and an exact demand sum. Earliest starts propagate predecessor workload; latest finishes propagate successor workload backwards from the fixed horizon. These are necessary bounds, not heuristic pruning. Start/end use minimum/maximum selected weeks.

Local night Booleans enforce contract resources. Local slot Booleans assign each actual work or implicit reservation to one supplied slot. Slot usage, PM exclusivity, PC count and total count are exact. Direct sharing witness Booleans connect exemption eligibility to actual work groups; **slot numbers are never equated across locations or with contract nights**. Every time, resource, and sharing decision is optimized together. Local used-slot prefix symmetry is valid because only those slot labels are interchangeable.

The model minimizes only the activity cost in integer tenths. There is no lexicographic priority substitution, balancing bonus, sharing reward, or early-placement tie-breaker. Priority-overrun diagnostics aggregate activity delay days; RESULTS aggregates each contract once.

## Search and bounds

Initialization supports direct optimization, a short feasibility phase, and a priority/slack/DAG/resource-aware greedy hint. A heuristic failure is never called infeasibility. Every incumbent is exported and re-read independently before acceptance, checkpointing or download.

ALNS uses the same complete model. It fixes week decisions outside the selected neighborhood and leaves all local resource/slot variables free, so a frozen group cannot obstruct repacking. Existing co-sharing groups are included transitively in the released activity set. Operators cover weighted delay/blockers, spatial bottlenecks, sharing, predecessor chains, contract resources and random/week-window diversification. Operator weights adapt to cost improvement per second with a positive exploration floor. Stagnation increases neighborhood size, and periodic **full-model** restarts get budget. Acceptance is strictly improving; best feasible is retained separately from each candidate. No simulated annealing is enabled without evidence.

Global bounds combine an admissible earliest-DAG relaxation and full-model CP-SAT bounds. Feasibility phases and LNS subproblem bounds never update the global bound. Equal verified upper/lower bounds prove optimality only for this policy; verified zero plus nonnegative costs is a valid special case. Results distinguish feasible, policy-optimal, no solution within budget, policy-infeasible, input/model errors and cancellation.

## Limits

The fixed-budget benchmark is a small study, not a hidden-instance performance guarantee. The model uses activity-pair sharing witnesses and can grow substantially on larger dense instances. Initialization, model construction, validation and export count against the worker budget, with a finalization reserve. The API provides an external process timeout and incumbent recovery; process startup/termination overhead is reported separately. Linux CLI runs apply an address-space limit; on macOS only CP-SAT's advisory memory limit is available and the report says so. Threads use the configured worker count; benchmark runs are serial and API jobs share one queue.

The abstract input has no calendar-night identity linking different locations. This solver therefore does not certify a real-world dispatch calendar beyond the published local accounting model. Supplying such a calendar requires additional official semantics.
