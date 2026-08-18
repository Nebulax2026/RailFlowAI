# RailFlowAI Requirements And Design

## 1. Product Overview

RailFlowAI is an explainable railway maintenance scheduling tool for planning maintenance, upgrades, inspections, and emergency work inside limited engineering windows. Railway assets need constant work while train services leave limited closure capacity, so requests often compete for the same track sectors, crews, equipment, and sequencing prerequisites.

The product goal is to automate the tedious coordination step: validate incoming maintenance requests, place conflict-free work tentatively, generate manager-reviewed rescheduling proposals when clashes occur, explain conflicts and schedule movement clearly, and let a Schedule Manager approve selected tentative work into the locked operational baseline.

RailFlowAI is a web-first, human-in-the-loop decision support system. The scheduler proposes valid options, but operational release remains a Schedule Manager decision.

### MVP User Model

The MVP uses two lightweight roles with shared visibility: Requester and Schedule Manager. There are no required separate Field Technician, Maintenance Planner, and Operations Manager roles.

Requester users can:

- Create maintenance requests.
- View proposed slots for their own requests.
- View schedules, conflicts, proposals, explanations, and KPIs.
- Generate and compare proposal options.
- Import CSV or JSON seed/demo data.

Schedule Manager users can do everything a Requester can do, plus:

- Apply selected rescheduling proposals.
- Approve selected tentative scheduled work.
- Modify scheduled work.
- Reject requests or scheduled decisions.
- Finalize operational work by approval.

Manual Lock and Unlock endpoints may remain for compatibility or admin use, but they are not the primary MVP workflow. In the product UI, approval is the release/baseline action.

The app should describe workflows as product areas, not permission roles:

- New Request
- Planning Board
- Decision Review
- Proposal Options
- KPI Dashboard

Role behavior stays simple in the MVP. Everyone can see the same operational information, while final scheduling authority belongs to the Schedule Manager.

## 2. Functional Requirements

### Request Creation

Users must be able to submit a maintenance request from the web interface. A request must capture enough information for validation, conflict detection, direct placement, and proposal generation.

Required request fields:

- `title`
- `track_sector`
- `work_type`
- `duration_minutes`
- `earliest_start`
- `deadline`
- `priority`

Fields with predefined accepted values:

- `track_sector`: `T08`, `T09`, `T10`, `T11`, `T12`, `T13`, `T14`
- `work_type`: `inspection`, `electrical`, `track`, `signal_replacement`, `signal_test`, `track_inspection`, `track_renewal`, `power_isolation`, `electrical_repair`, `safety_clearance`, `service_restore`, `emergency`
- `priority`: `1`, `2`, `3`, `4`, `5`
- `required_crew`: `E1`, `E2`, `TG1`, `TG2`, `MECH1`, `MECH2`, `SIG1`, `SIG2`, `SAFE1`
- `required_equipment`: `SignalKit-1`, `SignalKit-2`, `GeometryCar-1`, `GeometryCar-2`, `PowerUnit-1`, `PowerUnit-2`, `DiagnosticKit-1`, `RailGrinder-1`, `IsolationKit-1`

Optional request fields:

- `required_crew`
- `required_equipment`
- `dependencies`
- `incompatible_work_types`
- `locked`
- `fixed_start`
- `fixed_end`
- `duration_variance_percent`
- `notes`
- `source`
- `created_by`

When a request is submitted, the system validates hard blockers first.

If the requested slot fits the current active schedule:

- The request is stored.
- A tentative `ScheduledWork` block is created immediately at the requested start.
- The response shows the assigned slot as `scheduled_work`.
- The request does not appear in the Request Queue because it is already placed on the calendar.

If the requested slot conflicts but could fit by moving upcoming work:

- The request remains pending and visible in the Request Queue.
- The active schedule is not mutated during request submission.
- The response shows conflicts, affected changes, and a manager-reviewed proposal option.
- The proposal may move upcoming tentative or locked/approved work, but only after Schedule Manager application.

If the request violates hard validation:

- The API returns `422`.
- The request is not queued and no schedule block is created.

