# PS1 Schedule Copilot

The PS1 Schedule Copilot demonstrates the PS1 Bonus Scope without giving an LLM control over a railway schedule. It supports evidence-grounded questions about moves, downstream risk, capacity, co-sharing, handovers, milestones, replan impact, and comparisons among internally validated available scenarios.

The chat endpoint uses Gemini to generate English-only replies regardless of the input language, with the last six exchanges as context. It is one persistent conversation over all available A/B/C results—not one chat per selected scenario. General conversation and arithmetic are answered directly. For scheduling questions Gemini calls server-side tools to read scores, weighted contract penalties, activities, capacity, co-sharing, downstream links, milestones, handovers and replan diffs. An overall Scenario A/B/C design explanation is grounded in the documented policy, score components, delay drivers, capacity/precedence evidence and solver status rather than an invented solver thought process. Gemini can also read filtered rows from the selected validated `RESULTS.csv`, `SCHEDULE_ACCESS.csv` or `SCHEDULE_OCCUPANCY.csv`; it cannot access paths, URLs, uploads or unvalidated output. These tool results are sent to Vertex AI so Gemini can explain them. Model errors are visible; chat never silently falls back to canned replies. The older deterministic helpers remain internal evidence utilities, not the chat response generator.

For a timing-reasoning question, Gemini can first inspect the selected activity and then invoke one bounded counterfactual check. The server constrains that activity's start or finish week, resolves the CP-SAT model, and independently validates the resulting CSV before returning a comparison of score, contract completion, changed activities and validation status. It is ephemeral and cannot alter a job, baseline, revised CSV or replan. A time-limited, busy or failed check is `unknown`, not evidence that the alternative is impossible; successful internal validation does not claim official-validator parity.

Disruption tools assess exposed work and dependencies and prepare a validated draft without starting a solver. A displayed preview can be approved in a subsequent chat message or with the execution button. Gemini interprets approval intent, but cannot supply execution parameters: only the current server-issued preview token is submitted to the existing execution endpoint, which rechecks job, scenario, expiry, revision and single use. Chat itself does not start a solver. Open Innovation is represented by this what-if workflow; predictive bundling, negotiation and engineering-train logistics are not implemented tools.

Agent Mode automatically asks Gemini for an initial evidence-backed English briefing across all available scenarios. This introduces scores, risks and the approval workflow without a user message. Switching the visible scenario keeps the conversation and its current preview; switching jobs starts a fresh conversation.

## Disruption workflow

1. A controller describes a capacity disruption, or uses the manual form.
2. The Copilot normalizes and validates location, weeks, capacity, and reason, then creates a ten-minute preview bound to the job, scenario, baseline revision, and parameters.
3. The preview changes no schedule. The controller explicitly selects **Run validated re-plan** or approves the displayed draft in chat (for example “승인” or “실행해”). Changed parameters require a new preview and fresh approval.
4. CP-SAT generates the revision and the independent export validator plus disruption audit decide whether it is usable.
5. Only a completed, internally validated revision with a passing audit receives download links and an operational briefing.

This provides dynamic re-optimization and natural-language decision support, but it does not claim parity with an unavailable official validator or availability on real dated maintenance windows.
