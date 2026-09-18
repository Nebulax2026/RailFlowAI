# RailFlowAI 2-3 Minute Pitch

## 0:00-0:20 - Problem

“Every engineering night is contested. Contractors need the same tunnels and platforms, but each activity has its own start date, predecessor, workfront, weekly allocation, safety footprint, and deadline. RailFlowAI turns that demand book into a possession plan a controller can inspect and dispatch.”

Show the workspace title and eight-file intake.

## 0:20-0:45 - Load and Validate

Click **Load public dataset**.

“The app accepts the same eight CSV files used for hidden judging. Before optimisation, it verifies schemas, identifiers, topology, dates, capacities, contracts, activities, and predecessors. Invalid data never enters the solver.”

Point to instance totals: 54 activities, 192 accesses, and 30 weeks.

## 0:45-1:20 - Three Policies

Show A/B/C progress and open each completed tab.

“One upload produces three independent answers. Scenario A protects nominal supply and accepts schedule slip. Scenario B protects planned completion and measures the extra operational cost, including ECLO. Scenario C balances both sides with tightly limited elasticity.”

Point to objective, overrun, excess, and ECLO metrics.

## 1:20-1:55 - Explainability

Show weekly access load, hotspots, and the contract table.

“Controllers can see where workload clusters, which locations reach capacity, which contracts overrun, and why. Compatible PC and C work is packed into auditable possession groups. The schedule is not a black box.”

## 1:55-2:25 - Urgent Re-planning

Select a capacity hotspot, reduce its available slots, and click **Re-plan**.

?When urgent maintenance cuts access, RailFlowAI treats the reduced capacity as a physical limit, preserves completed work, and finds the best policy result with minimum disruption to the remaining plan. Controllers see exactly which activities and contracts moved.?

Ask **Why was A001 moved?** in **PS1 Schedule Copilot** and show the grounded evidence IDs. Then type a disruption request, review the preview card, and explicitly click **Run validated re-plan**—the Copilot interprets and explains, while the solver and validator remain the decision authority.

## 2:25-2:45 - Proof and Export

Download one CSV and then the combined ZIP.

“Before downloads are enabled, RailFlowAI serializes the official files, reads them back, and independently checks workload, dates, predecessors, weekly allocation, workfronts, occupancy, capacity, ECLO, and results. We validate the artifact the judges receive.”

## 2:45-3:00 - Decision Evidence and Close

Select an activity and show its scheduled weeks, shared possessions, and protection footprint.

?Planners can trace each activity from its workload through its scheduled access and protection requirements. Compare the three policies, inspect the evidence, and export the internally validated result.?