The request result must include:

- `request`
- `fits_current_schedule`
- `conflicts`
- `suggested_alternatives`
- `scheduled_work`
- `requires_manager_review`
- `affected_changes`
- `proposal_option`

### Validation

The system validates both schema rules and scheduling rules before a request can be treated as schedulable.

Validation checks:

- Required fields are present.
- Duration is greater than zero.
- Priority is within the supported range.
- Earliest start is before the deadline.
- Fixed start and fixed end are valid when a request is seeded as locked.
- Work types with predefined prerequisites can be requested only when prerequisite work is already scheduled on the same track sector.
- Engineering-hour and prerequisite failures are hard blockers for request intake.

The standard visible planning day is 06:00-22:00. The normal engineering window is 09:00-18:00; work outside that range is allowed as overtime for scheduling impact, not treated as a resource conflict.

Predefined MVP prerequisites:

- Signal Test requires Signal Replacement.
- Track Renewal requires Track Inspection.
- Electrical Repair requires Power Isolation.
- Service Restore requires Safety Clearance.

### Conflict Detection

The system detects resource conflicts between requested or scheduled work. Conflicts are resolvable scheduling clashes that can produce proposal options.

Conflict types:

- Track sector overlap
- Crew double-booking
- Equipment double-booking
- Safety incompatibility from request `incompatible_work_types`

Engineering-hour and dependency/prerequisite failures are not conflicts. They are hard validation blockers and must be rejected before scheduling.

Each conflict must have:

- Type
- Severity
- Affected request IDs
- Affected resource, when applicable
- Time overlap, when applicable
- Plain-English explanation
- Suggested action, when available

### Proposal Generation

If the requested slot cannot fit the current schedule, RailFlowAI generates ranked proposal options by default.

Default behavior:

- Generate up to 2-3 ranked feasible proposal options.
- Scope proposal generation to selected pending request IDs when the user has selected pending requests in the Request Queue.
- Otherwise, backend compatibility may allow whole-board proposal generation.
- Score every proposal across a balanced set of criteria instead of exposing one-criterion scheduling modes as the primary UX.

Each proposal must show:

- Scheduled work candidate
- Changed jobs
- Moved locked jobs
- Unresolved conflicts
- Estimated overtime
- Engineering-hours utilisation
- Schedule stability
- Robustness score
- Disruption score
- Overtime score
- Completion score
- Critical-priority score
- Overall score
- Churn penalty
- Plain-English explanation
- Impact summary

Proposals should be shown when:

- A newly submitted request does not fit the current schedule.
- A user selects pending Request Queue items and chooses Show Proposals.
- An emergency scenario requires rescheduling existing approved work.

Applying a proposal mutates the active working schedule only after Schedule Manager authorization. Any moved previously locked work becomes tentative at the new slot and must be approved again.

### Decision Review

Users must be able to review what is selected, why a request did not fit, and what a selected proposal changes.

The Decision Review experience must support:

- Showing selected pending request IDs and requested windows.
- Showing selected tentative or locked calendar tasks and scheduled windows.
- Viewing conflict reason.
- Viewing affected requests and owners.
- Viewing suggested movement.
- Viewing KPI/proposal impact.
- Comparing proposal options.
- Requesters can view recommendations and understand impact.
- Schedule Managers can apply proposals.
- Schedule Managers can approve selected tentative calendar tasks.
- Schedule Managers can modify or reject selected work where supported.

### Schedule Approval

Approval remains human-in-the-loop. The system can recommend and tentatively place work, but it must not silently finalize operational changes.

Approval behavior:

- Pending unscheduled requests cannot be approved directly.
- Only a Schedule Manager can apply proposals, approve selected work, reject, or modify schedule decisions.
- `Approve Selected` approves only selected tentative scheduled tasks.
- If no tentative calendar task is selected, `Approve Selected` is disabled.
- Approval locks the selected tentative scheduled work.
- Moved locked work becomes tentative after proposal application and must be approved again.
- Locked work is preserved during normal optimization.
- Manager-reviewed proposals may move upcoming locked work, but movement is penalized and not applied silently.

