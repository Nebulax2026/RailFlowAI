# RailFlowAI Demo & Pitch Script (3.5–4 Minutes)

## 0:00–0:30 — Problem Understanding & Core Policies (Scenarios A, B, C)

**Show:** The RailFlowAI intake dashboard. Show the file checklist displaying the eight core demand book CSVs and the optional ninth `09_PREVENTIVE_MAINTENANCE.csv`.

**Say:** “Railway possession planning is an intensely constrained combinatorial challenge. Capital renewal projects and maintenance teams compete for scarce overnight track access across platforms, directional sectors, and interlocking buffers. Every activity is governed by strict workload, release dates, predecessor dependencies, workfront concurrency, spatial safety closures, and legal co-sharing rules. 

RailFlowAI ingests the official PS1 demand book and mathematically models three core operational policies:
- **Scenario A (Supply-Protective):** strictly protects network access capacity limits (Score: **608.3**, with 21 overrun days).
- **Scenario B (Deadline-Protective):** prioritizes project completion dates to guarantee zero contract delay (Score: **50.0**, 0 overrun days).
- **Scenario C (Balanced Multi-Objective):** jointly balances delay penalties, excess supply usage, and ECLO weekend nights, achieving our competition-winning score of **122.4**.”

---

## 0:30–1:15 — Algorithmic Evolution & Why CP-SAT Finds the Global Optimum

**Show:** The Algorithm Selector in the UI (showing `OR-Tools CP-SAT`, `CP-SAT + RLNS`, and `Adaptive LNS`), and click **Run Demand Book** to display live solver telemetry and convergence charts.

**Say:** “Solving this problem required an algorithmic evolution:
- We began with **Greedy Heuristics**. While running in under one second, greedy dispatching repeatedly fell into local minima traps, producing illegal spatial overlaps and unacceptable penalty scores.
- To resolve this, we formulated the full mathematical model into **OR-Tools CP-SAT**.
- **Why can CP-SAT find the global minimum?** Unlike heuristics or metaheuristics that get stuck in local optima, CP-SAT couples **Conflict-Driven Clause Learning (CDCL)** with integer **Branch-and-Bound** and domain constraint propagation. It systematically searches the decision space, dynamically prunes provably non-optimal subtrees through learned conflict clauses, and tightens lower and upper bounds until the optimality gap reaches zero. This mathematically proves global optimality.
- For massive-scale instances, we augmented the engine with **CP-SAT + RLNS (Relaxation-induced LNS)** and **Adaptive LNS (ALNS)**—selectively freezing high-confidence subgraphs while re-optimizing bottlenecks to accelerate convergence without ever compromising constraint feasibility.”

---

## 1:15–1:55 — Explainable Dashboard & Conversational AI Copilot

**Show:** The 2-column command center:
- **Left Panel:** Navigate through the **Overview**, the cumulative **Milestone Delivery S-Curve Chart**, and the **Contract Delivery Audit Table**. Switch tabs to **Activities** and **Locations** to show weekly capacity heatmaps.
- **Right Panel:** Focus on the permanent **AI Assistant** sidebar. Click the suggested prompt: *“Explain score drivers and why activity A12 moved”*. Show the verifiable evidence response citing specific week numbers and locations.

**Say:** “Rather than treating the schedule as an inscrutable black box, RailFlowAI provides complete visibility. Operators can inspect milestone delivery S-curves, contract completion dates, weekly access loads, and location capacity heatmaps.

On the right sidebar, RailFlowAI features an integrated **AI Schedule Copilot powered by Gemini**. Crucially, the AI is directly grounded in mathematical solver evidence via structured function calling—completely eliminating hallucinations. Dispatchers can query in plain natural language why an activity was shifted, identify capacity bottlenecks, or audit contract delay risks, receiving instant, auditable answers.”

---

## 1:55–2:40 — Urgent Re-planning Algorithm: Min-Churn under Disruption

**Show:** In the AI chat, type: *“Reduce capacity on SEC:BET:S15_S16:EB to 0 in week 23”*. The assistant validates the disruption and triggers the **Re-plan Sandbox**.
- Highlight the **Re-plan Sandbox top banner** with its bottom amber highlight bar.
- Toggle between **[Baseline]** and **[Re-plan]**.
- Show the KPI delta badges (`+0 pts`, `0d overrun`), **Preserved Plan (98.1%)**, and **Moved Activities (1)**.
- Show the split download button (`Download ZIP` / `SCHEDULE_ACCESS.csv`) and the human-in-the-loop **[Apply to Schedule]** and **[Discard]** buttons.

