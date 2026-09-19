# RailFlowAI Demo Video Script (5 Minutes)

---

### [0:00–0:40] Part 1: Problem Overview & Core Policies (A, B, C)

**[화면: RailFlowAI 메인 화면. 8개 필수 CSV 파일과 9번째 `09_PREVENTIVE_MAINTENANCE.csv`가 나열된 체크리스트를 보여준다.]**

Railway possession planning is one of the most demanding combinatorial optimization problems in infrastructure management. Every year, capital track renewal projects and recurring maintenance crews compete for scarce overnight track access across platforms, directional sectors, and interlocking buffer zones. 

Every single work activity is constrained by strict physical workloads, earliest release dates, multi-stage predecessor graphs, workfront concurrency limits, spatial safety closures, and legal co-sharing rules. 

**[화면: 파일 체크리스트에서 'Load Public Dataset'을 누르고, 상단의 세 가지 정책 A, B, C를 가리킨다.]**

RailFlowAI ingests the official demand book and mathematically models three distinct operational policies:
First, Scenario A—Supply-Protective—which strictly penalizes excess capacity usage, protecting network supply with an official score of 608.3 and 21 overrun days.
Second, Scenario B—Deadline-Protective—which prioritizes project completion deadlines, guaranteeing zero contract delay with a score of 50.0.
And third, Scenario C—our balanced multi-objective policy—which simultaneously balances delay penalties, excess supply usage, and ECLO weekend nights, achieving our competition-winning score of 122.4.

---

### [0:40–1:35] Part 2: Algorithmic Evolution & Why CP-SAT Finds the Global Optimum

**[화면: 입력 카드에서 Algorithm Selector 드롭다운을 열어 `OR-Tools CP-SAT`, `CP-SAT + RLNS`, `Adaptive LNS`를 보여준 뒤 'Run Demand Book'을 클릭한다. 솔버 진행률 바와 8개 워커 병렬 탐색 텔레메트리가 실시간으로 올라가는 모습을 보여준다.]**

Solving this problem required a deliberate algorithmic evolution.

We began with Greedy Dispatching Heuristics. While executing in under one second, greedy algorithms repeatedly fell into local minima traps—failing to anticipate downstream spatial conflicts, causing illegal closure overlaps, and producing unacceptable penalty scores.

To solve this rigorously, we formulated the entire problem into Google OR-Tools CP-SAT.

Why can CP-SAT reliably find the global optimum? Unlike heuristics or local search that get trapped in local basins, CP-SAT couples Conflict-Driven Clause Learning—known as CDCL—with integer Branch-and-Bound and domain constraint propagation. 

As the search runs across parallel workers, the engine learns conflict clauses that mathematically prune vast subtrees of non-optimal solutions. Simultaneously, it maintains a proven mathematical lower bound and upper bound. When the optimality gap closes to zero percent, the solution is mathematically proven to be the global minimum.

For massive enterprise networks, we augmented the solver with CP-SAT plus Relaxation-induced LNS and Adaptive LNS. These hybrid engines dynamically freeze non-conflicting subgraphs and re-optimize bottleneck clusters, drastically accelerating convergence while preserving strict mathematical feasibility.

---

### [1:35–2:25] Part 3: Explainable Command Center & Grounded AI Assistant

**[화면: 대시보드 2열 레이아웃을 보여준다. 좌측 메인 패널에서 S-Curve 마일스톤 차트의 계획선 대비 실제 곡선을 가리키고, 스크롤을 내려 계약 납기 감사 테이블(P1, P2, P3 배지 및 Overrun 일수)을 보여준다. 이어서 'Activities' 탭과 'Locations' 탭의 구간별 주간 용량 히트맵을 차례로 클릭한다.]**

RailFlowAI provides complete operational transparency. Rather than treating the schedule as a black box, dispatchers can track cumulative progress via the milestone delivery S-curve, audit individual contract delivery dates across priority tiers, and inspect weekly capacity heatmaps to pinpoint track bottlenecks.

**[화면: 우측의 상시 AI 어시스턴트 패널로 시선을 옮긴다. 추천 프롬프트 칩 'Explain score drivers and why activity A12 moved'를 클릭한다. AI가 솔버 데이터를 인용하며 특정 주차와 트랙 구간을 들어 즉각 답변하는 카드를 보여준다.]**

