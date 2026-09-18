# PS1 improvement verification

Implementation includes hardened parsing/export validation, joint ECLO and possession optimisation, lexicographic early placement, two-pass jobs with cancellation and retained incumbents, revision-aware APIs/downloads, and an activity/location evidence UI. Deployment publishing, video production, GitLab migration and what-if replanning were not performed.

## Checks performed

- Backend suite: 50 tests passed, including public A/B/C solves. After the final parser/export refinements, 47 targeted tests passed; the three public solves were also regenerated separately.
- Frontend: `npm run lint` (Next type generation + TypeScript) and production static build passed.
- Docker: production image built successfully with Python 3.12 and Node 22. Real localhost container requests passed health/static serving, public A/B/C completion, 54 evidence rows per scenario, all nine CSVs in ZIP, eight-file multipart upload, cancellation request, and stale/current revision download checks. The final image also passed health/static/CSV parsing smoke checks.
- CSVs were regenerated and independently re-parsed. ZIP includes validation summary and a revision manifest. Compatibility and stress failures are retained in JSON.
- Browser interaction/visual QA remains **unverified**: the Browser runtime reported no available browsers, and its discovery list was empty. HTTP and type/build checks do not substitute for clicking, filter interaction, accessibility or responsive visual verification.

## Public run

| Scenario | First validated solution | Final score | Primary model optimum proved |
| --- | ---: | ---: | --- |
| A | 12.03 s | 40.6 | Yes |
| B | 4.32 s | 30 | Yes |
| C | 8.45 s | 25.2 | Yes |

All 54 activities meet the requested workload in each scenario. A has 35 contract-overrun days, B zero, C 21; B uses six ECLO nights. All three have zero excess exported work possessions. Peak memory is process-wide: 742.47 MiB at the end of the public generation process. See `submission/public-results/benchmark.json` for exact platform, timings, bounds and measurements. These are observations, not a hidden-instance runtime guarantee.

## Known compatibility and scaling boundaries

The conservative protection policy differs from the organizers' stated-feasible sample at 36 location/weeks and rejects the old A result at 16. This is explicitly an interpretation difference. The old A score must not be compared to the new A score as if both passed the same validator. The official executable validator is unavailable; model optimality is not official benchmark optimality. See `validator-spec.md` and `compatibility_report.json`.

Seed-42 reduced-supply stress: A was proved infeasible under this policy; B found a validated model optimum; C found a validated incumbent with a remaining gap. Doubled demand (108 activities) produced no validated result within the 30-second probe for A/B/C. The stress process reached approximately 1652 MiB peak working set. Explicit possession pattern enumeration scales combinatorially, and build-time budgeting prevents an unbounded search rather than guaranteeing larger instances finish. The stress probe uses one 30-second pass, not the production improvement pass. See `stress_benchmark.json`.

Manual browser verification remains necessary when a browser becomes available: load public data, observe improving revisions, filter activities/contracts/lines, toggle timeline/table, inspect protection and shared memberships, filter location/week usage, cancel while retaining output, and verify desktop/mobile layout and downloads.
