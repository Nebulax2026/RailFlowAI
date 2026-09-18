# Current README-rules update

The user confirmed that the supplied sample is format-only, not a feasible
reference answer. The current implementation is `readme-physical-night-v3`;
the previous v2 measurements below are historical and do not certify current outputs.

- 71 targeted backend tests passed (public solves are measured separately).
- Type checking and the production frontend build passed.
- New coverage: contradictory cross-location sharing, transitive cross-contract
  conflicts, seven/eight-night limits, validation timeout vs infeasibility,
  unsafe incumbent revalidation, and API physical-night evidence.
- No browser interaction or Docker runtime verification was performed for this update.
- A/B/C CSVs were regenerated under v3, independently revalidated and checked
  byte-for-byte against the ZIP. Every exported physical-night witness was also
  checked directly against raw CSV local indices, sharing relations and protection
  intersections, without using the coloring search.

| Scenario | First 30-second pass | Final score | Model optimum proved |
| --- | --- | ---: | --- |
| A | No solution in first 30 s | 25.2 | True |
| B | 29.63 s | 30 | True |
| C | No solution in first 30 s | 25.2 | True |

All three required the improvement pass in the final measured run. A first found
an incumbent 28.81 seconds into its additional pass; C 21.72 seconds into its
additional pass. These are not first-pass success times. The 30-second first-result
target was missed for A and C. B's first-pass score was 439 and improved to 30.
The final scores are A 25.2 / B 30 / C 25.2; A/C each have 21 contract-overrun days
across two contracts, B has zero delay and six ECLO accesses, all have zero excess
work slots. Peak process memory: 1712.71 MiB. Eight CP-SAT workers were used.
Exact OS/Python, wall times and bounds are in `benchmark.json`.

The format-only sample produces 64 safety diagnostics under the current model
and receives no objective score. This is an expected negative fixture, not a
requirement to weaken validation. Historic reports below are explicitly superseded.

---

## Historical v2 verification (superseded)

# PS1 improvement verification

Implementation includes hardened parsing/export validation, joint ECLO and possession optimisation, lexicographic early placement, two-pass jobs with cancellation and retained incumbents, revision-aware APIs/downloads, and an activity/location evidence UI. Deployment publishing, video production, GitLab migration and what-if replanning were not performed.

## Current supply/safety correction checks

- 55 backend regression/API tests passed; three public solve tests also passed during the first check, and final A/B/C outputs were subsequently regenerated and independently re-parsed.
- New cases cover supply-independent same-night collisions in A/B/C, separate local nights, cross-contract timing uncertainty, location-local sharing partners, and handwritten Live mirroring/interchange conflicts. Existing schema, date, workload, ECLO, workfront and objective-enumeration tests remain green.
- Frontend `npm.cmd run lint` and production build passed. No browser interaction or Docker runtime checks were rerun for this correction; earlier Docker verification is historical, not verification of this revision.
- Official sample now has one explicit same-local-night buffer ambiguity (A001/A007, week 22), instead of 36 unsupported protection-slot capacity failures. The official CSVs were not changed.
- Regenerated CSVs and ZIP contain current work-only supply accounting and safety-coverage diagnostics. API `location_usage.used` and the UI both show work possessions only.

## Public run after correction

| Scenario | First validated solution | Final score | Primary model optimum proved |
| --- | ---: | ---: | --- |
| A | 9.39 s | 25.2 | Yes |
| B | 6.00 s | 30 | Yes |
| C | 10.34 s | 25.2 | Yes |

All 54 activities meet the requested workload. A and C each have 21 contract-overrun days across two contracts; B has zero delay and six ECLO nights. All scenarios have zero excess work possessions. Peak process memory was 1034.32 MiB. C's total run including extraction and validation took 30.30 s; the search budget is not a strict wall-clock response guarantee. Exact environment and timing are in `submission/public-results/benchmark.json`.

Before this correction A scored 40.6 with 35 contract-overrun days across four contracts under the previous protection-reservation policy. The new result uses a different constraint interpretation, so this is a policy correction, not evidence of beating the old model at its own objective.

## Known compatibility and scaling boundaries

The official executable validator is unavailable. Comparable contract/type-local nights are checked; network-wide physical timing across contracts remains unverified. Potential cross-contract intersections are exposed in the validation report, not certified safe. One organizer-sample buffer-sharing interpretation remains unresolved. Model optimality is not official benchmark optimality. See `validator-spec.md` and `compatibility_report.json`.

`stress_benchmark.json` and the `previous_*` compatibility entries are historical measurements of `local-protection-reservations-v1`, not measurements of this revision. The earlier doubled-demand probe found no result within 30 seconds; current larger-instance performance has not been remeasured. Location-local pattern enumeration still scales combinatorially.

Manual browser verification remains necessary when a browser becomes available: load public data, observe improving revisions, filter activities/contracts/lines, toggle timeline/table, inspect protection and shared memberships, filter location/week usage, cancel while retaining output, and verify desktop/mobile layout and downloads.


## Main integration audit

Remote main added alternative search methods and 30 synthetic datasets while
this safety update was in progress. Both feature sets are retained. The alternative
worker now revalidates every candidate with the current application CSV validator
before publication, in addition to any strategy-specific checks.

The 30 historical dataset witnesses are preserved unchanged. Only 3 pass the v3
physical-night rules; 27 are negative safety fixtures under this policy. Their
exact current diagnostics are recorded in
`benchmarks/dataset-suite/current-validation.json`. Historical witness feasibility
and benchmark averages must not be presented as v3 validation results.

Integration verification: 122 backend tests passed (three public full-search tests
excluded); frontend type generation, TypeScript and production build passed.
