# Submission Short Answers

## What does your solution do? (105 words)

RailFlowAI transforms the eight PS1 demand-book CSVs into fully audited, optimal railway possession schedules for Scenarios A, B, and C. Powered by OR-Tools CP-SAT and an independent CSV validator, it strictly enforces network topology, weekly closures, and co-sharing rules. Designed to solve beyond-the-schedule operational challenges, RailFlowAI provides works controllers with a production-grade command center: interactive dashboards visualize real-time supply headroom, network bottlenecks, and priority-tiered contract milestone delivery audits. An evidence-grounded AI Assistant powered by Google Gemini handles plain-English schedule queries, downstream risk checks, and live disruption re-planning—allowing dispatchers to test capacity cuts, re-optimize schedules on the fly with minimal churn, and export submission-ready CSV packages.

## What tech stack was used to build this solution? (62 words)

The backend is Python 3.12 with FastAPI, Google OR-Tools CP-SAT for optimization, and Google Gemini via Vertex AI for grounded scheduling intelligence. The frontend uses Next.js 16, React 19, TypeScript, and Lucide icons for interactive analytics dashboards. Pytest covers parsing, topology, solver, CSV validation, and regression cases; TypeScript checks validate the frontend. Docker packages the entire application into a single deployable service.

## What challenges did you face, and how did you overcome them? (116 words)

Ensuring official validator parity across tightly coupled railway constraints was our toughest hurdle. We explored diverse paradigms: greedy heuristics trapped early decisions into deadlocks, while Random and Adaptive LNS introduced search variance and struggled with complex weekly closure boundaries. Benchmarking proved that standard CP-SAT was decisively superior and more reliable. We pivoted to strengthening the core CP-SAT model directly: encoding official feedback into regression tests, enforcing strict closure exclusivity without heuristic shortcuts, and accurately penalizing contract completion delays. Paired with an independent CSV validator, this pure constraint programming approach eliminated illegal overlaps and achieved stable global convergence, securing officially accepted schedules for Scenarios A (608.3) and B (50.0), alongside our locally validated 122.4 Scenario C candidate.

## Bonus Scope & Beyond-the-Schedule Innovation

- **What-if / Digital-Twin Sandboxing**: Interactive disruption injection where controllers simulate capacity reductions mid-horizon, preview affected work, and trigger live, bounded CP-SAT re-optimization that stabilizes unaffected schedules.
- **Fragility & Bottleneck Scoring**: Real-time operational resilience diagnostics via Supply Headroom %, pinpointing saturated zero-buffer hotspots and downstream delay propagation risks.
- **Contractor Negotiation Support**: Comprehensive milestone delivery audit tracking planned deadlines vs simulated completion across Priority 1 ($100\times$), Priority 2 ($10\times$), and Priority 3 ($1\times$) tiers to guide commercial trade-offs.
- **Predictive Bundling**: Automated co-sharing legal-mix optimization that bundles non-conflicting maintenance activities into shared possessions, maximizing network throughput.
- **Natural Language Operational Q&A**: Dual-engine assistant (Google Gemini + deterministic parser) answering complex controller queries regarding move root-causes, milestone risks, and shift handover briefs.

## Status wording

Use “officially accepted” only for the submitted A/B/C replacement run. Describe C=122.4 as a “locally validated, strict-model candidate pending official confirmation.”

