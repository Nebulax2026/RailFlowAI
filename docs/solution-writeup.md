# RailFlowAI Solution Write-up

## The Problem

Rail maintenance contractors compete for a small number of overnight possessions across two lines, two bounds, tunnels, platforms, and an exceptional interchange. A useful plan must schedule the complete workload while respecting supply, weekly allocation, workfronts, co-sharing, precedence, safety rules, and policy-specific completion targets.

## Our Solution

RailFlowAI searches the official demand book for three auditable policy answers. A strict parser rejects malformed or inconsistent data. A topology engine expands work and protection footprints. OR-Tools CP-SAT jointly chooses access weeks, local nights, ECLO, and explicit legal co-sharing possessions. First searches target 30 seconds per scenario; validated incumbents may improve for another 90 seconds.

Every generated CSV is re-read by a separate validator before download. This “prove the artifact” boundary prevents UI or serialization defects from being mistaken for a valid plan.

## What Is Different

The original RailFlowAI prototype scheduled ad-hoc maintenance requests against crews and equipment. The PS1 version schedules complete programme workloads against physical railway possessions. Its key differentiators are:

- Validator-first outputs with exact official schemas.
- All three scenarios solved from one upload and compared in one workspace.
- Explanations tied to completion, capacity, excess supply, and ECLO.
- Explicit legal co-sharing patterns and a documented conservative protection policy.
- Ephemeral hidden-instance handling with no database retention.
- Live LTA network context without pretending that real line codes map to the fictional judging network.

## DataMall

The optional server-side integration reads Train Service Alerts using an AccountKey. It gives a works controller current operating context, but it never mutates Alpha/Beta capacity or influences validator scoring. This avoids an unsafe synthetic-to-real mapping.

## Technology

- FastAPI and Pydantic-compatible Python domain services
- Google OR-Tools CP-SAT
- Next.js, React, TypeScript, and Lucide icons
- Docker single-origin deployment on Render
- Pytest and GitHub Actions

## Impact

RailFlowAI reduces a dense spreadsheet-and-manual-checking exercise to a repeatable workflow: load, validate, solve, inspect, and export. The controller sees not just a schedule, but why it is feasible and where each policy spends its flexibility.

## Validation boundary

The official executable validator is unavailable. Protection-slot accounting reports 36 compatibility differences against the organizers' sample; these are documented in the validator specification and compatibility report, not hidden. Internal optimality refers to the documented model. Activity evidence reports observed constraints and costs, not untested counterfactual causes. Infeasibility and time-limit failures are surfaced while preserving other validated scenarios.
