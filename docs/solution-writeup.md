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
- Location-local legal co-sharing patterns and separate work-capacity and cross-contract physical-night safety checks.
- Ephemeral hidden-instance handling with no database retention.
- Emergency location-capacity re-planning with a hard operational cap, frozen past work, and score-first minimum-churn recovery.
- Baseline-to-revised impact evidence and a Gemini Copilot that calls schedule tools and writes evidence-based conversational replies.

## Technology

- FastAPI and Pydantic-compatible Python domain services
- Google OR-Tools CP-SAT
- Gemini Enterprise Agent Platform through the Google Gen AI SDK when deploy-time ADC is configured
- Next.js, React, TypeScript, and Lucide icons
- Docker single-origin deployment on Render
- Pytest and GitHub Actions

## Impact

RailFlowAI reduces a dense spreadsheet-and-manual-checking exercise to a repeatable workflow: load, validate, solve, inspect, and export. The controller sees not just a schedule, but why it is feasible and where each policy spends its flexibility.

After an urgent maintenance restriction, a controller can reduce one location's available capacity over a week range and re-plan the selected policy. The disruption is an additional hard limit even under flexible-supply policies. Completed past weeks remain fixed; future changes are minimized only after preserving the best policy score. Revised files pass both the normal export validator and a dedicated disruption-capacity audit before download.

## Validation boundary

The official executable validator is unavailable. Unsupported protection-slot supply charges have been removed. The sample is format-only per user clarification, so safety violations are negative test cases. The validator reconstructs a seven-night assignment independently from CSV and exposes it as evidence. Exact maintenance availability dates are not supplied. Internal optimality refers to the documented model. Activity evidence reports observed constraints and costs, not untested counterfactual causes. Infeasibility and time-limit failures are surfaced while preserving other validated scenarios.
