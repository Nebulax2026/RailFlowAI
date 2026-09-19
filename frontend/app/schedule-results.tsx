"use client";

import { useMemo, useState } from "react";
import { Activity, AlertTriangle, ArrowRight, CheckCircle2, ChevronRight, Gauge, Info, LoaderCircle, ShieldAlert, ShieldCheck, Sparkles, X } from "lucide-react";
import { Inspection } from "./inspection";
import { AIAssistantPanel } from "./bonus-tools";
import { POLICIES, TABS, formatLocationName, type Scenario, type Job, type ScenarioDetail, type RunState, type DetailTab } from "./schedule-types";

export function ScheduleResults({
  job,
  details
}: {
  job: Job;
  details: Partial<Record<Scenario, ScenarioDetail>>;
}) {
  const [choice, setSelectedScenario] = useState<Scenario>("A");
  const selectedScenario = job.scenarios[choice] ? choice : ((Object.keys(job.scenarios)[0] as Scenario) ?? "A");
  const [tab, setTab] = useState<DetailTab>("overview");
  const [weekFilter, setWeekFilter] = useState<number | null>(null);

  const selected = details[selectedScenario];
  if (!job.scenarios[selectedScenario]) {
    return <div className="empty-result">No policies available for this job.</div>;
  }

  const handleBarClick = (week: number) => {
    setWeekFilter(week);
    setTab("activities");
  };

  return (
    <section className="dashboard-2col-layout" aria-label="Command Center Dashboard">
      {/* Column 1: Main Workspace Column (Slim Top Policy Bar + Active Workspace) */}
      <div className="main-workspace-column">
        {/* Slim Top Policy Selector Bar (spanning full width of the main panel) */}
        <div className="top-policy-bar" role="tablist" aria-label="Policy Switcher">
          {(["A", "B", "C"] as Scenario[]).map((scenario) => {
            const run = job.scenarios[scenario];
            if (!run) return null;
            const isSelected = selectedScenario === scenario;

            return (
              <div
                key={scenario}
                role="tab"
                tabIndex={0}
                className={`top-policy-card policy-${scenario.toLowerCase()} ${isSelected ? "selected" : ""}`}
                onClick={() => setSelectedScenario(scenario)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setSelectedScenario(scenario); }}
                aria-selected={isSelected}
              >
                <div className="top-policy-left">
                  <span className="top-policy-letter">{scenario}</span>
                  <div className="top-policy-meta">
                    <div className="top-policy-name-row">
                      <strong>Policy {scenario}</strong>
                      <span className="top-policy-subtitle">({POLICIES[scenario]})</span>
                    </div>
                  </div>
                </div>

                <div className="top-policy-right">
                  <span className="top-policy-pill">{runLabel(run)}</span>
                </div>

                <div
                  className="top-policy-progress-line"
                  style={{ width: `${run.progress}%`, opacity: run.progress > 0 ? 1 : 0 }}
                />
              </div>
            );
          })}
        </div>

        {/* Center Main Active Workspace */}
        <main className="center-workspace" key={job.job_id}>
          <ScenarioWorkspace
            detail={selected}
            run={job.scenarios[selectedScenario]!}
            scenario={selectedScenario}
            jobId={job.job_id}
            job={job}
            details={details}
            tab={tab}
            onTabChange={setTab}
            weekFilter={weekFilter}
            onSelectWeek={handleBarClick}
            onClearWeekFilter={() => setWeekFilter(null)}
          />
        </main>
      </div>

      {/* Column 2: Permanent AI Assistant Sidebar */}
      <AIAssistantPanel
        jobId={job.job_id}
        scenario={selectedScenario}
        runStatus={job.scenarios[selectedScenario]?.status ?? "queued"}
        usage={selected?.validation.detail.location_usage ?? []}
        hotspots={selected?.validation.detail.capacity_hotspots ?? []}
        locations={selected?.locations ?? []}
      />
    </section>
  );
}

