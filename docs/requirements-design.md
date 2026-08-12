# RailFlowAI Requirements And Design

## 1. Product Overview

RailFlowAI is an explainable railway maintenance scheduling tool for planning maintenance, upgrades, inspections, and emergency work inside limited engineering hours. Railway assets need constant work while train services leave only short closure windows, so schedule requests often compete for the same track sectors, crews, equipment, and safety conditions.

The product goal is to automate the tedious coordination step: collect valid pending requests, generate feasible schedule candidates for the batch, explain resource contentions clearly, and let a Schedule Manager approve and lock the final schedule.

RailFlowAI is a web-first, human-in-the-loop decision support system. The scheduler engine proposes valid options, but the user remains responsible for accepting, modifying, rejecting, or locking schedule decisions.

### MVP User Model

The MVP uses two lightweight roles with shared visibility: Requester and Schedule Manager. There are no required separate Field Technician, Maintenance Planner, and Operations Manager roles.

Requester users can:

- Create maintenance requests.
- Edit requests they have submitted before approval.
- View the schedule dashboard.
- Detect and review conflicts.
- Generate and compare alternative schedules.
- Review explanations and KPI impact.
- View dashboard KPIs.
- Import CSV or JSON seed/demo data.

Schedule Manager users can do everything a Requester can do, plus:

- Edit any submitted request.
- Accept, modify, or reject suggested schedules.
- Approve final schedules.
- Lock scheduled work.
- Unlock scheduled work when rescheduling is required.

The app should describe workflows as product areas, not permission roles:

- New Request
- Planning Board
- Decision Review
- Alternatives
- KPI Dashboard

Role behavior should stay simple in the MVP. Everyone can see the same operational information, while final scheduling authority belongs to the Schedule Manager.

## 2. Functional Requirements

### Request Creation

Users must be able to submit a maintenance request from the web interface. A request must capture enough information for validation, conflict detection, and scheduling.

Submitted requests enter a pending queue. They are not automatically inserted into the active schedule one by one.

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

When a request is submitted, the system must validate that the request is allowed to enter the pending queue.

The request result must include or trigger:

- `fits_current_schedule`
- `conflicts`
- `suggested_alternatives`, when the original request does not fit

For the MVP batch workflow, request creation primarily confirms that the request is valid and queued. Feasibility and alternatives are generated when the user runs the batch schedule action.

### Validation

The system must validate both schema rules and scheduling rules before a request can be treated as schedulable.

Validation must check:

- Required fields are present.
- Duration is greater than zero.
- Priority is within the supported range.
- Earliest start is before the deadline.
- Fixed start and fixed end are valid when a request is locked.
- The request is compatible with engineering-hour windows.
- Work types with predefined prerequisites can be requested only when prerequisite work is already scheduled on the same track sector.

Predefined MVP prerequisites:

- Signal Test requires Signal Replacement.
- Track Renewal requires Track Inspection.
- Electrical Repair requires Power Isolation.
- Service Restore requires Safety Clearance.

### Resource Contention Detection

The system must detect resource contentions between requested or scheduled work. Resource contentions are resolvable scheduling clashes that can produce alternative schedule options.

Contention types:

- Track sector overlap
- Crew double-booking
- Equipment double-booking
- Safety incompatibility

Engineering-hours violations and dependency/prerequisite failures are not contentions. They are hard validation blockers and must be rejected before scheduling.

Each contention must have:

- Type
- Severity
- Affected request IDs
- Affected resource, when applicable
- Time overlap, when applicable
- Plain-English explanation
- Suggested action, when available

### Alternative Schedule Generation

If the original request cannot fit the current schedule, RailFlowAI must generate alternative schedule options by default.

Default behavior:

- Generate 2-3 ranked feasible alternatives.
- Include Requested Slot as an alternative when hard validation passes.
- Score every alternative across all four criteria instead of making separate one-criterion modes.

Each alternative must show:

- Scheduled work
- Changed jobs
- Unresolved resource contentions
- Estimated overtime
- Engineering-hours utilisation
- Schedule stability
- Robustness score
- Disruption score
- Overtime score
- Completion score
- Critical-priority score
- Overall score
- Plain-English explanation

Alternatives should be shown when:

- A newly submitted request does not fit the current schedule.
- The user explicitly asks to compare schedule options.
- An emergency scenario requires rescheduling existing approved work.

### Decision Review

Users must be able to review why the original request did not fit and compare suggested alternatives.

The decision review experience must support:

- Viewing conflict reason.
- Viewing affected requests.
- Viewing suggested movement.
- Viewing KPI impact.
- Comparing alternative options.
- Requesters can view recommendations and understand impact.
- Schedule Managers can accept a recommendation.
- Schedule Managers can modify a recommendation.
- Schedule Managers can reject a recommendation.
- Schedule Managers can lock scheduled work.

### Schedule Approval

