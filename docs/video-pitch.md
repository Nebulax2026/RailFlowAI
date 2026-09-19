# RailFlowAI 2–3 Minute Demo Script

## 0:00–0:20 — The planning problem

**Show:** The RailFlowAI intake page.

**Say:** “Rail maintenance activities compete for a limited number of weekly possessions across platforms, sectors, buffers, and tunnels. Each activity has workload, release dates, predecessors, workfronts, safety footprint, and contract deadline constraints. RailFlowAI converts the PS1 demand book into a complete, auditable possession plan.”

## 0:20–0:40 — Input validation

**Show:** The eight-file upload list, then click **Load public dataset** or upload the demand book.

**Say:** “The application accepts the eight official CSV inputs. Before optimisation, it checks schemas, cross-file identifiers, dates, topology, capacities, contracts, and predecessors. Invalid input does not reach the solver.”

## 0:40–1:10 — Optimisation and policies

**Show:** The algorithm selector and a running A/B/C job.

**Say:** “The validated input is solved with OR-Tools CP-SAT. The model jointly assigns access weeks, legal co-sharing groups, local nights, and ECLO decisions. One run produces three policy views: A protects supply, B protects planned completion, and C balances delay, excess capacity, and ECLO. The dashboard shows each policy’s objective, overruns, excess access, ECLO nights, and total search time.”

## 1:10–1:40 — Explainable schedule evidence

**Show:** One scenario’s Overview, Activities, Location & capacity, and Contract results tabs.

**Say:** “The result is inspectable. We can see weekly access load, constrained locations, each activity’s scheduled work, legal possession groups, and contract completion dates. This makes the trade-off behind a score visible instead of treating the solver as a black box.”

## 1:40–2:05 — Validator-first export

**Show:** Result details, then the CSV download links and ZIP download.

**Say:** “Before files are downloadable, RailFlowAI exports the three required CSVs and validates those CSV bytes again. This independent check covers workload, precedence, capacity, workfront, ECLO, results, legal co-sharing, and weekly closure compatibility. The ZIP therefore contains the exact artifact that was validated.”

## 2:05–2:30 — Validation learning and close

**Show:** The final submission folder with A.zip, B.zip, and C.zip.

**Say:** “An early local schedule was rejected by the official validator because an activity entered another group’s weekly closure zone. We converted that feedback into regression tests and tightened the closure model. All three final schedules were accepted officially: Scenario A at 608.3, Scenario B at 50.0, and our optimized Scenario C at 122.4. RailFlowAI provides a repeatable path from demand-book validation to explainable, submission-ready schedules.”

## Recording notes

- Use the existing planner / normal CP-SAT path for the final submission demonstration.
- Present integrated CP-SAT and adaptive LNS only as comparison modes; do not claim they produced the final C=122.4 candidate.
- Say “internally validated” for local checks and “officially accepted” only for confirmed replacement submission results.