function formatSeconds(value?: number | null) {
  return value == null ? "—" : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}s`;
}

function runLabel(run: RunState) {
  if (["optimal", "optimal_for_policy"].includes(run.termination_reason ?? "")) return "Optimal Proved";
  if (run.phase === "improving") return "Improving";
  if (run.phase === "first_search") return "Searching";
  if (run.feasible) return "Feasible Plan";
  if (run.termination_reason === "infeasible") return "Infeasible";
  if (["time_limit", "no_solution_within_budget"].includes(run.termination_reason ?? "")) return "Budget Expired";
  return run.status;
}

function ScenarioWorkspace({
  detail,
  run,
  scenario,
  jobId,
  job,
  details,
  tab,
  onTabChange,
  weekFilter,
  onSelectWeek,
  onClearWeekFilter
}: {
  job: Job;
  details: Partial<Record<Scenario, ScenarioDetail>>;
  detail?: ScenarioDetail;
  run: RunState;
  scenario: Scenario;
  jobId: string;
  tab: DetailTab;
  onTabChange: (tab: DetailTab) => void;
  weekFilter: number | null;
  onSelectWeek: (week: number) => void;
  onClearWeekFilter: () => void;
}) {
  const scores = detail?.validation.soft_scores;
  const hotspots = detail?.validation.detail.capacity_hotspots ?? [];
  const strainedBottlenecks = useMemo(() => {
    if (!detail) return [];
    const allUsage = detail.validation.detail.location_usage ?? [];
    if (allUsage.length > 0) {
      const items = allUsage
        .filter((u) => u.used > 0)
        .map((u) => {
          const saturation = u.capacity > 0 ? u.used / u.capacity : 0;
          return {
            ...u,
            saturation,
            pct: Math.round(saturation * 100),
          };
        })
        .filter((u) => u.saturation >= 0.5 || u.used >= u.capacity)
        .sort((a, b) => b.saturation - a.saturation || a.week - b.week);

      if (items.length > 0) {
        return items.slice(0, 24);
      }
    }
    return hotspots.map((h) => ({
      ...h,
      saturation: h.capacity > 0 ? h.used / h.capacity : 1,
      pct: h.capacity > 0 ? Math.round((h.used / h.capacity) * 100) : 100,
    }));
  }, [detail, hotspots]);
  const [hoveredWeek, setHoveredWeek] = useState<{ week: number; count: number; eclo: number } | null>(null);
  const [hoveredFormulaTerm, setHoveredFormulaTerm] = useState<string | null>(null);
  const [hoveredSCurveWeek, setHoveredSCurveWeek] = useState<number | null>(null);
  const [milestoneChartMode, setMilestoneChartMode] = useState<"delay" | "completion">("delay");

  // Group scheduled accesses by week for the active policy
  const weekStats = useMemo(() => {
    const map = new Map<number, { count: number; eclo: number }>();
    detail?.accesses.forEach((item) => {
      const current = map.get(item.week) || { count: 0, eclo: 0 };
      current.count += 1;
      if (item.eclo) current.eclo += 1;
      map.set(item.week, current);
    });
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [detail?.accesses]);

  // Global maximum across all policies (active scenario + compared scenarios) to ensure no curve shoots off the top
  const maxWeekAccess = useMemo(() => {
    let max = Math.max(1, ...weekStats.map((item) => item[1].count));
    (["A", "B", "C"] as Scenario[]).forEach((s) => {
      const otherDetail = details[s];
      if (otherDetail) {
        const countMap = new Map<number, number>();
        otherDetail.accesses.forEach((acc) => {
          countMap.set(acc.week, (countMap.get(acc.week) || 0) + 1);
        });
        countMap.forEach((cnt) => {
          if (cnt > max) max = cnt;
        });
      }
    });
    return max;
  }, [details, weekStats]);

  // Cross-policy comparison overlay lines
  const otherPoliciesCurves = useMemo(() => {
    const otherScenarios = (["A", "B", "C"] as Scenario[]).filter((s) => s !== scenario);
    return otherScenarios.map((s) => {
      const otherDetail = details[s];
      if (!otherDetail) return null;
      const countMap = new Map<number, number>();
      otherDetail.accesses.forEach((acc) => {
        countMap.set(acc.week, (countMap.get(acc.week) || 0) + 1);
      });
      return {
        scenario: s,
        counts: weekStats.map(([w]) => countMap.get(w) || 0)
      };
    }).filter(Boolean) as { scenario: Scenario; counts: number[] }[];
  }, [details, scenario, weekStats]);

  // Supply Headroom & Capacity Hotspots (PS1 Standard)
  const supplyHeadroomMetrics = useMemo(() => {
    const totalUsage = detail?.validation.detail.location_usage ?? [];
    const totalSlots = totalUsage.reduce((sum, u) => sum + u.capacity, 0) || 1;
    const usedSlots = totalUsage.reduce((sum, u) => sum + u.used, 0);
    const quotaUsedPct = Math.round((usedSlots / totalSlots) * 100);
    const remainingHeadroomPct = Math.max(0, 100 - quotaUsedPct);

    // Identify the peak strain week from capacity_hotspots
    const weekHotspotMap = new Map<number, number>();
    hotspots.forEach((h) => {
      weekHotspotMap.set(h.week, (weekHotspotMap.get(h.week) || 0) + 1);
    });
    let peakWeek = 1;
    let peakCount = 0;
    weekHotspotMap.forEach((count, wk) => {
      if (count > peakCount) {
        peakCount = count;
        peakWeek = wk;
      }
    });

    const hasCriticalHotspots = hotspots.length > 20;
    const hasModerateHotspots = hotspots.length > 0;

    return {
      quotaUsedPct,
      remainingHeadroomPct,
      usedSlots,
      totalSlots,
      hotspotCount: hotspots.length,
      peakWeek: peakCount > 0 ? peakWeek : null,
      peakCount,
      statusLabel: hasCriticalHotspots
        ? "Zero-Buffer Bottleneck Risk"
        : hasModerateHotspots
        ? "Moderate Strain"
        : "Resilient Buffer",
      color: hasCriticalHotspots
        ? "var(--rose)"
        : hasModerateHotspots
        ? "var(--amber)"
        : "var(--emerald)",
    };
  }, [detail, hotspots]);

  // Exact mathematical breakdown matching activity delay_cost
  const exactDelayBreakdown = useMemo(() => {
    if (!detail) return [];
    // Group delay_cost by contract
    const contractDelayMap = new Map<string, { days: number; cost: number; tier: string }>();
    detail.activity_details.forEach((act) => {
      if (act.contract_overrun_days > 0 && act.delay_cost > 0) {
        const existing = contractDelayMap.get(act.contract_number) || {
          days: act.contract_overrun_days,
          cost: 0,
          tier: act.contract_number.includes("1") ? "P1 (100×)" : act.contract_number.includes("2") ? "P2 (10×)" : "P3 (1×)"
        };
        existing.cost += act.delay_cost;
        contractDelayMap.set(act.contract_number, existing);
      }
    });
    return Array.from(contractDelayMap.entries()).map(([cid, data]) => ({
      contract: cid,
      days: data.days,
      tier: data.tier,
      cost: Number(data.cost.toFixed(1))
    }));
  }, [detail]);

  // PS1 Priority-tiered breakdown (§2.5 & §2.7: 100× / 10× / 1×)
  const priorityTierSummary = useMemo(() => {
    const p1 = { days: 0, cost: 0, contracts: [] as string[] };
    const p2 = { days: 0, cost: 0, contracts: [] as string[] };
    const p3 = { days: 0, cost: 0, contracts: [] as string[] };

    exactDelayBreakdown.forEach((item) => {
      if (item.tier.includes("P1")) {
        p1.days += item.days;
        p1.cost += item.cost;
        p1.contracts.push(item.contract);
      } else if (item.tier.includes("P2")) {
        p2.days += item.days;
        p2.cost += item.cost;
        p2.contracts.push(item.contract);
      } else {
        p3.days += item.days;
        p3.cost += item.cost;
        p3.contracts.push(item.contract);
      }
    });

    const totalDays = p1.days + p2.days + p3.days;
    const totalCost = Number((p1.cost + p2.cost + p3.cost).toFixed(1));

    return {
      p1: { days: p1.days, cost: Number(p1.cost.toFixed(1)), contracts: p1.contracts },
      p2: { days: p2.days, cost: Number(p2.cost.toFixed(1)), contracts: p2.contracts },
      p3: { days: p3.days, cost: Number(p3.cost.toFixed(1)), contracts: p3.contracts },
      totalDays,
      totalCost,
      p1Pct: totalCost > 0 ? Math.round((p1.cost / totalCost) * 100) : 0,
      p2Pct: totalCost > 0 ? Math.round((p2.cost / totalCost) * 100) : 0,
      p3Pct: totalCost > 0 ? Math.round((p3.cost / totalCost) * 100) : 0,
    };
  }, [exactDelayBreakdown]);

  const totalDelayScore = detail?.score_breakdown.delay ?? 0;
  const totalEcloScore = detail?.score_breakdown.eclo ?? 0;
  const ecloNights = detail?.validation.detail.eclo_nights ?? 0;
  const totalScoreVal = totalDelayScore + totalEcloScore;

  // Cumulative Milestone Completion & Delay Slip Curves (PS1 Target vs Simulated)
  const sCurveData = useMemo(() => {
    if (!detail) {
      return {
        weeks: [] as number[],
        targetPoints: [] as { week: number; count: number; pct: number }[],
        policyPoints: { A: [], B: [], C: [] } as Record<Scenario, { week: number; count: number; pct: number }[]>,
        policyDelayPoints: { A: [], B: [], C: [] } as Record<Scenario, { week: number; delay: number }[]>,
        delayYMax: 60,
        totalContracts: 0,
        contractRows: [] as {
          contract: string;
          tier: string;
          tierClass: string;
          plannedTarget: string;
          actualFinish: string;
          isLate: boolean;
          overrunDays: number;
          targetWk: number;
          scenarioWeeks: Record<Scenario, number>;
          scenarioDates: Record<Scenario, string | null>;
          scenarioOverrun: Record<Scenario, number>;
        }[],
      };
    }

    const contractRows = detail.results.map((r) => {
      const contractActs = detail.activity_details.filter((a) => a.contract_number === r.contract_number);
      const actIds = new Set(contractActs.map((a) => a.activity_id));
      const plannedTarget = contractActs[0]?.planned_completion_date ?? r.simulated_completion_date;
      const targetWk = Math.max(
        1,
        Math.min(30, Math.ceil((new Date(plannedTarget).getTime() - new Date("2027-01-04").getTime()) / (7 * 24 * 3600 * 1000)))
      );

      const scenarioWeeks: Record<Scenario, number> = { A: 30, B: 30, C: 30 };
      const scenarioDates: Record<Scenario, string | null> = { A: null, B: null, C: null };
      const scenarioOverrun: Record<Scenario, number> = { A: 0, B: 0, C: 0 };

      (["A", "B", "C"] as Scenario[]).forEach((sc) => {
        const scDetail = details[sc];
        if (scDetail) {
          const scAccesses = scDetail.accesses.filter((acc) => actIds.has(acc.activity_id));
          if (scAccesses.length > 0) {
            scenarioWeeks[sc] = Math.max(...scAccesses.map((acc) => acc.week));
          } else {
            const res = scDetail.results.find((x) => x.contract_number === r.contract_number);
            if (res) {
              scenarioWeeks[sc] = Math.max(
                1,
                Math.min(30, Math.ceil((new Date(res.simulated_completion_date).getTime() - new Date("2027-01-04").getTime()) / (7 * 24 * 3600 * 1000)))
              );
            }
          }
          const res = scDetail.results.find((x) => x.contract_number === r.contract_number);
          scenarioDates[sc] = res?.simulated_completion_date ?? null;
          scenarioOverrun[sc] = res?.overrun_days ?? 0;
        }
      });

      const tier = r.contract_number.includes("1") ? "P1 (100×)" : r.contract_number.includes("2") ? "P2 (10×)" : "P3 (1×)";
      const tierClass = r.contract_number.includes("1") ? "tier-1" : r.contract_number.includes("2") ? "tier-2" : "tier-3";

      return {
        contract: r.contract_number,
        tier,
        tierClass,
        plannedTarget,
        actualFinish: r.simulated_completion_date,
        isLate: r.overrun_days > 0,
        overrunDays: r.overrun_days,
        targetWk,
        scenarioWeeks,
        scenarioDates,
        scenarioOverrun,
      };
    });

    const totalContracts = contractRows.length || 1;
    const allWeeks = Array.from({ length: 30 }, (_, i) => i + 1);

    const targetPoints = allWeeks.map((w) => {
      const count = contractRows.filter((c) => c.targetWk <= w).length;
      return { week: w, count, pct: Math.round((count / totalContracts) * 100) };
    });

    const policyPoints: Record<Scenario, { week: number; count: number; pct: number }[]> = {
      A: [],
      B: [],
      C: [],
    };

    const policyDelayPoints: Record<Scenario, { week: number; delay: number }[]> = {
      A: [],
      B: [],
      C: [],
    };

    (["A", "B", "C"] as Scenario[]).forEach((sc) => {
      policyPoints[sc] = allWeeks.map((w) => {
        const count = contractRows.filter((c) => c.scenarioWeeks[sc] <= w).length;
        return { week: w, count, pct: Math.round((count / totalContracts) * 100) };
      });
      policyDelayPoints[sc] = allWeeks.map((w) => {
        const delay = contractRows
          .filter((c) => c.scenarioWeeks[sc] <= w)
          .reduce((sum, c) => sum + (c.scenarioOverrun[sc] || 0), 0);
        return { week: w, delay };
      });
    });

    const maxObservedDelay = Math.max(
      20,
      ...(["A", "B", "C"] as Scenario[]).flatMap((sc) => policyDelayPoints[sc].map((p) => p.delay))
    );
    const delayYMax = Math.ceil(maxObservedDelay / 20) * 20;

    return {
      weeks: allWeeks,
      targetPoints,
      policyPoints,
      policyDelayPoints,
      delayYMax,
      totalContracts,
      contractRows,
    };
  }, [detail, details]);

  const activeAuditStats = useMemo(() => {
    const rows = sCurveData.contractRows;
    const total = rows.length;
    let onTime = 0;
    let delayed = 0;
    let totalOverrun = 0;
    rows.forEach((r) => {
      const overrun = r.scenarioOverrun[scenario] ?? r.overrunDays;
      if (overrun > 0) {
        delayed += 1;
        totalOverrun += overrun;
      } else {
        onTime += 1;
      }
    });
    const onTimePct = total > 0 ? Math.round((onTime / total) * 100) : 100;
    return { total, onTime, delayed, totalOverrun, onTimePct };
  }, [sCurveData.contractRows, scenario]);

  const activeColor = scenario === "A" ? "#10b981" : scenario === "B" ? "#ec4899" : "#8b5cf6";

  const chartCoordinates = useMemo(() => {
    const isDelay = milestoneChartMode === "delay";
    const yMax = isDelay ? sCurveData.delayYMax : 100;

    const getY = (val: number) => {
      const clamped = Math.max(0, Math.min(yMax, val));
      return 190 - (clamped / yMax) * 180;
    };

    const getX = (w: number) => ((w - 1) / 29) * 500;

    const targetPointsSvg = isDelay
      ? ""
      : sCurveData.targetPoints.map((p) => `${getX(p.week)},${getY(p.pct)}`).join(" ");

    const policyAPointsSvg = sCurveData.weeks
      .map((w) => {
        const val = isDelay
          ? sCurveData.policyDelayPoints.A[w - 1]?.delay ?? 0
          : sCurveData.policyPoints.A[w - 1]?.pct ?? 0;
        return `${getX(w)},${getY(val)}`;
      })
      .join(" ");

    const policyBPointsSvg = sCurveData.weeks
      .map((w) => {
        const val = isDelay
          ? sCurveData.policyDelayPoints.B[w - 1]?.delay ?? 0
          : sCurveData.policyPoints.B[w - 1]?.pct ?? 0;
        return `${getX(w)},${getY(val)}`;
      })
      .join(" ");

    const policyCPointsSvg = sCurveData.weeks
      .map((w) => {
        const val = isDelay
          ? sCurveData.policyDelayPoints.C[w - 1]?.delay ?? 0
          : sCurveData.policyPoints.C[w - 1]?.pct ?? 0;
        return `${getX(w)},${getY(val)}`;
      })
      .join(" ");

    const activeVertices = sCurveData.weeks.map((w) => {
      const val = isDelay
        ? sCurveData.policyDelayPoints[scenario][w - 1]?.delay ?? 0
        : sCurveData.policyPoints[scenario][w - 1]?.pct ?? 0;
      return {
        week: w,
        x: getX(w),
        y: getY(val),
        val,
      };
    });

    const activeAreaPoints = `${activeVertices.map((v) => `${v.x},${v.y}`).join(" ")} 500,190 0,190`;

    const yAxisLabels = isDelay
      ? [
          `${yMax}d`,
          `${Math.round(yMax * 0.75)}d`,
          `${Math.round(yMax * 0.5)}d`,
          `${Math.round(yMax * 0.25)}d`,
          "0d",
        ]
      : ["100%", "75%", "50%", "25%", "0%"];

    return {
      targetPointsSvg,
      policyAPointsSvg,
      policyBPointsSvg,
      policyCPointsSvg,
      activeVertices,
      activeAreaPoints,
      yAxisLabels,
      yMax,
      getX,
      getY,
    };
  }, [milestoneChartMode, sCurveData, scenario]);

  return (
    <>
      {/* Prominent Top KPI Metric Bar (Restored & Large) */}
      <div className="prominent-metric-strip">
        <div className="prominent-metric-card">
          <span>Penalty Score</span>
          <strong style={{ color: "var(--emerald)" }}>{totalScoreVal}</strong>
        </div>
        <div className="prominent-metric-card">
          <span>Total Overrun</span>
          <strong style={{ color: Number(scores?.overrun_days_total) > 0 ? "var(--rose)" : "var(--text-primary)" }}>
            {String(scores?.overrun_days_total ?? "0")}d
          </strong>
        </div>
        <div className="prominent-metric-card">
          <span>ECLO Nights</span>
          <strong style={{ color: ecloNights > 0 ? "var(--orange)" : "var(--text-primary)" }}>
            {ecloNights}n
          </strong>
        </div>
        <div className="prominent-metric-card">
          <span>Possession Accesses</span>
          <strong>{detail?.accesses.length ?? 0}</strong>
        </div>
        <div className="prominent-metric-card">
          <span>Search Runtime</span>
          <strong>{formatSeconds(run.diagnostics?.elapsed_seconds ?? run.solver_stats.elapsed_seconds)}</strong>
        </div>
      </div>

      {/* 4 Workspace Tabs: overview, activities, locations, contracts */}
      <nav className="workspace-tabs" role="tablist" aria-label="Policy tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            id={`tab-${item.id}`}
            role="tab"
            aria-selected={tab === item.id}
            aria-controls={`panel-${item.id}`}
            onClick={() => onTabChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {/* Tab Content Area */}
      <div className="tab-content-area">
        {!detail && (
          <div className="empty-result" style={{ padding: "40px", textAlign: "center" }}>
            {run.status === "running" ? <LoaderCircle size={32} className="spin" /> : <Gauge size={32} />}
            <h3 style={{ margin: "12px 0 6px" }}>Optimizing Policy {scenario}</h3>
            <p className="muted">{run.error || run.message || runLabel(run)}</p>
          </div>
        )}

        {detail && (
          <>
            {/* TAB 1: OVERVIEW & METRICS */}
            {tab === "overview" && (
              <div className="overview-tab-wrap">
                {/* Score Formulation Breakdown (Excess removed; hover breakdown math matches) */}
                <div className="score-formula-card">
                  <div className="score-formula-header">
                    <h4><Sparkles size={14} /> Penalty Formulation Breakdown</h4>
                  </div>

                  <div className="score-formula-blocks">
                    {/* Delay Term */}
                    <div
                      className="formula-block"
                      onMouseEnter={() => setHoveredFormulaTerm("delay")}
                      onMouseLeave={() => setHoveredFormulaTerm(null)}
                    >
                      <span>Delay Penalty:</span>
                      <strong>{totalDelayScore} pts</strong>
                      {hoveredFormulaTerm === "delay" && (
                        <div className="formula-popover">
                          <strong>Contract-by-Contract Delay Breakdown:</strong>
                          {exactDelayBreakdown.length > 0 ? (
                            exactDelayBreakdown.map((row) => (
                              <div key={row.contract}>
                                {row.contract} ({row.tier}): {row.days}d delay → <strong>{row.cost} pts</strong>
                              </div>
                            ))
                          ) : (
                            <div>Zero contract overruns (0.0 pts)</div>
                          )}
                          <div style={{ marginTop: "4px", borderTop: "1px solid var(--border-subtle)", paddingTop: "4px", color: "var(--emerald)" }}>
                            Total Delay Cost = {totalDelayScore} pts
                          </div>
                        </div>
                      )}
                    </div>

                    <span className="formula-op">+</span>

                    {/* ECLO Term */}
                    <div
                      className="formula-block"
                      onMouseEnter={() => setHoveredFormulaTerm("eclo")}
                      onMouseLeave={() => setHoveredFormulaTerm(null)}
                    >
                      <span>ECLO Penalty (5×):</span>
                      <strong>{totalEcloScore} pts</strong>
                      {hoveredFormulaTerm === "eclo" && (
                        <div className="formula-popover">
                          <strong>ECLO Calculation:</strong>
                          <div>{ecloNights} ECLO nights × 5 pts/night = <strong>{totalEcloScore} pts</strong></div>
                        </div>
                      )}
                    </div>

                    <span className="formula-op">=</span>

                    {/* Total Penalty Score */}
                    <div className="formula-block formula-total">
                      <span>Total Penalty Score:</span>
                      <strong>{totalScoreVal}</strong>
                    </div>
                  </div>
                </div>

                {/* Visual Operational Indicators Grid (PS1 §2.5 & §2.7: Minimal text, maximum visual clarity) */}
                <div className="indicator-grid">
                  {/* Card 1: Priority Overrun Breakdown (100× / 10× / 1×) */}
                  <div className="indicator-card">
                    <div className="indicator-card-top">
                      <div className="indicator-card-title">
                        <AlertTriangle size={14} color={priorityTierSummary.p1.cost > 0 ? "var(--rose)" : priorityTierSummary.totalCost > 0 ? "var(--amber)" : "var(--emerald)"} />
                        <span>Priority Overrun (§2.5)</span>
                      </div>
                      <span className={`indicator-status-badge ${priorityTierSummary.p1.cost > 0 ? "rose" : priorityTierSummary.totalCost > 0 ? "amber" : "emerald"}`}>
                        {priorityTierSummary.totalDays > 0 ? `${priorityTierSummary.totalDays}d delay · ${priorityTierSummary.totalCost} pts` : "0d delay · On Plan"}
                      </span>
                    </div>

                    {/* Proportional Multi-Segment Visual Bar */}
                    <div className="indicator-bar-track">
                      {priorityTierSummary.totalCost > 0 ? (
                        <>
                          <div style={{ width: `${priorityTierSummary.p1Pct}%`, backgroundColor: "var(--rose)" }} title={`P1 (100×): ${priorityTierSummary.p1Pct}% of penalty`} />
                          <div style={{ width: `${priorityTierSummary.p2Pct}%`, backgroundColor: "var(--amber)" }} title={`P2 (10×): ${priorityTierSummary.p2Pct}% of penalty`} />
                          <div style={{ width: `${priorityTierSummary.p3Pct}%`, backgroundColor: "var(--cyan)" }} title={`P3 (1×): ${priorityTierSummary.p3Pct}% of penalty`} />
                        </>
                      ) : (
                        <div style={{ width: "100%", backgroundColor: "var(--emerald)" }} title="All priorities on time" />
                      )}
                    </div>

                    {/* 3 Compact Chips for P1, P2, P3 */}
                    <div className="indicator-chips-row">
                      <span className={`indicator-chip ${priorityTierSummary.p1.days > 0 ? "rose" : "emerald"}`}>
                        <strong>P1 (100×):</strong> {priorityTierSummary.p1.days > 0 ? `${priorityTierSummary.p1.days}d · ${priorityTierSummary.p1.cost}p` : "0d"}
                      </span>
                      <span className={`indicator-chip ${priorityTierSummary.p2.days > 0 ? "amber" : "emerald"}`}>
                        <strong>P2 (10×):</strong> {priorityTierSummary.p2.days > 0 ? `${priorityTierSummary.p2.days}d · ${priorityTierSummary.p2.cost}p` : "0d"}
                      </span>
                      <span className={`indicator-chip ${priorityTierSummary.p3.days > 0 ? "cyan" : "emerald"}`}>
                        <strong>P3 (1×):</strong> {priorityTierSummary.p3.days > 0 ? `${priorityTierSummary.p3.days}d · ${priorityTierSummary.p3.cost}p` : "0d"}
                      </span>
                    </div>
                  </div>

                  {/* Card 2: Supply Headroom & Capacity Hotspots */}
                  <div className="indicator-card">
                    <div className="indicator-card-top">
                      <div className="indicator-card-title">
                        <Activity size={14} color={supplyHeadroomMetrics.color} />
                        <span>Supply Headroom (§2.7)</span>
                      </div>
                      <span className={`indicator-status-badge ${supplyHeadroomMetrics.remainingHeadroomPct < 20 ? "rose" : supplyHeadroomMetrics.remainingHeadroomPct < 40 ? "amber" : "emerald"}`}>
                        {supplyHeadroomMetrics.remainingHeadroomPct}% Headroom
                      </span>
                    </div>

                    {/* Supply Usage Gauge Bar */}
                    <div className="indicator-bar-track">
                      <div
                        style={{
                          width: `${supplyHeadroomMetrics.quotaUsedPct}%`,
                          backgroundColor: supplyHeadroomMetrics.color,
                        }}
                      />
                    </div>

                    {/* Headroom & Hotspots Chips */}
                    <div className="indicator-chips-row">
                      <span className="indicator-chip">
                        <strong>Quota:</strong> {supplyHeadroomMetrics.quotaUsedPct}%
                      </span>
                      <span className={`indicator-chip ${supplyHeadroomMetrics.hotspotCount > 20 ? "rose" : supplyHeadroomMetrics.hotspotCount > 0 ? "amber" : "emerald"}`}>
                        <strong>Hotspots:</strong> {supplyHeadroomMetrics.hotspotCount}
                      </span>
                      <span className="indicator-chip">
                        <strong>Peak:</strong> {supplyHeadroomMetrics.peakWeek ? `Week ${supplyHeadroomMetrics.peakWeek}` : "Even"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Charts & Hotspots Visual Grid */}
                <div className="visual-grid flex-stretch">
                  {/* Weekly Night Accesses with Continuous Line Overlay */}
                  <section className="data-panel chart-panel-wrap">
                    <div className="subheading">
                      <h3>Weekly Night Accesses</h3>
                      <span>{weekStats.length} weeks · Click bar to inspect in Activities</span>
                    </div>

                    <div className="week-chart-container">
                      <div className="week-chart-stage">
                        {/* SVG Connected Continuous Lines & Dots for other policies */}
                        {otherPoliciesCurves.length > 0 && (
                          <svg className="chart-overlay-svg" preserveAspectRatio="none" viewBox={`0 0 ${weekStats.length * 10} 100`}>
                            {otherPoliciesCurves.map((curve) => {
                              const coords = curve.counts.map((cnt, i) => ({
                                x: (i + 0.5) * 10,
                                y: 92 - (cnt / maxWeekAccess) * 80
                              }));
                              const pointsStr = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
                              const strokeColor = curve.scenario === "A" ? "#10b981" : curve.scenario === "B" ? "#ec4899" : "#8b5cf6";

                              return (
                                <g key={curve.scenario}>
                                  {/* Solid continuous line */}
                                  <polyline
                                    fill="none"
                                    stroke={strokeColor}
                                    strokeWidth="2"
                                    vectorEffect="non-scaling-stroke"
                                    opacity="0.85"
                                    points={pointsStr}
                                  />
                                  {/* Circular dots exactly centered on the line vertices */}
                                  {coords.map((c, ptIdx) => (
                                    <g key={ptIdx}>
                                      <path
                                        d={`M ${c.x.toFixed(2)} ${c.y.toFixed(2)} l 0.001 0`}
                                        stroke={strokeColor}
                                        strokeWidth="6"
                                        strokeLinecap="round"
                                        vectorEffect="non-scaling-stroke"
                                      />
                                      <path
                                        d={`M ${c.x.toFixed(2)} ${c.y.toFixed(2)} l 0.001 0`}
                                        stroke="#090d16"
                                        strokeWidth="2"
                                        strokeLinecap="round"
                                        vectorEffect="non-scaling-stroke"
                                      />
                                    </g>
                                  ))}
                                </g>
                              );
                            })}
                          </svg>
                        )}

                        {/* Bars Row */}
                        <div className="chart-bars-row">
                          {weekStats.map(([week, stat]) => {
                            const heightPct = Math.max(6, (stat.count / maxWeekAccess) * 80 + 8);
                            const isHovered = hoveredWeek?.week === week;
                            return (
                              <div
                                key={week}
                                className="chart-bar-wrap"
                                onMouseEnter={() => setHoveredWeek({ week, count: stat.count, eclo: stat.eclo })}
                                onMouseLeave={() => setHoveredWeek(null)}
                                onClick={() => onSelectWeek(week)}
                                title={`Click to inspect Week ${week}`}
                              >
                                {isHovered && (
                                  <div className="chart-tooltip">
                                    <strong>Week {week}</strong>: {stat.count} nights
                                    {stat.eclo > 0 && <span style={{ color: "var(--orange)", marginLeft: "4px" }}>({stat.eclo} ECLO)</span>}
                                  </div>
                                )}
                                <div className={`chart-bar ${stat.eclo > 0 ? "has-eclo" : ""}`} style={{ height: `${heightPct}%` }} />
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Week labels aligned with bars */}
                      <div className="week-labels-row">
                        {weekStats.map(([week]) => (
                          <div key={week} className="week-label-col">
                            {week}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="chart-legend">
                      <div className="chart-legend-item">
                        <span className="legend-swatch" style={{ background: "var(--cyan)" }} />
                        <span>Policy {scenario}</span>
                      </div>
                      <div className="chart-legend-item">
                        <span className="legend-swatch" style={{ background: "var(--orange)" }} />
                        <span>ECLO Active</span>
                      </div>
                      {otherPoliciesCurves.map((c) => (
                        <div key={c.scenario} className="chart-legend-item">
                          <span
                            className="legend-swatch"
                            style={{ background: c.scenario === "A" ? "#10b981" : c.scenario === "B" ? "#ec4899" : "#8b5cf6" }}
                          />
                          <span>Policy {c.scenario} Curve</span>
                        </div>
                      ))}
                    </div>
                  </section>

                  {/* Critical & High-Strain Sectors */}
                  <section className="data-panel bottleneck-panel-wrap">
                    <div className="subheading">
                      <h3>Critical & High-Strain Sectors</h3>
                      <span>{strainedBottlenecks.length} congested sectors</span>
                    </div>

                    <div className="bottleneck-list">
                      {strainedBottlenecks.map((item) => {
                        const loc = formatLocationName(item.location_id);
                        const isSaturated = item.saturation >= 1;
                        const isHighStrain = item.saturation >= 0.75;
                        const tierClass = isSaturated
                          ? "saturated"
                          : isHighStrain
                          ? "high-strain"
                          : "moderate-strain";
                        const pillTierClass = isSaturated
                          ? "tier-critical"
                          : isHighStrain
                          ? "tier-high"
                          : "tier-moderate";
                        const barColor = isSaturated
                          ? "var(--rose)"
                          : isHighStrain
                          ? "var(--amber)"
                          : "var(--cyan)";

                        return (
                          <div
                            key={`${item.location_id}-${item.week}`}
                            className={`bottleneck-item ${tierClass}`}
                            style={{ cursor: "pointer" }}
                            onClick={() => onSelectWeek(item.week)}
                            title={`Week ${item.week} · Click to filter activities`}
                          >
                            <div className="bottleneck-loc">
                              <div className="bottleneck-loc-header">
                                <strong>{loc.primary}</strong>
                                <span className="facility-tag">{loc.typeTag}</span>
                              </div>
                              <small>{item.location_id} · Week {item.week}</small>
                              {item.activities && item.activities.length > 0 && (
                                <div className="bottleneck-activities">
                                  {item.activities.slice(0, 3).join(", ")}
                                  {item.activities.length > 3 ? ` +${item.activities.length - 3}` : ""}
                                </div>
                              )}
                            </div>
                            <div className="bottleneck-stats">
                              <span className={`bottleneck-pill ${pillTierClass}`}>
                                {isSaturated
                                  ? `${item.used}/${item.capacity} Full`
                                  : `${item.used}/${item.capacity} (${item.pct}%)`}
                              </span>
                              <div className="bottleneck-mini-bar">
                                <div
                                  className="bottleneck-mini-bar-fill"
                                  style={{
                                    width: `${Math.min(100, item.pct)}%`,
                                    backgroundColor: barColor,
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                        );
                      })}
                      {!strainedBottlenecks.length && <p className="muted">No capacity strain detected (all sectors &lt;50%).</p>}
                    </div>
                  </section>
                </div>
              </div>
            )}

            {/* TAB 2: ACTIVITIES */}
            {tab === "activities" && (
              <Inspection
                activities={detail.activity_details ?? []}
                usage={detail.validation.detail.location_usage ?? []}
                view="activities"
                initialWeekFilter={weekFilter}
                onClearWeekFilter={onClearWeekFilter}
              />
            )}

            {/* TAB 3: LOCATIONS */}
            {tab === "locations" && (
              <Inspection
                activities={detail.activity_details ?? []}
                usage={detail.validation.detail.location_usage ?? []}
                view="locations"
                initialWeekFilter={weekFilter}
                onClearWeekFilter={onClearWeekFilter}
              />
            )}

            {/* TAB 4: MILESTONE & RISK (Delay Slip Trajectory / Completion S-Curve + Single-Policy Audit Table) */}
            {tab === "contracts" && (
              <div className="milestone-workspace tab-full-panel" role="tabpanel" id="panel-contracts" aria-labelledby="tab-contracts">
                {/* Chart Panel */}
                <section className="scurve-chart-panel">
                  <div className="subheading" style={{ marginBottom: "6px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "10px" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <h3 style={{ margin: 0 }}>
                          {milestoneChartMode === "delay" ? "Cumulative Schedule Delay Slip Trajectory" : "Cumulative Milestone Completion S-Curve"}
                        </h3>
                        <span className="chip" style={{ background: "var(--bg-shell)", color: "var(--text-dim)", fontSize: "10.5px" }}>
                          Horizon: 30 Weeks (Jan – Jul 2027)
                        </span>
                      </div>
                      <div className="muted" style={{ fontSize: "11px", marginTop: "3px" }}>
                        {hoveredSCurveWeek !== null ? (
                          milestoneChartMode === "delay" ? (
                            <span style={{ color: "var(--cyan)", fontWeight: 600 }}>
                              Week {hoveredSCurveWeek}: Pol A: +{sCurveData.policyDelayPoints.A[hoveredSCurveWeek - 1]?.delay ?? 0}d · Pol B: {sCurveData.policyDelayPoints.B[hoveredSCurveWeek - 1]?.delay ?? 0}d · Pol C: +{sCurveData.policyDelayPoints.C[hoveredSCurveWeek - 1]?.delay ?? 0}d (Active: {scenario})
                            </span>
                          ) : (
                            <span style={{ color: "var(--cyan)", fontWeight: 600 }}>
                              Week {hoveredSCurveWeek}: Target {sCurveData.targetPoints[hoveredSCurveWeek - 1]?.pct ?? 0}% · Pol A: {sCurveData.policyPoints.A[hoveredSCurveWeek - 1]?.pct ?? 0}% · Pol B: {sCurveData.policyPoints.B[hoveredSCurveWeek - 1]?.pct ?? 0}% · Pol C: {sCurveData.policyPoints.C[hoveredSCurveWeek - 1]?.pct ?? 0}%
                            </span>
                          )
                        ) : (
                          milestoneChartMode === "delay"
                            ? "Policy B enforces 0d slip · Policy C moderate · Policy A high · Hover week to inspect"
                            : "Hover week coordinate on chart to inspect cross-policy trajectory"
                        )}
                      </div>
                    </div>

                    {/* Mode Toggle Switcher */}
                    <div className="chart-mode-pill-group">
                      <button
                        type="button"
                        className={`chart-mode-pill ${milestoneChartMode === "delay" ? "active" : ""}`}
                        onClick={() => setMilestoneChartMode("delay")}
                      >
                        Delay Slip (Days)
                      </button>
                      <button
                        type="button"
                        className={`chart-mode-pill ${milestoneChartMode === "completion" ? "active" : ""}`}
                        onClick={() => setMilestoneChartMode("completion")}
                      >
                        Completion (%)
                      </button>
                    </div>
                  </div>

                  {/* Chart Stage: HTML labels prevent any text stretching or distortion */}
                  <div className="chart-plot-stage">
                    {/* Y-axis HTML Labels */}
                    <div className="chart-y-axis">
                      {chartCoordinates.yAxisLabels.map((lbl, idx) => (
                        <span key={idx}>{lbl}</span>
                      ))}
                    </div>

                    {/* Chart Plot Body */}
                    <div className="chart-plot-body">
                      <div className="chart-svg-wrap">
                        <svg viewBox="0 0 500 200" preserveAspectRatio="none" className="chart-svg">
                          <defs>
                            <linearGradient id="activeMilestoneAreaGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={activeColor} stopOpacity="0.25" />
                              <stop offset="100%" stopColor={activeColor} stopOpacity="0.01" />
                            </linearGradient>
                          </defs>

                          {/* 5 Horizontal Grid Lines */}
                          {[0, 25, 50, 75, 100].map((pct) => {
                            const y = 10 + (1 - pct / 100) * 180;
                            return (
                              <line
                                key={pct}
                                x1="0"
                                y1={y}
                                x2="500"
                                y2={y}
                                stroke="rgba(255,255,255,0.06)"
                                strokeDasharray={pct === 0 ? "none" : "3,3"}
                                strokeWidth={pct === 0 ? "1.5" : "1"}
                                vectorEffect="non-scaling-stroke"
                              />
                            );
                          })}

                          {/* 7 Vertical Grid Lines (W01, W05, W10, W15, W20, W25, W30) */}
                          {[1, 5, 10, 15, 20, 25, 30].map((w) => {
                            const x = ((w - 1) / 29) * 500;
                            return (
                              <line
                                key={w}
                                x1={x}
                                y1="10"
                                x2={x}
                                y2="190"
                                stroke="rgba(255,255,255,0.04)"
                                strokeDasharray="2,2"
                                vectorEffect="non-scaling-stroke"
                              />
                            );
                          })}

                          {/* Area Fill under Active Curve */}
                          <polygon
                            points={chartCoordinates.activeAreaPoints}
                            fill="url(#activeMilestoneAreaGrad)"
                          />

                          {/* Target Baseline Curve (Completion Mode only) */}
                          {milestoneChartMode === "completion" && chartCoordinates.targetPointsSvg && (
                            <polyline
                              points={chartCoordinates.targetPointsSvg}
                              fill="none"
                              stroke="#94a3b8"
                              strokeWidth="2"
                              strokeDasharray="5,4"
                              vectorEffect="non-scaling-stroke"
                            />
                          )}

                          {/* Zero-Delay Baseline (Delay Mode only) */}
                          {milestoneChartMode === "delay" && (
                            <line
                              x1="0"
                              y1="190"
                              x2="500"
                              y2="190"
                              stroke="#ec4899"
                              strokeWidth="1.5"
                              strokeDasharray="4,3"
                              opacity="0.6"
                              vectorEffect="non-scaling-stroke"
                            />
                          )}

                          {/* Policy A Curve (Emerald) */}
                          <polyline
                            points={chartCoordinates.policyAPointsSvg}
                            fill="none"
                            stroke="#10b981"
                            strokeWidth={scenario === "A" ? "3" : "1.6"}
                            opacity={scenario === "A" ? 1 : 0.45}
                            vectorEffect="non-scaling-stroke"
                          />

                          {/* Policy B Curve (Pink) */}
                          <polyline
                            points={chartCoordinates.policyBPointsSvg}
                            fill="none"
                            stroke="#ec4899"
                            strokeWidth={scenario === "B" ? "3" : "1.6"}
                            opacity={scenario === "B" ? 1 : 0.45}
                            vectorEffect="non-scaling-stroke"
                          />

                          {/* Policy C Curve (Violet) */}
                          <polyline
                            points={chartCoordinates.policyCPointsSvg}
                            fill="none"
                            stroke="#8b5cf6"
                            strokeWidth={scenario === "C" ? "3" : "1.6"}
                            opacity={scenario === "C" ? 1 : 0.45}
                            vectorEffect="non-scaling-stroke"
                          />

                          {/* Active Policy Data Points: use vectorEffect="non-scaling-stroke" + round stroke-linecap so dots stay mathematically 1:1 circular and NEVER stretch horizontally into ovals */}
                          {chartCoordinates.activeVertices.map((p) => {
                            const isHovered = hoveredSCurveWeek === p.week;
                            return (
                              <g key={p.week} pointerEvents="none">
                                {isHovered && (
                                  <path
                                    d={`M ${p.x} ${p.y} l 0.001 0`}
                                    stroke={activeColor}
                                    strokeWidth="16"
                                    strokeLinecap="round"
                                    opacity="0.35"
                                    vectorEffect="non-scaling-stroke"
                                  />
                                )}
                                <path
                                  d={`M ${p.x} ${p.y} l 0.001 0`}
                                  stroke="#0f172a"
                                  strokeWidth={isHovered ? "10" : "6.5"}
                                  strokeLinecap="round"
                                  vectorEffect="non-scaling-stroke"
                                />
                                <path
                                  d={`M ${p.x} ${p.y} l 0.001 0`}
                                  stroke={activeColor}
                                  strokeWidth={isHovered ? "6" : "3.5"}
                                  strokeLinecap="round"
                                  vectorEffect="non-scaling-stroke"
                                />
                              </g>
                            );
                          })}

                          {/* Hover Cross-Policy Comparison Dots */}
                          {hoveredSCurveWeek !== null && (
                            <g pointerEvents="none">
                              {(["A", "B", "C"] as Scenario[])
                                .filter((s) => s !== scenario)
                                .map((sc) => {
                                  const val =
                                    milestoneChartMode === "delay"
                                      ? sCurveData.policyDelayPoints[sc][hoveredSCurveWeek - 1]?.delay ?? 0
                                      : sCurveData.policyPoints[sc][hoveredSCurveWeek - 1]?.pct ?? 0;
                                  const color = sc === "A" ? "#10b981" : sc === "B" ? "#ec4899" : "#8b5cf6";
                                  const x = chartCoordinates.getX(hoveredSCurveWeek);
                                  const y = chartCoordinates.getY(val);
                                  return (
                                    <g key={sc}>
                                      <path
                                        d={`M ${x} ${y} l 0.001 0`}
                                        stroke="#0f172a"
                                        strokeWidth="7"
                                        strokeLinecap="round"
                                        vectorEffect="non-scaling-stroke"
                                      />
                                      <path
                                        d={`M ${x} ${y} l 0.001 0`}
                                        stroke={color}
                                        strokeWidth="4"
                                        strokeLinecap="round"
                                        vectorEffect="non-scaling-stroke"
                                      />
                                    </g>
                                  );
                                })}
                            </g>
                          )}

                          {/* Vertical Hover Guide Line */}
                          {hoveredSCurveWeek !== null && (
                            <line
                              x1={((hoveredSCurveWeek - 1) / 29) * 500}
                              y1="10"
                              x2={((hoveredSCurveWeek - 1) / 29) * 500}
                              y2="190"
                              stroke="var(--cyan)"
                              strokeWidth="1.5"
                              strokeDasharray="3,3"
                              vectorEffect="non-scaling-stroke"
                            />
                          )}

                          {/* Transparent Hover Hitboxes per Week */}
                          {sCurveData.weeks.map((w) => {
                            const x = ((w - 1) / 29) * 500 - 8;
                            return (
                              <rect
                                key={w}
                                x={x}
                                y="10"
                                width="16"
                                height="180"
                                fill="transparent"
                                style={{ cursor: "pointer" }}
                                onMouseEnter={() => setHoveredSCurveWeek(w)}
                                onMouseLeave={() => setHoveredSCurveWeek(null)}
                              />
                            );
                          })}
                        </svg>
                      </div>

                      {/* X-axis HTML Labels (Never stretched) */}
                      <div className="chart-x-axis">
                        <span>W01</span>
                        <span>W05</span>
                        <span>W10</span>
                        <span>W15</span>
                        <span>W20</span>
                        <span>W25</span>
                        <span>W30</span>
                      </div>
                    </div>
                  </div>

                  {/* Chart Legend */}
                  <div className="chart-legend" style={{ marginTop: "6px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "6px 12px" }}>
                    <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
                      {milestoneChartMode === "completion" && (
                        <div className="chart-legend-item">
                          <span className="legend-swatch" style={{ background: "#94a3b8", height: "2px", borderRadius: "0" }} />
                          <span>Target Baseline</span>
                        </div>
                      )}
                      <div className="chart-legend-item">
                        <span className="legend-swatch" style={{ background: "#10b981" }} />
                        <span style={{ fontWeight: scenario === "A" ? 700 : 400 }}>
                          Policy A {milestoneChartMode === "delay" && `(+${sCurveData.policyDelayPoints.A[29]?.delay ?? 0}d)`}
                        </span>
                      </div>
                      <div className="chart-legend-item">
                        <span className="legend-swatch" style={{ background: "#ec4899" }} />
                        <span style={{ fontWeight: scenario === "B" ? 700 : 400 }}>
                          Policy B {milestoneChartMode === "delay" && `(0d · Strict)`}
                        </span>
                      </div>
                      <div className="chart-legend-item">
                        <span className="legend-swatch" style={{ background: "#8b5cf6" }} />
                        <span style={{ fontWeight: scenario === "C" ? 700 : 400 }}>
                          Policy C {milestoneChartMode === "delay" && `(+${sCurveData.policyDelayPoints.C[29]?.delay ?? 0}d)`}
                        </span>
                      </div>
                    </div>

                    {milestoneChartMode === "delay" && (
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                        Policy B guarantees 0d delay slip
                      </span>
                    )}
                  </div>
                </section>

                {/* Milestone Delivery Audit Table (Single Active Policy Only) */}
                <section className="milestone-table-panel">
                  <div className="subheading" style={{ marginBottom: "8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <h3 style={{ display: "inline-flex", alignItems: "center", gap: "8px", margin: 0 }}>
                        Contract Delivery Audit
                        <span
                          style={{
                            fontSize: "11px",
                            padding: "2px 7px",
                            borderRadius: "12px",
                            background: scenario === "A" ? "rgba(16,185,129,0.15)" : scenario === "B" ? "rgba(236,72,153,0.15)" : "rgba(139,92,246,0.15)",
                            color: scenario === "A" ? "#10b981" : scenario === "B" ? "#ec4899" : "#8b5cf6",
                            border: `1px solid ${scenario === "A" ? "rgba(16,185,129,0.3)" : scenario === "B" ? "rgba(236,72,153,0.3)" : "rgba(139,92,246,0.3)"}`,
                            fontWeight: 700,
                          }}
                        >
                          Policy {scenario}
                        </span>
                      </h3>
                      <div className="muted" style={{ fontSize: "11px", marginTop: "2px" }}>
                        {activeAuditStats.total} contracts · {activeAuditStats.onTime} on-time ({activeAuditStats.onTimePct}%) · {activeAuditStats.delayed} delayed (+{activeAuditStats.totalOverrun}d)
                      </div>
                    </div>
                  </div>

                  <div className="milestone-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th style={{ width: "20%", whiteSpace: "nowrap" }}>Contract</th>
                          <th style={{ width: "16%", whiteSpace: "nowrap" }}>Tier</th>
                          <th style={{ width: "22%", whiteSpace: "nowrap" }}>Target Deadline</th>
                          <th style={{ width: "22%", whiteSpace: "nowrap" }}>Actual Finish</th>
                          <th style={{ width: "12%", whiteSpace: "nowrap" }}>Overrun</th>
                          <th style={{ width: "8%", whiteSpace: "nowrap" }}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sCurveData.contractRows.map((row) => {
                          const finishDate = row.scenarioDates[scenario] ?? row.actualFinish;
                          const overrun = row.scenarioOverrun[scenario] ?? row.overrunDays;
                          const isLate = overrun > 0;
                          return (
                            <tr key={row.contract}>
                              <td style={{ whiteSpace: "nowrap" }}><strong>{row.contract}</strong></td>
                              <td style={{ whiteSpace: "nowrap" }}><span className={`tier-badge ${row.tierClass}`}>{row.tier}</span></td>
                              <td style={{ whiteSpace: "nowrap", color: "var(--text-secondary)" }}>{row.plannedTarget}</td>
                              <td style={{ whiteSpace: "nowrap", color: isLate ? "var(--rose)" : "var(--emerald)", fontWeight: 600 }}>
                                {finishDate ?? "—"}
                              </td>
                              <td style={{ whiteSpace: "nowrap" }}>
                                <span
                                  className={`tier-badge ${isLate ? "tier-1" : ""}`}
                                  style={{
                                    background: isLate ? "var(--rose-soft)" : "var(--emerald-soft)",
                                    color: isLate ? "var(--rose)" : "var(--emerald)",
                                    fontWeight: 700,
                                  }}
                                >
                                  {isLate ? `+${overrun}d` : "0d"}
                                </span>
                              </td>
                              <td style={{ whiteSpace: "nowrap" }}>
                                <span
                                  style={{
                                    fontSize: "11px",
                                    fontWeight: 600,
                                    color: isLate ? "var(--rose)" : "var(--emerald)",
                                  }}
                                >
                                  {isLate ? "Delayed" : "On-Time"}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
