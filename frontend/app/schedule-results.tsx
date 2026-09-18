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

  const maxWeekAccess = Math.max(1, ...weekStats.map((item) => item[1].count));

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

  const totalDelayScore = detail?.score_breakdown.delay ?? 0;
  const totalEcloScore = detail?.score_breakdown.eclo ?? 0;
  const ecloNights = detail?.validation.detail.eclo_nights ?? 0;
  const totalScoreVal = totalDelayScore + totalEcloScore;

  // Cumulative Milestone Completion S-Curve (PS1 Target vs Simulated)
  const sCurveData = useMemo(() => {
    if (!detail) {
      return {
        weeks: [] as number[],
        targetPoints: [] as { week: number; count: number; pct: number }[],
        policyPoints: { A: [], B: [], C: [] } as Record<Scenario, { week: number; count: number; pct: number }[]>,
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

    (["A", "B", "C"] as Scenario[]).forEach((sc) => {
      policyPoints[sc] = allWeeks.map((w) => {
        const count = contractRows.filter((c) => c.scenarioWeeks[sc] <= w).length;
        return { week: w, count, pct: Math.round((count / totalContracts) * 100) };
      });
    });

    return { weeks: allWeeks, targetPoints, policyPoints, totalContracts, contractRows };
  }, [detail, details]);

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

                {/* Supply Headroom & Capacity Hotspots Indicator (PS1 Standard) */}
                <div className="indicator-grid">
                  <div className="indicator-card">
                    <Activity size={24} color={supplyHeadroomMetrics.color} />
                    <div>
                      <h4>Supply Headroom & Hotspot Risk</h4>
                      <p style={{ color: supplyHeadroomMetrics.color }}>
                        {supplyHeadroomMetrics.remainingHeadroomPct}% Remaining Headroom · {supplyHeadroomMetrics.hotspotCount} Capacity Hotspots
                      </p>
                      <small className="muted" style={{ fontSize: "11px" }}>
                        {supplyHeadroomMetrics.usedSlots}/{supplyHeadroomMetrics.totalSlots} Location Supply slots used ({supplyHeadroomMetrics.quotaUsedPct}% quota)
                        {supplyHeadroomMetrics.peakWeek
                          ? ` · Peak strain in Week ${supplyHeadroomMetrics.peakWeek} (${supplyHeadroomMetrics.peakCount} zero-buffer sectors)`
                          : " · 0 zero-headroom sectors"}
                      </small>
                    </div>
                  </div>

                  <div className="indicator-card">
                    <ShieldCheck size={24} color={scenario === "C" ? "var(--cyan)" : "var(--text-muted)"} />
                    <div>
                      <h4>ECLO Continuous Window Rule</h4>
                      <p>
                        {scenario === "C"
                          ? "Compliant (Max 2 consecutive calendar weeks per line)"
                          : scenario === "A"
                            ? "Compliant (ECLO Forbidden)"
                            : "Exempt (Flexible placement allowed)"}
                      </p>
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
                                y: 94 - (cnt / maxWeekAccess) * 84
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
                            const heightPct = Math.max(6, (stat.count / maxWeekAccess) * 84 + 6);
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

            {/* TAB 4: MILESTONE & RISK (Cumulative Completion S-Curve + Audit Table) */}
            {tab === "contracts" && (
              <div className="milestone-workspace tab-full-panel" role="tabpanel" id="panel-contracts" aria-labelledby="tab-contracts">
                {/* S-Curve Chart Panel */}
                <section className="scurve-chart-panel">
                  <div className="subheading" style={{ marginBottom: "6px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <h3>Cumulative Milestone Completion S-Curve</h3>
                      <span className="chip" style={{ background: "var(--bg-shell)", color: "var(--text-dim)", fontSize: "10.5px" }}>
                        Horizon: 30 Weeks (Jan – Jul 2027)
                      </span>
                    </div>
                    <span className="muted" style={{ fontSize: "11px" }}>
                      {hoveredSCurveWeek !== null ? (
                        <span style={{ color: "var(--cyan)", fontWeight: 600 }}>
                          Week {hoveredSCurveWeek}: Target {sCurveData.targetPoints[hoveredSCurveWeek - 1]?.pct ?? 0}% ({sCurveData.targetPoints[hoveredSCurveWeek - 1]?.count ?? 0}/{sCurveData.totalContracts} contracts)
                          {" · "}Active ({scenario}): {sCurveData.policyPoints[scenario][hoveredSCurveWeek - 1]?.pct ?? 0}%
                        </span>
                      ) : (
                        "Hover week coordinate on chart to inspect cross-policy trajectory"
                      )}
                    </span>
                  </div>

                  <div className="scurve-stage-wrap">
                    <svg viewBox="0 0 600 320" className="scurve-svg" preserveAspectRatio="none">
                      {/* Grid Lines: Y-axis (0%, 25%, 50%, 75%, 100%) */}
                      {[0, 25, 50, 75, 100].map((pct) => {
                        const y = 20 + 260 - (pct / 100) * 260;
                        return (
                          <g key={pct}>
                            <line x1="45" y1={y} x2="585" y2={y} stroke="rgba(255,255,255,0.06)" strokeDasharray="3,3" />
                            <text x="38" y={y + 3} textAnchor="end" fill="#64748b" fontSize="10" fontWeight="600">
                              {pct}%
                            </text>
                          </g>
                        );
                      })}

                      {/* Grid Lines: X-axis (Weeks 1, 5, 10, 15, 20, 25, 30) */}
                      {[1, 5, 10, 15, 20, 25, 30].map((w) => {
                        const x = 45 + ((w - 1) / 29) * 535;
                        return (
                          <g key={w}>
                            <line x1={x} y1="20" x2={x} y2="280" stroke="rgba(255,255,255,0.04)" />
                            <text x={x} y="302" textAnchor="middle" fill="#64748b" fontSize="10" fontWeight="600">
                              W{String(w).padStart(2, "0")}
                            </text>
                          </g>
                        );
                      })}

                      {/* Target Baseline Curve (Dashed Slate) */}
                      <polyline
                        points={sCurveData.targetPoints.map((p) => `${45 + ((p.week - 1) / 29) * 535},${20 + 260 - (p.pct / 100) * 260}`).join(" ")}
                        fill="none"
                        stroke="#94a3b8"
                        strokeWidth="2"
                        strokeDasharray="5,4"
                        vectorEffect="non-scaling-stroke"
                      />

                      {/* Policy A Curve (Emerald) */}
                      <polyline
                        points={sCurveData.policyPoints.A.map((p) => `${45 + ((p.week - 1) / 29) * 535},${20 + 260 - (p.pct / 100) * 260}`).join(" ")}
                        fill="none"
                        stroke="#10b981"
                        strokeWidth={scenario === "A" ? "3" : "1.6"}
                        opacity={scenario === "A" ? 1 : 0.45}
                        vectorEffect="non-scaling-stroke"
                      />

                      {/* Policy B Curve (Pink) */}
                      <polyline
                        points={sCurveData.policyPoints.B.map((p) => `${45 + ((p.week - 1) / 29) * 535},${20 + 260 - (p.pct / 100) * 260}`).join(" ")}
                        fill="none"
                        stroke="#ec4899"
                        strokeWidth={scenario === "B" ? "3" : "1.6"}
                        opacity={scenario === "B" ? 1 : 0.45}
                        vectorEffect="non-scaling-stroke"
                      />

                      {/* Policy C Curve (Violet) */}
                      <polyline
                        points={sCurveData.policyPoints.C.map((p) => `${45 + ((p.week - 1) / 29) * 535},${20 + 260 - (p.pct / 100) * 260}`).join(" ")}
                        fill="none"
                        stroke="#8b5cf6"
                        strokeWidth={scenario === "C" ? "3" : "1.6"}
                        opacity={scenario === "C" ? 1 : 0.45}
                        vectorEffect="non-scaling-stroke"
                      />

                      {/* Active Policy Data Points (Dots on vertices) */}
                      {sCurveData.policyPoints[scenario].map((p) => {
                        const x = 45 + ((p.week - 1) / 29) * 535;
                        const y = 20 + 260 - (p.pct / 100) * 260;
                        const isHovered = hoveredSCurveWeek === p.week;
                        const activeColor = scenario === "A" ? "#10b981" : scenario === "B" ? "#ec4899" : "#8b5cf6";

                        return (
                          <circle
                            key={p.week}
                            cx={x}
                            cy={y}
                            r={isHovered ? 5 : 2.5}
                            fill={activeColor}
                            stroke="#0f172a"
                            strokeWidth="1.5"
                          />
                        );
                      })}

                      {/* Vertical Hover Guide Line */}
                      {hoveredSCurveWeek !== null && (
                        <line
                          x1={45 + ((hoveredSCurveWeek - 1) / 29) * 535}
                          y1="20"
                          x2={45 + ((hoveredSCurveWeek - 1) / 29) * 535}
                          y2="280"
                          stroke="var(--cyan)"
                          strokeWidth="1.5"
                          strokeDasharray="3,3"
                        />
                      )}

                      {/* Transparent Hover Hitboxes per Week */}
                      {sCurveData.weeks.map((w) => {
                        const x = 45 + ((w - 1) / 29) * 535 - 9;
                        return (
                          <rect
                            key={w}
                            x={x}
                            y="15"
                            width="18"
                            height="275"
                            fill="transparent"
                            style={{ cursor: "pointer" }}
                            onMouseEnter={() => setHoveredSCurveWeek(w)}
                            onMouseLeave={() => setHoveredSCurveWeek(null)}
                          />
                        );
                      })}
                    </svg>
                  </div>

                  {/* Chart Legend */}
                  <div className="chart-legend" style={{ marginTop: "8px", flexWrap: "wrap", gap: "6px 12px" }}>
                    <div className="chart-legend-item">
                      <span className="legend-swatch" style={{ background: "#94a3b8", height: "2px", borderRadius: "0" }} />
                      <span>Target Baseline</span>
                    </div>
                    <div className="chart-legend-item">
                      <span className="legend-swatch" style={{ background: "#10b981" }} />
                      <span style={{ fontWeight: scenario === "A" ? 700 : 400 }}>Policy A</span>
                    </div>
                    <div className="chart-legend-item">
                      <span className="legend-swatch" style={{ background: "#ec4899" }} />
                      <span style={{ fontWeight: scenario === "B" ? 700 : 400 }}>Policy B</span>
                    </div>
                    <div className="chart-legend-item">
                      <span className="legend-swatch" style={{ background: "#8b5cf6" }} />
                      <span style={{ fontWeight: scenario === "C" ? 700 : 400 }}>Policy C</span>
                    </div>
                  </div>
                </section>

                {/* Milestone Delivery Audit Table */}
                <section className="milestone-table-panel">
                  <div className="subheading" style={{ marginBottom: "8px" }}>
                    <h3>Contract Milestone Delivery Audit</h3>
                    <span className="muted">{sCurveData.contractRows.length} contracts</span>
                  </div>

                  <div className="milestone-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Contract</th>
                          <th>Tier</th>
                          <th>Target</th>
                          <th>Simulated</th>
                          <th>Overrun</th>
                          <th>Pol A</th>
                          <th>Pol B</th>
                          <th>Pol C</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sCurveData.contractRows.map((row) => (
                          <tr key={row.contract}>
                            <td><strong>{row.contract}</strong></td>
                            <td><span className={`tier-badge ${row.tierClass}`}>{row.tier}</span></td>
                            <td>{row.plannedTarget}</td>
                            <td style={{ color: row.isLate ? "var(--rose)" : "var(--emerald)", fontWeight: 600 }}>
                              {row.actualFinish}
                            </td>
                            <td>
                              <span
                                className={`tier-badge ${row.isLate ? "tier-1" : ""}`}
                                style={{
                                  background: row.isLate ? "var(--rose-soft)" : "var(--emerald-soft)",
                                  color: row.isLate ? "var(--rose)" : "var(--emerald)",
                                }}
                              >
                                {row.isLate ? `+${row.overrunDays}d` : "On-Time"}
                              </span>
                            </td>
                            <td>{row.scenarioDates.A ?? "—"}</td>
                            <td>{row.scenarioDates.B ?? "—"}</td>
                            <td>{row.scenarioDates.C ?? "—"}</td>
                          </tr>
                        ))}
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
