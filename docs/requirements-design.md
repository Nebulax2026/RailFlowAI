# RailFlowAI PS1 Requirements and Technical Design

## Product Goal

RailFlowAI is a decision-support workspace for an access planner or works controller. A user uploads an undisclosed PS1 instance, runs the three policy scenarios, inspects why work was placed or delayed, and downloads mechanically valid submission files.

Success means every activity workload is scheduled, every exported file has the official schema, no published hard rule is violated, and the policy trade-off is visible without reading solver logs.

## Authoritative Inputs

The application accepts exactly the eight files listed in the root README. Headers must match the published schema and identifiers must be unique. Cross-file validation covers lines, stations, sectors, locations, contracts, activities, predecessors, buffer rules, dates, bounds, priorities, capacities, workfronts, and weekly access limits.

Limits are 2 MB per file and 16 MB per batch. Inputs must be UTF-8. A failed batch returns row/file-oriented errors and never creates a solve job.

DataMall is not a solver input. The fictional Alpha/Beta network cannot be mapped safely to real Singapore line and station codes.

## Topology and Scheduling Semantics

- An activity's sector endpoints must share line and bound.
- Expansion includes every sector from the first endpoint through the last and every platform at the stations traversed, including endpoints.
- An activity receives at most one access occurrence per week.
- `access_night` is local to contract, activity type, and week and is bounded by the contract's weekly allocation.
- Concurrent occurrences on one local access night cannot exceed the contract's workfront count.
- `PM` occupies a possession alone. A `PC` can share with up to three `C` activities. Remaining `C` activities pack four per possession.
- Every activity occurrence emits occupancy for its complete expanded span. Co-sharing labels are deterministic within each location-week.
- Predecessor activities must complete in an earlier week. Links may cross contracts, but the predecessor graph must be acyclic.
- A standard occurrence contributes 1.0 workload; ECLO contributes 1.5.

The implementation is deliberately conservative where the brief is ambiguous. The internal validator is independent of CP-SAT variables and re-parses the final CSVs.

## Scenario Policies

### Scenario A

Nominal `LOCATION_SUPPLY` is hard. ECLO is forbidden. The objective minimizes planned-completion overrun with contract-priority weighting and earlier placement as a deterministic tie-breaker.

### Scenario B

Planned completion dates are hard. Capacity may exceed nominal supply. The solver introduces only the minimum ECLO compression needed to fit an activity between planned start and completion. The objective is `7 * excess access nights + 5 * ECLO nights`.

### Scenario C

Each location-week may use at most one possession above nominal capacity. The objective combines priority-weighted overrun, excess access nights, and ECLO. If ECLO is used, each affected line's ECLO weeks must fit one continuous two-week window; cross-line Live work affects both windows.

## Job Lifecycle and API

`POST /api/ps1/jobs` accepts eight multipart fields named `files`. `public=true` loads the bundled dataset. It returns HTTP 202 with instance counts and scenario states.

Jobs move through `queued`, `running`, `completed`, `failed`, or `cancelled`. Each scenario has its own status, progress, message, feasibility, and objective score. A single worker protects hosted CPU capacity. Cancellation is cooperative between scenario solves. Jobs expire after 60 minutes.

Scenario detail contains validation, explanations, contract results, access rows, and occupancy rows. CSV and ZIP endpoints are available only for internally feasible scenarios.

## Workspace Requirements

The first screen is the working product, not a landing page. It provides:

- Eight-file checklist, drag-and-drop, and public-data action.
- A/B/C progress and cancellation.
- Scenario score, overrun, excess supply, and ECLO metrics.
- Weekly access chart, capacity hotspots, contract completion table, and explanations.
- Individual CSV and combined ZIP downloads.
- DataMall service status with explicit separation from scheduling inputs.
- Responsive layouts for desktop and mobile without overlapping controls or clipped labels.

## Operational Requirements

- Uploaded data remains in process memory and expires after 60 minutes.
- AccountKey remains server-side.
- API errors must not expose secrets or uploaded rows in logs.
- The Docker image serves static frontend assets and API from one origin.
- `/api/health` is the deployment health check.
- CI runs backend tests, frontend type checking/build, and Docker build.

## Acceptance Criteria

- The public instance parses and all 54 activities and 192 requested access units are represented.
- The supplied Scenario A sample validates with zero hard violations.
- Generated A/B/C outputs re-parse with exact headers and zero internal hard violations.
- Scenario A has zero ECLO and zero capacity excess.
- Scenario B has zero planned-date overrun.
- Scenario C never exceeds its one-possession elasticity and enforces ECLO continuity when used.
- The combined ZIP has three scenario directories and `validation_summary.json`.
- The production container supports the complete public-data workflow from one public origin.