Approval must remain human-in-the-loop. The system can recommend a schedule, but it must not silently finalize schedule changes.

Approval behavior:

- Only a Schedule Manager can approve, reject, modify, lock, or unlock schedule decisions.
- A schedule can be approved only when unresolved conflicts are acceptable to the Schedule Manager or reduced to zero.
- Approved work should be eligible for locking by a Schedule Manager.
- Locked work should be preserved by future optimisation runs unless a Schedule Manager unlocks it.
- New requests should accumulate in the pending queue and be scheduled as a batch.
- Once a schedule is approved, its scheduled work becomes locked and future batch scheduling must preserve those fixed times.

### Dashboard KPIs

The dashboard must show the operational impact of the current schedule and alternatives.

Required KPIs:

- Unresolved conflicts
- Critical jobs scheduled
- Engineering-hours utilisation
- Estimated overtime
- Schedule stability
- Robustness score

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
Conflict Detection
        ->
Scheduling
```

The adapter layer must normalize external data into the same internal model used by manual web requests.

## 3. Scheduling And Alternative Design

### Scheduling Pipeline

The core pipeline is:

```text
Request Created
        ->
Request Validation
        ->
Pending Request Queue
        ->
Generate Batch Schedule
        ->
Ranked Alternative Generation, when needed
        ->
KPI Impact Analysis
        ->
Explanation Generation
        ->
Schedule Manager Decision
        ->
