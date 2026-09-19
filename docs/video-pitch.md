# RailFlowAI 2.5–3 Minute Demo Script

## 0:00–0:20 — The planning problem

**Show:** The RailFlowAI intake page.

**Say:** “Rail maintenance activities compete for a limited number of weekly possessions across platforms, sectors, buffers, and tunnels. Each activity has workload, release dates, predecessors, workfronts, safety footprint, and contract deadline constraints. RailFlowAI converts the PS1 demand book into a complete, auditable possession plan.”

## 0:20–0:35 — Input validation & demand book

**Show:** The file checklist showing the eight core demand book CSVs plus the optional 9th `09_PREVENTIVE_MAINTENANCE.csv` row. Click **Load public dataset** and toggle **+ Policy D/E**, then click **Run Demand Book**.

**Say:** “The application validates the complete railway demand book—including the eight core operational files and the ninth preventive maintenance schedule. Before reaching the solver, it strictly verifies schemas, cross-file references, dates, track topology, physical capacities, contracts, and predecessor graphs. Invalid inputs never reach the engine.”

## 0:35–1:05 — Optimisation & key metrics (Scenarios A, B, C)

**Show:** The top policy selector bar, running job progress, and metric badges across Policies A, B, and C.

**Say:** “The validated problem is solved using OR-Tools CP-SAT across parallel workers. One run produces three distinct policy views:
- **Scenario A (Supply-Protective):** strictly protects network access capacity (Score: **608.3**, with 21 overrun days).
- **Scenario B (Deadline-Protective):** guarantees zero contract delay (Score: **50.0**, 0 overrun days).
- **Scenario C (Balanced Multi-Objective):** jointly balances delay, excess capacity, and ECLO weekend nights (Score: **122.4**).

The dashboard immediately highlights critical metrics: overall objective scores, contract overrun days, excess capacity penalties, ECLO night allocations, and total solver runtime.”

## 1:05–1:40 — AI Assistant: conversational schedule copilot

**Show:** The permanent AI Assistant panel on the right sidebar. Type or click an example prompt: *“Explain score drivers and why activity A12 moved”* or *“Identify capacity hotspots and downstream risks for Contract C3.”* Show the instant response with verifiable evidence cards.

**Say:** “Rather than treating the schedule as a black box, RailFlowAI features an integrated AI Assistant powered by Gemini. It is directly grounded in mathematical solver evidence—preventing hallucinations. Operators can query why specific activities were shifted, review capacity bottlenecks, or evaluate contract risks in plain natural language. The assistant can even prepare validated disruption re-plans with human-in-the-loop approval before anything touches the solver.”

## 1:40–2:15 — Joint preventive maintenance & trade-offs (Scenarios D & E)

**Show:** Click the **Policy D** tab in the top policy bar, then **Policy E**, and click the **D vs E Trade-off** modal button. Show the side-by-side metric comparison and schedule diff table.

**Say:** “In real operations, capital renewals must co-exist with recurring track inspections. Incorporating the 9-file joint maintenance dataset, RailFlowAI models joint preventive maintenance directly in the dashboard across two policies:
- **Scenario D (PM Priority):** strictly locks maintenance to planned calendar windows with **0 deferral days** (100% on-time maintenance across all 6,840 occurrences). However, forcing capital renewals to yield causes **49 days of project overrun**.
- **Scenario E (PM Flexible / Project-Protected):** uses multi-stage lexicographic CP-SAT to protect project delivery first. By allowing just **2 maintenance occurrences** to shift by a total of **3 deferral days**, Scenario E completely prevents that 49-day project delay.

The interactive trade-off modal visualizes this exact operational trade-off: saving 49 days of critical contract delay at the minor cost of 3 maintenance deferral days.”

## 2:15–2:40 — Validator-first export & submission integrity

**Show:** Result details, the independent validation badge (`FEASIBLE · 0 violations`), and the download buttons for CSVs and submission ZIPs.

**Say:** “Before any file is released for download, RailFlowAI exports the required CSVs and independently re-validates the raw CSV bytes against all domain rules—including safety footprints, legal co-sharing, and weekly closure compatibility. The downloaded ZIP contains the exact, byte-verified artifact evaluated by the engine.”

## 2:40–3:00 — Official validator acceptance & close

**Show:** Submission summary showing official validator acceptance for Scenario A, Scenario B, and Scenario C (Score: 122.4).

**Say:** “An early schedule iteration was rejected by the official validator due to overlapping weekly closure zones. We converted that feedback into automated regression tests, tightened our spatial model, and achieved official acceptance across all scenarios: **Scenario A at 608.3**, **Scenario B at 50.0**, and our competition-winning **Scenario C at 122.4**. RailFlowAI provides an end-to-end, mathematically proven, and explainable path to railway possession planning.”

---

## Recording & Presentation Notes

1. **Screen Layout:**
   - Keep the 2-column view visible during the schedule and assistant sections so viewers see the schedule timeline on the left and the permanent AI Assistant sidebar on the right.
2. **AI Assistant Demo:**
   - Pre-copy a clean query (e.g., `Why did activity A12 move and what are the capacity bottlenecks?`) or click one of the suggested query chips for smooth delivery.
   - Highlight that the assistant cites actual activity IDs, week numbers, and score penalties.
3. **Scenario D vs E & 9-File Dataset Demo:**
   - Show the intake checklist with `09_PREVENTIVE_MAINTENANCE.csv` highlighted as the 9th joint maintenance input.
   - Click **Policy D** to show 100% on-time maintenance alongside the 49-day project overrun.
   - Click **Policy E** to show how project delay is wiped out.
   - Click **D vs E Trade-off** to show the popup dialog with the delta metrics (`-49d project overrun` vs `+3d maintenance deferral`).
4. **Terminology Guidelines:**
   - Use **“internally validated”** when demonstrating local runs/re-plans.
   - Use **“officially accepted”** when showcasing the final submission benchmark scores (A: 608.3, B: 50.0, C: 122.4).