On the right sidebar, RailFlowAI integrates an AI Schedule Copilot powered by Gemini. Crucially, the AI is directly grounded in mathematical solver evidence through structured tool-calling—completely eliminating hallucinations. 

Dispatchers can query in natural language why an activity was shifted, evaluate downstream contract risks, or inspect spatial bottlenecks, receiving immediate, auditable answers.

---

### [2:25–3:20] Part 4: Urgent Re-planning Algorithm — Min-Churn under Disruption

**[화면: AI 어시스턴트 채팅창에 "Reduce capacity on SEC:BET:S15_S16:EB to 0 in week 23"을 입력한다. 어시스턴트가 단선을 검증하고 즉시 상단에 Re-plan Sandbox 배너(하단 앰버 라인)를 띄운다.]**

When unplanned track closures or emergency speed restrictions strike in real operations, dispatchers cannot afford a chaotic overhaul of the entire timetable. 

RailFlowAI features an Urgent Re-planning Engine governed by a two-tier lexicographic optimization:
Tier 1 preserves the best possible objective penalty score under the degraded capacity.
And Tier 2 explicitly minimizes schedule churn, solving for minimum moved activities and minimum night shifts relative to the original schedule.

**[화면: Re-plan Sandbox 배너에서 [Baseline]과 [Re-plan] 토글 버튼을 번갈아 클릭하여 변경된 일정을 시각적으로 비교한다. Preserved Plan 98.1%, Moved Activities 1개, Score Delta +0 배지를 가리킨 뒤, 상단 분할 다운로드 버튼과 [Apply to Schedule] 버튼을 보여준다.]**

As shown in our live Re-plan Sandbox, when track capacity drops to zero in week 23, the engine shifts only one single activity, preserving 98.1% of the original schedule with zero score penalty. 

Dispatchers can compare baseline versus revised plans, verify delta badges across all KPIs, and review changes with human-in-the-loop control before applying them to the live railway.

---

### [3:20–4:15] Part 5: Joint Preventive Maintenance & Policy D vs E Trade-off

**[화면: 상단 Policy 탭 바에서 'Policy D' 탭을 클릭한다. 6개 KPI 카드 중 On-time Maintenance 100%(6,840건)와 빨간색 Project Overrun 49일을 가리킨다. 이어 'Policy E' 탭을 클릭하여 녹색 Project Overrun 0일과 지연 정비 2건(3일)을 보여준다. 스크롤하여 정비 스케줄 표를 확인한 뒤, 상단의 [D vs E Trade-off] 버튼을 클릭해 팝업 모달을 띄운다.]**

Real railway networks cannot plan capital renewals in isolation—routine track inspections and preventive maintenance must occur simultaneously. Utilizing our expanded 9-file demand book, RailFlowAI jointly schedules renewals and maintenance across two specialized policies:

Scenario D—PM Priority—strictly locks every maintenance occurrence to its planned calendar window with zero deferral days. Every single one of the 6,840 maintenance occurrences runs on time. However, forcing capital renewal projects to yield causes 49 days of project delay.

Scenario E—PM Flexible—utilizes multi-stage lexicographic CP-SAT to prioritize contract deadlines first. By allowing just two maintenance occurrences to shift by a total of three deferral days, Scenario E completely eliminates the 49-day project delay, achieving zero overrun.

Our interactive D vs E Trade-off modal quantifies this exact operational exchange: saving 49 days of critical contract delay at the minor cost of three maintenance deferral days.

---

### [4:15–4:55] Part 6: Validator-First Architecture, Official Acceptance & Close

**[화면: Result Details 패널에서 독립 검증 통과 배지인 'FEASIBLE · 0 violations'와 3종 CSV 및 검증된 ZIP 다운로드 버튼을 보여준다. 마지막으로 공식 검증기 점수 요약 화면을 비춘다.]**

Before any schedule is released for operations, RailFlowAI’s independent export validator re-validates the raw exported CSV bytes against all domain rules—including spatial safety footprints, legal co-sharing, and weekly closure compatibility.

An early schedule candidate was rejected by the official validator due to overlapping weekly closure zones. We converted that feedback into automated regression tests, tightened our spatial model, and achieved official acceptance across all scenarios: Scenario A at 608.3, Scenario B at 50.0, and our competition-winning Scenario C at 122.4.

RailFlowAI delivers an end-to-end, mathematically proven, explainable, and disruption-resilient platform for modern railway possession planning. Thank you.