### Dashboard KPIs

The dashboard shows the highest-signal operational KPIs for the current active schedule and selected proposal preview.

Visible MVP KPIs:

- Open Conflicts
- Window Utilisation
- Estimated Overtime
- Schedule Stability

The backend model may also calculate:

- Critical Jobs Scheduled
- Robustness Score

### CSV And JSON Import

CSV and JSON import are secondary inputs for seed data, official hackathon datasets, and legacy integrations.

Import must pass through adapters before entering the scheduling pipeline:

```text
CSV / JSON / Official Dataset
        ->
Adapter Layer
        ->
Internal Request Model
        ->
Validation
        ->
In-Memory Request Store
        ->
Scheduling / Proposal Workflow
```

The adapter layer normalizes external data into the same internal model used by manual web requests. CSV and JSON preview/confirm endpoints validate imported rows before they enter `REQUESTS`.

Demo seed/reset endpoints load or clear deterministic in-memory state for hackathon walkthroughs.

### Sample Data Columns

The sample CSV intentionally includes more columns than a normal requester must provide. The extra columns create deterministic demo scenarios with tentative, pending, and locked work.

Minimum required import columns:

- `Request ID`
- `Title`
- `Track Sector`
- `Work Type`
- `Duration Minutes`
- `Earliest Start`
- `Deadline`
- `Priority`

Useful scheduling columns:

- `Required Crew`
- `Required Equipment`
- `Dependencies`
- `Incompatible Work Types`

Demo-state columns:

- `Approval Status`
- `Locked`
- `Fixed Start`
- `Fixed End`

Narrative/debug columns:

- `Notes`

`Approval Status`, `Locked`, `Fixed Start`, and `Fixed End` are not required for ordinary new requests. They are useful for seeding an existing planning board with already tentative or locked work. If those columns are absent, imports should default to pending draft requests unless the API payload explicitly provides scheduling state.

## 3. Scheduling And Proposal Design

### Scheduling Pipeline

The core direct-fit pipeline is:

```text
Request Created
        ->
Hard Validation
        ->
Requested Slot Conflict Check
        ->
Tentative Calendar Placement
        ->
Requester Sees Proposed Slot
        ->
Schedule Manager Approves Selected Tentative Work
        ->
Locked Operational Baseline
```

The reschedule-needed pipeline is:

```text
Request Created
        ->
Hard Validation
        ->
Requested Slot Conflict Check
        ->
Pending Request Queue
        ->
Selected Pending Requests
        ->
Show Proposals
        ->
Decision Review With Affected Changes
        ->
Schedule Manager Applies Proposal
        ->
Changed Work Becomes Tentative
        ->
Schedule Manager Approves Selected Tentative Work
        ->
Locked Operational Baseline
```

### Hard Constraints

Hard constraints must not be violated in a valid active schedule:

- Work starts no earlier than `earliest_start`.
- Work ends no later than `deadline`.
- The same crew cannot be assigned to overlapping work.
- The same equipment cannot be assigned to overlapping work.
- The same track sector cannot host incompatible overlapping work.
- Safety incompatibilities declared through `incompatible_work_types` must be respected.
- Dependencies and predefined prerequisites must be satisfied.
- Active schedules must be conflict-free before approval.

Locked work is fixed during normal optimization. In manager-reviewed rescheduling proposals, locked upcoming work may be proposed for movement, but movement is penalized, shown explicitly, and only applied by a Schedule Manager. Once moved, that work becomes tentative until approved again.

If a hard constraint cannot be satisfied, the schedule candidate must not be treated as a valid approval-ready schedule.

### Soft Objectives

Soft objectives determine which valid schedule is preferred:

- Minimize movement of already approved work.
- Minimize overtime.
- Minimize delays to critical work.
- Maximize completed jobs.
- Minimize total track closure time.
- Minimize resource movement.
- Preserve schedule stability.
- Improve robustness against duration variance.

### Proposal Ranking

Proposal options use the same hard constraints and are ranked with a balanced score across:

