# RailFlowAI Solution Write-up

RailFlowAI converts the PS1 demand book into complete, auditable possession schedules for Scenarios A, B, and C. A strict parser checks the eight source CSVs before a topology layer expands each activity into its work and closure footprint. OR-Tools CP-SAT then chooses access weeks, legal co-sharing groups, local nights, and ECLO use while enforcing workload, precedence, capacity, workfront, and strict weekly-closure rules.

The product is validator-first: every result is exported to the three required CSV files and independently re-read before download. The UI shows policy score, overruns, excess access, ECLO usage, total search time, activity evidence, location load, and contract completion.

The Operations tab supports bounded disruption re-planning and a grounded Schedule Assistant. Re-planning treats the reduced location capacity as a hard constraint, preserves completed work, and provides a validated revised CSV set plus activity-level changes.

## Technology

Python 3.12, FastAPI, OR-Tools CP-SAT, Next.js, React, TypeScript, Docker, Pytest, and TypeScript checking.

## Validation boundary

The official validator executable is not available locally. The strict weekly-closure policy and scoring formula were updated from official feedback and protected with regression tests. All three final scenario outputs are officially accepted: Scenario A (608.3), Scenario B (50.0), and Scenario C (122.4).