**Say:** “When track disruptions strike in real operations, speed and stability are critical. RailFlowAI features an **Urgent Re-planning Engine** governed by a two-tier lexicographic optimization:
1. **Tier 1 (Objective Score Preservation):** It seeks the best possible penalty score under the degraded capacity.
2. **Tier 2 (Min-Churn / Maximum Plan Preservation):** Among solutions that achieve that optimal score, it explicitly minimizes schedule churn: $\min \sum (\text{moved\_activities}) + \Delta \text{nights}$.

As demonstrated in our interactive **Re-plan Sandbox**, when track capacity drops to zero in week 23, the engine shifts only **one single activity**, preserving **98.1% of the baseline schedule** with **zero score penalty**. Operators can inspect the exact diff, review delta badges across all KPIs, and approve the revised plan with human-in-the-loop control before applying it.”

---

## 2:40–3:25 — Joint Preventive Maintenance & D vs E Trade-off

**Show:** In the top policy bar, click **Policy D**, then **Policy E**. Show the 6 KPI metric cards (Overrun, On-time PM, Deferred PM) and the maintenance schedule table. Click the **[D vs E Trade-off]** button to open the side-by-side modal dialog.

**Say:** “Real railways cannot plan capital renewals in isolation—recurring track maintenance must happen simultaneously. Incorporating our expanded 9-file demand book, RailFlowAI jointly schedules project renewals and preventive maintenance across two specialized policies:
- **Scenario D (PM Priority):** strictly fixes every maintenance occurrence to its planned calendar window with **0 deferral days** (100% on-time across all 6,840 occurrences). However, forcing capital renewal projects to yield causes **49 days of project delay (overrun)**.
- **Scenario E (PM Flexible / Project-Protected):** utilizes multi-stage lexicographic CP-SAT to prioritize project delivery first. By permitting just **2 maintenance occurrences** to shift by a total of **3 deferral days**, Scenario E completely eliminates the 49-day project delay (0 overrun days).

Our interactive **D vs E Trade-off modal** quantifies this exact operational exchange: saving 49 days of critical contract delay at the minor cost of 3 maintenance deferral days.”

---

## 3:25–3:50 — Validator-First Byte Verification & Conclusion

**Show:** The Result Details panel showing the independent validation badge (`FEASIBLE · 0 violations`) and the download buttons for CSVs and submission ZIPs.

**Say:** “Before any schedule is released, RailFlowAI’s independent export validator re-validates the raw exported CSV bytes against all domain rules—including spatial safety footprints, legal co-sharing, and weekly closure zones. 

An early schedule iteration was rejected by the official validator due to overlapping closure zones. We converted that feedback into automated regression tests, tightened our spatial model, and achieved official acceptance across all scenarios: **Scenario A at 608.3**, **Scenario B at 50.0**, and our winning **Scenario C at 122.4**. RailFlowAI provides an end-to-end, mathematically proven, and explainable operating platform for railway possession planning.”

---

## Recording & Presentation Cheat Sheet

| Time | Section | Screen Action | Key Talking Point |
| :--- | :--- | :--- | :--- |
| **0:00–0:30** | Problem & Policies | Intake screen, 9-file list | A (Supply: 608.3), B (Deadline: 50.0), C (Balanced: 122.4) |
| **0:30–1:15** | Algorithmic Evolution | Algorithm selector, live solve | Greedy (<1s, traps) → CP-SAT (CDCL + B&B = Global Minimum) → ALNS/RLNS |
| **1:15–1:55** | Explainable UI & AI | S-curve, heatmaps, AI panel | Grounded in solver evidence (zero hallucination), causal explanations |
| **1:55–2:40** | Urgent Re-planning | AI prompt: capacity drop, Sandbox | Min-churn: Tier 1 best score, Tier 2 min moved (98.1% preserved, 1 moved) |
| **2:40–3:25** | Preventive D vs E | Policy D & E tabs, Trade-off modal | D: 0d PM deferral → 49d project delay; E: 3d PM deferral → 0d project delay |
| **3:25–3:50** | Validator & Close | Feasible badge, ZIP download | Byte-level verification, official acceptance (A: 608.3, B: 50.0, C: 122.4) |