- Disruption: prefer fewer moved jobs.
- Overtime: prefer no overtime or deadline pressure.
- Completion: prefer scheduling all selected valid requests.
- Critical priority: prefer preserving high-priority work.
- Churn: penalize moving locked or near-term work.

The UI should show the top feasible proposals with score summaries, changed-job counts, moved-locked counts, conflicts, and churn penalty.

### No Valid Schedule Fallback

If no valid schedule exists, the system must not pretend that a schedule is valid.

The system must return:

- The blocking conflicts or hard blockers.
- The requests that prevent feasibility.
- The hard constraints that could not be satisfied.
- The closest available proposals, clearly marked as unresolved if conflicts remain.
- Suggested user actions, such as changing deadline, extending the allowed window, reducing duration, changing crew/equipment, approving overtime, or rejecting the request.

## 4. UX Requirements

### Shared Navigation

Navigation should be mostly shared across both roles. Preferred MVP labels:

- New Request
- Planning Board

Requester users should see decision actions as read-only or unavailable. Schedule Manager users should see proposal application, approval, modify, and reject actions.

### New Request Screen

The New Request screen must allow users to enter maintenance work details and submit the request for validation.

After submission:

- If the request fits, show "Your proposed slot" with start/end time.
- If the request requires rescheduling, show that manager review is required and list affected moved tasks/owners.
- If validation fails, show backend hard-blocker messages.

### Planning Board

The Planning Board makes monthly workload and the selected day's execution schedule visible without forcing users into a dense full Gantt first.

The Planning Board must show:

- KPI summary.
- Monthly calendar view with count of scheduled work per day.
- Conflict marker on days that contain conflicting work.
- Selected-day schedule with vertical time and horizontal track sectors.
- Request Queue containing only unscheduled pending requests.
- Tentative and locked calendar tasks.
- Conflict indicators.
- Decision Review panel.
- Proposal Options in Decision Review when proposals are generated.

The visible day schedule should show 06:00-22:00 with 09:00-18:00 treated as the standard working window for overtime calculation.

### Selection Behavior

The dashboard supports multi-select:

- Request Queue items can be selected as pending requests.
- Calendar tasks can be selected as tentative or locked scheduled work.
- Decision Review lists the actual selected items, not only counts.
- Show Proposals is enabled only when pending requests are selected.
- Apply Proposal is enabled only when a proposal exists and pending requests remain selected.
- Approve Selected is enabled only when selected calendar tasks include tentative work.

### Decision Review Panel

The Decision Review panel must explain:

- Which pending requests are selected.
- Which calendar tasks are selected.
- Which conflicts or blockers are active.
- Which tasks a proposal moves.
- Which owners are affected.
- Which proposal option is being shown.
- How the proposal changes schedule stability, overtime, and disruption.

Available primary actions:

- Show Proposals
- Apply Proposal, Schedule Manager only
- Approve Selected, Schedule Manager only
- Modify, Schedule Manager only
- Reject, Schedule Manager only

Lock and Unlock are not primary UI actions. Approved work is changed through proposal application, which makes moved work tentative again.

## 5. Technical Design

### Backend Baseline

The current backend structure is the baseline:

```text
backend/app/
  adapters/
  api/
  conflict/
  domain/
  explanation/
  kpi/
  scheduler/
  stress/
  validation/
```

The backend should keep adapters, validators, conflict detection, scheduling, KPI calculation, and explanations as separate modules.

### Public API Baseline

Required API endpoints:

- `POST /api/requests`
- `GET /api/requests`
- `PATCH /api/requests/{id}`
- `POST /api/import/preview`
- `POST /api/import/confirm`
- `POST /api/import/json/preview`
- `POST /api/import/json/confirm`
- `POST /api/conflicts/detect`
- `POST /api/schedule/optimise`
- `POST /api/schedule/alternatives`
- `POST /api/schedule/apply`
- `POST /api/schedule/approve`
- `POST /api/schedule/approve-selected`
- `POST /api/schedule/reject/{request_id}`
- `PATCH /api/schedule/modify/{request_id}`
- `GET /api/kpis`
- `POST /api/demo/seed`
- `POST /api/demo/reset`

