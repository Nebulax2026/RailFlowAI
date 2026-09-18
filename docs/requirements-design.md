# PS1 engine and judging workspace

## Data flow

Eight UTF-8 CSVs -> structural/reference/topology checks -> CP-SAT -> official CSV bytes -> independent validation -> immutable published solution revision -> evidence UI/downloads. Inputs are held in memory with a 60-minute TTL. The local data model and the three official CSV headers remain compatible.

Input validation covers row width, missing fields, enum/boolean/date/integer values, duplicate identifiers/parameters, connected station/sector order, supply topology, matching activity/contract types and valid endpoints. Zero supply is accepted. Cycles are detected iteratively, including cross-contract links. Empty contracts are rejected because no completion date can be calculated.

## Search

Activity/week access and ECLO are decisions. Local contract night variables enforce workfronts. Complete workload, strict-week precedence, scenario deadlines, per-line ECLO continuity, location-local possession patterns, work supply and cross-contract physical-night safety are jointly enforced. Explicit group patterns replace approximate weighted packing. See `validator-spec.md` for the physical-night model and the format-only sample classification.

One worker performs A/B/C first searches (30 seconds each), then non-optimal scenarios receive up to 90 seconds each using validated incumbent hints. Model building counts toward the budget; construction checks and an active StopSearch monitor support cancellation. Native solver shutdown and export validation can add a small overhead. No date horizon extension or dropped workload is permitted. A mathematically infeasible instance cannot be promised a solution; time limit, infeasibility, cancellation, validation failure and unexpected error are distinguished.

Each improving candidate is serialized and checked before publication. Only a strictly lower verified score replaces a published revision. Equal-score results can update bounds/status without changing CSVs. Optimal means the documented model's primary optimum is proved. Early placement is optimized only with that optimum fixed.

## API additions

Existing job/scenario/download routes are preserved. Job scenario states add `phase`, `termination_reason`, `solution_revision`, `solver_stats`, and `scores`. Phases are queued, first_search, waiting_improvement, improving, finished. Statistics include elapsed/first-feasible seconds, best score/bound, relative gap, model variables, search workers and process peak memory when available.

Scenario detail is available as soon as a validated incumbent exists, even while running. It adds `score_breakdown` and `activity_details` (workload, dates, predecessor completion, local nights, co-workers, protection footprint and possession memberships). Diagnostics do not infer counterfactual causes of delay.

File downloads accept optional `revision`; stale revisions receive 409 instead of silently downloading a different result. ZIPs contain only validated scenarios, `validation_summary.json`, and a manifest listing scenarios/revisions. Cancellation retains existing results. Expiry deletes results and cancels queued/running work.

## Workspace

The UI compares A/B/C completion, overrun, excess work slots, ECLO, score and search status. Revision-aware polling retrieves improvements and ignores responses from an old job. Filters select contract, activity or line. Activities have a timeline and table, actual dates, workload, predecessor, shared peers, work/buffer/opposite-bound/interchange lists and per-location memberships. A separate location/week table exposes work usage and informational protection footprints and related activities. Only internal validation is claimed.

AI Agent Mode places policy comparison beside Copilot. Gemini generates conversational replies, calling read-only schedule tools for Bonus queries and a draft tool for proposed disruptions. Tool evidence and recent conversation are sent to Vertex AI; provider failures are visible instead of silently returning template answers. Drafts lead to short-lived previews bound to the job, scenario and baseline revision. Only the explicit Run validated re-plan control starts the solver. Validation and the disruption audit gate successful revised output. See ps1-schedule-copilot.md for available tools and limitations.

## Acceptance and reproducibility

Tests include mutated exports, handwritten safety footprints, legal sharing/separate slots, ECLO precedence compression, independent tiny-instance objective enumeration, cancellation, partial failure, expiry, revision downloads and ZIP contents. Public generation runs the same search policy and records platform/timing/gap. Seed-42 congestion and doubled-demand probes record failures as well as successes.

CI runs pytest, TypeScript/build, and Docker build. Production static assets and API use one origin. `RAILFLOW_STATIC_DIR` optionally selects a prebuilt static export for local single-origin checks; Docker defaults to its bundled static directory.