Approved And Locked Schedule
```

### Hard Constraints

Hard constraints must not be violated in a valid schedule:

- Work starts no earlier than `earliest_start`.
- Work ends no later than `deadline`.
- The same crew cannot be assigned to overlapping work.
- The same equipment cannot be assigned to overlapping work.
- The same track sector cannot host incompatible overlapping work.
- Safety constraints must be respected.
- Dependencies must be scheduled in order.
- Locked work must keep its fixed time.
- Work must fit within allowed engineering-hour windows unless the selected scenario explicitly permits overtime.

If a hard constraint cannot be satisfied, the schedule candidate must not be created as a valid schedule option.

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

### Alternative Ranking

Alternatives use the same hard constraints and are ranked with a balanced score across:

- Disruption: prefer fewer moved jobs.
- Overtime: prefer no overtime or deadline pressure.
- Completion: prefer scheduling all valid requests.
- Critical priority: prefer preserving high-priority work.

The UI should show the top 2-3 feasible alternatives, each with all four scores and an overall score.

### No Valid Schedule Fallback

If no valid schedule exists, the system must not pretend that a schedule is valid.

The system must return:

- The blocking conflicts.
- The requests that prevent feasibility.
- The hard constraints that could not be satisfied.
- The closest available alternatives, clearly marked as unresolved if conflicts remain.
- Suggested user actions, such as changing deadline, extending engineering hours, reducing duration, changing crew/equipment, unlocking existing work, or rejecting the request.

## 4. UX Requirements

### Shared Navigation

Navigation should be mostly shared across both roles. Preferred MVP labels:

- New Request
- Planning Board
- Alternatives
- KPI Dashboard

Existing labels such as Field Request and Planner Dashboard may remain temporarily, but the product requirements should treat them as workflow labels, not the final role model.

Requester users should see decision actions as read-only or unavailable. Schedule Manager users should see the full decision action set.

### New Request Screen

The New Request screen must allow users to enter maintenance work details and submit the request for validation.

After submission:

- If the request fits, show that it can be scheduled.
- If the request does not fit, show the conflict summary and suggested alternatives.

### Planning Board

The Planning Board must make monthly workload and today's execution schedule visible without forcing users into a dense full Gantt first.

The Planning Board must show:

- KPI summary.
- Monthly calendar view with count of scheduled work per day.
- Conflict marker on days that contain conflicting work.
- Today's schedule for the selected date.
- Request list.
- Conflict indicators.
- Decision review panel.

The full Gantt view may remain as a secondary or future view. The main MVP schedule experience is the monthly planning view plus the selected day's engineering schedule.

### Decision Review Panel

The decision review panel must explain:

- Why the original request did not fit.
- Which requests or resources conflict.
- Which task is recommended to move.
- What schedule option is being shown.
- How KPIs change before and after the recommendation.

Available actions:

- Accept, Schedule Manager only
- Modify, Schedule Manager only
- Reject, Schedule Manager only
- Lock schedule, Schedule Manager only

### Alternatives Comparison

The Alternatives view must compare the default options side by side.

Each option must include:

- Option name
- Schedule summary
- Changed jobs
- Remaining conflicts
- KPI impact
- Explanation
- Accept action

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
- `POST /api/conflicts/detect`
- `POST /api/schedule/optimise`
- `POST /api/schedule/alternatives`
- `POST /api/schedule/approve`
- `GET /api/kpis`

Optional or later endpoints:

- `POST /api/scenarios/emergency`
- `POST /api/stress-test`

### Domain Models

The current domain models remain the baseline:

- `MaintenanceRequest`
- `ScheduledWork`
- `Conflict`
- `KpiSnapshot`
- `ScheduleAlternative`

### Fit Status Contract

Request submission should return or trigger a fit-status response.

Recommended response shape:

```json
{
  "request": {},
  "fits_current_schedule": false,
  "conflicts": [],
  "suggested_alternatives": []
}
```

When `fits_current_schedule` is `true`, `suggested_alternatives` may be empty unless the user explicitly requested comparison.

When `fits_current_schedule` is `false`, `suggested_alternatives` must include the default balanced options when feasible.

### Authorization Boundary

The MVP role boundary is intentionally small.

Requester permissions:

- Create requests.
- Edit own pending requests.
- View schedules, conflicts, alternatives, explanations, and KPIs.

Schedule Manager permissions:

- Create and edit requests.
- Approve, reject, modify, lock, and unlock schedule decisions.
- Finalize schedules.

This may be implemented with a simple user-mode field, seed users, demo toggle, or equivalent lightweight mechanism. Full authentication and production-grade access control are future enhancements.

### Scheduler Boundary

The scheduling engine is responsible for constraint satisfaction and objective optimization.

The scheduler must:

- Accept normalized `MaintenanceRequest` records.
- Preserve locked work.
- Respect hard constraints.
- Apply the selected objective profile.
- Return `ScheduledWork` records.
- Mark changed work with `changed_from_original`.
- Provide enough change context for explanations.

The long-term target is OR-Tools CP-SAT. A simpler baseline scheduler may be used during MVP development only if it preserves the API contract.

### Explanation Boundary

The explanation layer must translate scheduler and conflict outputs into user-facing reasons.

Explanations must include:

- What changed.
- Why it changed.
- Which conflict was resolved.
- Which tasks were affected.
- Which KPI improved or worsened.

Constraint logic decides schedules. LLM usage is optional and must only polish wording or summarize already-computed facts.

## 6. Demo Scenarios

### Demo 1: Live Request To Schedule

1. User creates a maintenance request.
2. Request appears in the Schedule Dashboard.
3. System checks the request against current scheduled work.
4. If no conflict exists, the request is scheduled.
5. User reviews KPI impact and approves.

### Demo 2: Conflict With Alternative Suggestions

1. User submits a request for a track sector already occupied in the requested window.
2. System flags the conflict.
3. System explains the original request does not fit because of track, crew, equipment, or deadline constraints.
4. System generates the four default alternatives.
5. User compares KPI impact and changed jobs.
6. User accepts the preferred recommendation.

### Demo 3: Emergency Rescheduling

1. User adds an emergency maintenance request.
2. System detects conflicts with existing approved work.
3. System generates ranked feasible alternatives.
4. Existing work is moved only where necessary.
5. User reviews schedule stability and explanation.
6. User approves or rejects the emergency reschedule.

## 7. Test And Acceptance Criteria

### Requirement Review

- The document does not define three required user roles.
- The MVP is described as two lightweight roles with shared visibility.
- Requesters can create requests and view schedules, conflicts, alternatives, explanations, and KPIs.
- Schedule Managers can approve, reject, modify, lock, and unlock schedule decisions.
- Alternative suggestions are required when the original request does not fit.

### Scheduling Scenarios

- Original request fits with no conflicts.
- Original request conflicts with track availability.
- Original request conflicts with crew availability.
- Original request conflicts with equipment availability.
- Original request misses deadline and requires alternatives.
- Emergency request forces minimum-disruption rescheduling.
- Locked work remains fixed during optimization.
- No-valid-schedule cases return explicit blockers.

### Acceptance Criteria

- Alternatives are shown when needed or when explicitly requested.
- Every conflict has a visible reason.
- Every alternative includes KPI impact and explanation.
- Only a Schedule Manager can accept, modify, or reject a suggested schedule.
- Requesters can still view the suggested schedule and explanation.
- The system does not claim an invalid schedule is conflict-free.

## 8. Future Enhancements

- More detailed role permissions beyond Requester and Schedule Manager.
- Official dataset enrichment, including MRT station or sector metadata.
- Schedule export.
- Audit history for schedule decisions.
- Robustness stress testing.
- Natural-language explanation polish.
- Richer optimization profiles.
- Multi-user collaboration.
- Authentication and production security.

## 9. Assumptions

- This document is the single PRD + technical design source for the MVP.
- MVP has two lightweight roles: Requester and Schedule Manager.
- Everyone has shared visibility into schedules, conflicts, alternatives, explanations, and KPIs.
- Only Schedule Managers can finalize schedule decisions.
- Alternative generation uses balanced named options by default.
- Existing backend and frontend labels may be updated later from role-flavored labels to shared workflow labels.
- The backend API and domain models currently in the repo are the baseline unless later implementation work changes them.