Compatibility or later endpoints:

- `POST /api/schedule/lock/{request_id}`
- `POST /api/schedule/unlock/{request_id}`
- `POST /api/scenarios/emergency`
- `POST /api/stress-test`

### Domain Models

The current domain models are the baseline:

- `MaintenanceRequest`
- `ScheduledWork`
- `Conflict`
- `KpiSnapshot`
- `ScheduleAlternative`
- `RequestFitResponse`
- `ScheduleChange`

### Fit Status Contract

Request submission returns a fit-status response.

Recommended response shape:

```json
{
  "request": {},
  "fits_current_schedule": false,
  "conflicts": [],
  "suggested_alternatives": [],
  "scheduled_work": null,
  "requires_manager_review": true,
  "affected_changes": [],
  "proposal_option": null
}
```

When `fits_current_schedule` is `true`, `scheduled_work` contains the tentative calendar block and `requires_manager_review` is `false`.

When `fits_current_schedule` is `false`, `suggested_alternatives` should include feasible proposal options when possible, `requires_manager_review` is `true`, and `affected_changes` should identify moved owners and before/after windows.

### Proposal And Approval Contracts

`POST /api/schedule/alternatives` accepts:

```json
{
  "request_ids": ["M-102", "M-109"]
}
```

When `request_ids` is provided, proposals must include those pending requests while preserving constraints for active scheduled work. Unselected pending requests remain queued.

`POST /api/schedule/apply` applies the selected proposal/candidate for selected pending request IDs. Applying a proposal schedules the selected pending requests and any affected changed work as tentative, except unchanged locked work remains locked.

`POST /api/schedule/approve-selected` accepts:

```json
{
  "request_ids": ["M-102", "M-109"]
}
```

It approves/locks only selected scheduled tentative work. It rejects unscheduled pending IDs.

`POST /api/schedule/approve` remains available as a backend compatibility action to approve all active tentative scheduled work.

### Authorization Boundary

The MVP role boundary is intentionally small and implemented through query/body role fields rather than production authentication.

Requester permissions:

- Create requests.
- View schedules, conflicts, proposals, explanations, and KPIs.
- Generate proposal previews.

Schedule Manager permissions:

- Create and edit requests.
- Apply proposals.
- Approve selected scheduled work.
- Reject or modify schedule decisions.
- Finalize schedules.

Full authentication, audit trails, and production-grade access control are future enhancements.

### Scheduler Boundary

The scheduling engine is responsible for constraint satisfaction and objective optimization.

The scheduler must:

- Accept normalized `MaintenanceRequest` records.
- Preserve locked work during normal optimization.
- Allow manager-reviewed proposal generation that can move upcoming locked work with penalty.
- Respect hard constraints.
- Apply selected objective/profile behavior.
- Return `ScheduledWork` records.
- Mark changed work with `changed_from_original`.
- Provide enough change context for explanations.

The scheduler is implemented as an OR-Tools CP-SAT interval-variable model behind the scheduler API. Locked work is modeled as mandatory fixed intervals; movable requests are optional intervals whose presence the solver decides. Track sector, crew, and equipment each get a `NoOverlap` constraint; dependencies enforce hard ordering; the objective maximizes scheduled (priority-weighted) work first and then applies the selected profile's disruption, overtime, priority-delay, and horizon-based move-penalty weights as tie-breakers. The solver runs single-threaded with a fixed seed so seeded demo runs are reproducible, and its time limit is configurable via `RAILFLOW_CP_SAT_TIME_LIMIT_SECONDS`. If the locked baseline itself is infeasible (e.g. two locked jobs contend for the same resource), the solver raises `SchedulingInfeasibleError` with the conflicting requests so the API can return actionable blocker details instead of a silently broken schedule.

### Explanation Boundary

The explanation layer translates scheduler and conflict outputs into user-facing reasons.

Explanations must include:

- What changed.
- Why it changed.
- Which conflict was resolved.
- Which tasks and owners were affected.
- Which KPI improved or worsened.

Constraint logic decides schedules. LLM usage is optional and must only polish wording or summarize already-computed facts.

## 6. Demo Scenarios

### Demo 1: Direct Fit Request

1. User creates a maintenance request whose requested slot is free.
2. System validates the request.
3. System creates a tentative scheduled block immediately.
4. Requester sees "Your proposed slot" with start/end time.
5. Schedule Manager selects the tentative calendar task and approves it.

### Demo 2: Selected Pending Request Proposal

1. User submits a request that conflicts with scheduled work.
2. System leaves the request in the Request Queue and returns manager-review proposal details.
3. Schedule Manager selects one or more pending requests.
4. Schedule Manager chooses Show Proposals.
5. System generates ranked proposals and lists affected moved tasks/owners.
6. Schedule Manager applies a selected proposal.
7. Changed work becomes tentative and is approved with Approve Selected.

### Demo 3: Locked Work Revision

1. Seed data includes locked approved work and tentative work.
2. A selected pending request can fit only if upcoming work moves.
3. System proposes movement and penalizes moving locked work.
4. Schedule Manager reviews affected owners and before/after windows.
5. Schedule Manager applies the proposal.
6. Moved previously locked work becomes tentative and must be approved again.

### Demo 4: Emergency Rescheduling

1. User adds an emergency maintenance request.
2. System detects conflicts with existing scheduled work.
3. System generates ranked feasible proposals.
4. Existing work is moved only where necessary and explicitly listed.
5. User reviews schedule stability and explanation.
6. Schedule Manager applies or rejects the emergency reschedule.

## 7. Test And Acceptance Criteria

### Requirement Review

- The MVP is described as two lightweight roles with shared visibility.
- Requesters can create requests and view schedules, conflicts, proposals, explanations, and KPIs.
- Direct-fit requests create tentative scheduled work.
- Conflicting requests remain in the unscheduled Request Queue.
- Schedule Managers can apply proposals and approve selected tentative work.
- Manual lock/unlock is not the primary product workflow.

### Scheduling Scenarios

- Original request fits with no conflicts and appears on the calendar as tentative.
- Original request conflicts with track availability.
- Original request conflicts with crew availability.
- Original request conflicts with equipment availability.
- Engineering-hour and prerequisite failures return hard validation blockers.
- Selected pending requests generate feasible proposals when possible.
- Applying proposals schedules selected pending requests as tentative.
- Moved locked work becomes tentative after proposal application.
- Approval locks only selected tentative scheduled work.
- No-valid-schedule cases return explicit blockers.

### Acceptance Criteria

- Proposals are shown when needed or when selected pending requests request comparison.
- Every conflict has a visible reason.
- Every proposal includes KPI impact, score context, changed jobs, and explanation.
- Only a Schedule Manager can apply, approve, modify, or reject schedule decisions.
- Requesters can still view proposed schedules and explanations.
- Pending requests cannot be approved directly.
- The system does not claim an invalid schedule is conflict-free.

## 8. Future Enhancements

- More detailed role permissions beyond Requester and Schedule Manager.
- Official dataset enrichment, including MRT station or sector metadata.
- Import UI for CSV and JSON files.
- Schedule export.
- Audit history for schedule decisions.
- Robustness stress testing.
- Natural-language explanation polish.
- Richer optimization profiles.
- Multi-user collaboration.
- Authentication and production security.
- Cloud database persistence.

## 9. Assumptions

- This document is the single PRD + technical design source for the MVP.
- MVP has two lightweight roles: Requester and Schedule Manager.
- Everyone has shared visibility into schedules, conflicts, proposals, explanations, and KPIs.
- Only Schedule Managers can finalize schedule decisions.
- Direct-fit requests may be tentatively placed immediately.
- Conflicting requests stay pending until a proposal is applied.
- Proposal generation uses balanced named options by default.
- Storage remains in memory for the MVP.
- The backend API and domain models currently in the repo are the baseline unless later implementation work changes them.
