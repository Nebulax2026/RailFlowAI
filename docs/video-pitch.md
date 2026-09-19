# RailFlowAI Demo Video Script (5 Minutes)

---

### [0:00–0:35] Intake Dashboard & Demand Book Validation

**[화면: RailFlowAI 메인 Intake 화면. 8개 필수 CSV 파일과 9번째 `09_PREVENTIVE_MAINTENANCE.csv`가 나열된 체크리스트를 보여준다. 'Load Public Dataset'을 클릭하고 '+ Policy D/E' 토글을 켠 뒤, 'Run Demand Book'을 클릭한다.]**

Welcome to RailFlowAI, an end-to-end railway possession planning and decision-support platform. 

On the intake screen, RailFlowAI validates the complete railway demand book—including the eight core operational files and the ninth preventive maintenance schedule. Before reaching the solver, it verifies schemas, cross-file identifiers, track topology, physical capacities, and predecessor dependencies.

The validated model is solved using Google OR-Tools CP-SAT across parallel workers, producing three core operational policies:
Scenario A—Supply-Protective—achieving an official score of 608.3 with 42 overrun days;
Scenario B—Deadline-Protective—guaranteeing zero contract delay with a score of 50.0;
And Scenario C—our balanced multi-objective policy—achieving our competition-winning score of 122.4.

Let’s explore the dashboard tab by tab.

---

### [0:35–1:20] Tab 1: Overview — S-Curve & Contract Delivery Audit

**[화면: 대시보드가 열리면 최상단 'Overview' 탭에 위치한다. 상단 6종 KPI 메트릭 스트립(Penalty Score, Overrun Days, ECLO Nights, Excess Access, Total Accesses, Runtime)을 마우스로 훑는다. 아래로 내려와 Milestone Delivery S-Curve 차트를 보여주고, 이어서 Contract Delivery Audit 테이블을 스크롤한다.]**

At the top of the Overview tab, the prominent KPI strip immediately provides mission-critical metrics: total penalty score, contract overrun days, ECLO weekend nights, excess access usage, and total solver runtime.

Below, the Milestone Delivery S-Curve chart tracks cumulative contract delivery. Operators can visually compare the target baseline trajectory against actual completion trajectories across Policies A, B, and C.

Further down, the Contract Delivery Audit table breaks down every single contract:
It displays contract priority tiers—from high-priority P1 with a 100-times penalty weight, to P2 and P3 tiers;
Target deadlines versus actual completion dates;
And color-coded overrun badges showing exactly which contracts are on time and which are delayed.

---

### [1:20–1:55] Tab 2: Activities — Workload & Possession Co-sharing

**[화면: 상단 탭에서 'Activities' 탭을 클릭한다. 주차 필터 버튼과 검색창을 보여주고, 특정 활동(예: A025)을 클릭하여 우측 Evidence Drawer(작업 시간, 할당 주차, 야간 작업일, 법적 공동 점유 그룹)를 열어 보여준다.]**

Switching to the Activities tab, dispatchers gain full visibility into every scheduled activity.

Using the week filters or search bar, operators can inspect individual activity durations, earliest release dates, and scheduled access nights. 

Clicking any activity opens the evidence drawer, revealing its exact track footprint and legal possession co-sharing groups. Here, RailFlowAI proves how multiple compatible activities safely share the same track closure window, minimizing disruption and maximizing infrastructure throughput.

---

### [1:55–2:30] Tab 3: Locations — Track Capacity Heatmap

**[화면: 상단 탭에서 'Locations' 탭을 클릭한다. Eastbound(EB) 및 Westbound(WB) 선로 구간, 역 플랫폼, 버퍼 존이 나열된 주간 용량 히트맵 그리드를 보여주고, 사용량이 한계에 도달한 특정 주차의 셀을 마우스로 가리킨다.]**

The Locations tab provides a spatial capacity heatmap across the entire rail network.

It displays weekly capacity limits versus scheduled possession loads across directional sectors, platform station tracks, and interlocking buffers. 

Cells highlighted in amber or red pinpoint infrastructure bottlenecks and peak-demand weeks. This spatial transparency allows network operators to identify constrained track corridors months in advance.

---

### [2:30–3:30] AI Assistant & Urgent Re-planning Sandbox (Min-Churn)

**[화면: 우측 상시 AI 어시스턴트 패널을 보여준다. 추천 프롬프트 'Explain score drivers and why activity A12 moved'를 클릭해 수치와 위치가 명시된 답변을 보여준다. 이어서 채팅창에 "Reduce capacity on SEC:BET:S15_S16:EB to 0 in week 23"을 입력한다.]**

On the right sidebar, RailFlowAI features an integrated AI Schedule Copilot powered by Gemini. Grounded directly in mathematical solver evidence through structured tool-calling, the AI provides causal explanations with zero hallucination.

**[화면: 상단에 Re-plan Sandbox 배너가 앰버 하이라이트 라인과 함께 나타난다. [Baseline]과 [Re-plan] 토글을 번갈아 클릭하여 스케줄 변동을 보여주고, Preserved Plan 98.1%, Moved Activities 1개, Score Delta +0 배지, 그리고 [Apply to Schedule] 버튼을 가리킨다.]**

When emergency track closures occur, operators can issue plain natural language commands. 

Here, we inject an emergency disruption: capacity on sector S15–S16 is reduced to zero in week 23. 

The Urgent Re-planning Engine instantly triggers a two-tier lexicographic optimization:
Tier 1 preserves the best possible penalty score;
Tier 2 explicitly minimizes schedule churn.

As shown in our live Re-plan Sandbox, the engine shifts only one single activity, preserving 98.1% of the original schedule with zero score penalty. Dispatchers can toggle baseline versus revised plans, verify KPI delta badges, and approve the plan with human-in-the-loop control.

---

### [3:30–4:25] Policy D & E: Joint Preventive Maintenance & Trade-off

**[화면: 상단 Policy 탭 바에서 'Policy D' 탭을 클릭한다. 6개 PM KPI 카드 중 On-time Maintenance 100%(6,840건)와 빨간색 Project Overrun 49일을 가리킨다. 이어 'Policy E' 탭을 클릭해 녹색 Project Overrun 0일과 경미한 정비 지연 2건(3일)을 보여준다. 스크롤하여 정비 스케줄 표를 확인한 뒤, 상단의 [D vs E Trade-off] 버튼을 클릭해 팝업 모달을 띄운다.]**

Next, in the top policy bar, we switch to our joint preventive maintenance policies—Scenario D and Scenario E.

Scenario D—PM Priority—strictly fixes every maintenance occurrence to its planned calendar window. While all 6,840 maintenance occurrences run 100% on time, forcing capital renewals to yield causes 49 days of project delay.

Switching to Scenario E—PM Flexible—our multi-stage lexicographic CP-SAT prioritizes contract deadlines first. By allowing just two maintenance occurrences to shift by a total of three deferral days, Scenario E completely eliminates the 49-day project delay, achieving zero overrun.

Clicking the D vs E Trade-off modal reveals the exact operational exchange: saving 49 days of critical contract delay at the minor cost of three maintenance deferral days.

---

### [4:25–4:55] Validator-First Export & Official Acceptance

**[화면: Result Details 패널에서 독립 검증 통과 배지 'FEASIBLE · 0 violations'와 Split Download 버튼(ZIP 및 SCHEDULE_ACCESS, OCCUPANCY, RESULTS CSV)을 보여준다. 마지막으로 공식 검증기 점수 요약(A: 608.3, B: 50.0, C: 122.4)을 비춘다.]**

Before any schedule is downloaded, RailFlowAI’s independent export validator re-validates the raw exported CSV bytes against all domain rules—including spatial safety footprints and legal co-sharing.

All final schedules achieved official acceptance from the official competition validator: Scenario A at 608.3 with 42 overrun days, Scenario B at 50.0, and our competition-winning Scenario C at 122.4.

RailFlowAI delivers a transparent, mathematically proven, explainable, and disruption-resilient platform for railway possession planning. Thank you.

