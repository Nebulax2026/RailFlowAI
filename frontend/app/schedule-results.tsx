"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, ArrowRight, CheckCircle2, ChevronRight, Clock3, Download, Gauge, Info, LoaderCircle, MoreVertical, Scale, ShieldAlert, ShieldCheck, Sparkles, X } from "lucide-react";
import { Inspection } from "./inspection";
import { AIAssistantPanel } from "./bonus-tools";
import { POLICIES, TABS, formatLocationName, type Scenario, type Job, type ScenarioDetail, type RunState, type DetailTab, type ReplanState, type PreventiveScenario, type PreventiveDetail } from "./schedule-types";

const PM_LABELS: Record<PreventiveScenario, string> = {
  D: "PM Priority",
  E: "PM Flexible",
};

export function ScheduleResults({
  job,
  details,
  onSandboxStateChange,
  preventiveJob,
  preventiveDetails,
}: {
  job: Job;
  details: Partial<Record<Scenario, ScenarioDetail>>;
  onSandboxStateChange?: (active: boolean) => void;
  preventiveJob?: Job;
  preventiveDetails?: Partial<Record<PreventiveScenario, PreventiveDetail>>;
}) {
  const [choice, setSelectedScenario] = useState<Scenario>("A");
  const selectedScenario = job.scenarios[choice] ? choice : ((Object.keys(job.scenarios)[0] as Scenario) ?? "A");
  const [tab, setTab] = useState<DetailTab>("overview");
  const [weekFilter, setWeekFilter] = useState<number | null>(null);

  const [activeReplan, setActiveReplan] = useState<ReplanState | null>(null);
  const [replanViewMode, setReplanViewMode] = useState<"baseline" | "replan">("replan");
  const [appliedReplans, setAppliedReplans] = useState<Partial<Record<Scenario, ReplanState>>>({});
  const [replanDownloadMenuOpen, setReplanDownloadMenuOpen] = useState(false);

  // D/E preventive tab state
  const [selectedPMScenario, setSelectedPMScenario] = useState<PreventiveScenario | null>(null);
  const [pmTradeoff, setPmTradeoff] = useState<Record<string, unknown> | null>(null);
  const [pmTradeoffOpen, setPmTradeoffOpen] = useState(false);
  const tradeoffFetched = useRef<string | null>(null);

  // Active tab: null = standard scenario, PreventiveScenario = D or E
  const isPMTabActive = selectedPMScenario !== null;

  const handleReplanCreated = (newReplan: ReplanState) => {
    setActiveReplan(newReplan);
    setReplanViewMode("replan");
    if (newReplan.scenario && newReplan.scenario !== selectedScenario) {
      setSelectedScenario(newReplan.scenario);
    }
  };

  const selected = details[selectedScenario];
  if (!job.scenarios[selectedScenario]) {
    return <div className="empty-result">No policies available for this job.</div>;
  }

  const handleBarClick = (week: number) => {
    setWeekFilter(week);
    setTab("activities");
  };

  const currentReplanForScenario = activeReplan && activeReplan.scenario === selectedScenario ? activeReplan : null;
  const isApplied = !!(currentReplanForScenario && appliedReplans[selectedScenario]?.replan_id === currentReplanForScenario.replan_id);

  const isSandboxActive = !!(currentReplanForScenario && currentReplanForScenario.status === "completed");

  // Auto-fetch tradeoff when both D/E complete
  useEffect(() => {
    if (!preventiveJob) return;
    const d = preventiveJob.scenarios["D" as PreventiveScenario];
    const e = preventiveJob.scenarios["E" as PreventiveScenario];
    const bothDone = d?.feasible && e?.feasible
      && preventiveDetails?.["D" as PreventiveScenario]
      && preventiveDetails?.["E" as PreventiveScenario];
    if (!bothDone || tradeoffFetched.current === preventiveJob.job_id) return;
    tradeoffFetched.current = preventiveJob.job_id;
    fetch(`/api/ps1/jobs/${preventiveJob.job_id}/preventive-tradeoff`)
      .then((r) => r.json())
      .then((data) => setPmTradeoff(data))
      .catch(() => {});
  }, [preventiveJob, preventiveDetails]);

  useEffect(() => {
    onSandboxStateChange?.(isSandboxActive);
  }, [isSandboxActive, onSandboxStateChange]);

  const handleApplyReplan = () => {
    if (!currentReplanForScenario) return;
    setAppliedReplans((prev) => ({ ...prev, [selectedScenario]: currentReplanForScenario }));
    setReplanViewMode("replan");
    setActiveReplan(null);
    setReplanDownloadMenuOpen(false);
  };

  const handleDiscardReplan = () => {
    setActiveReplan(null);
    setReplanViewMode("baseline");
    setReplanDownloadMenuOpen(false);
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
            const isSelected = !isPMTabActive && selectedScenario === scenario;

            return (
              <div
                key={scenario}
                role="tab"
                tabIndex={0}
                className={`top-policy-card policy-${scenario.toLowerCase()} ${isSelected ? "selected" : ""}`}
                onClick={() => { setSelectedPMScenario(null); setSelectedScenario(scenario); }}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { setSelectedPMScenario(null); setSelectedScenario(scenario); } }}
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

          {/* D/E Preventive tabs — only shown when preventiveJob exists */}
          {preventiveJob && (["D", "E"] as PreventiveScenario[]).map((pmScenario) => {
            const run = preventiveJob.scenarios[pmScenario];
            if (!run) return null;
            const isSelected = isPMTabActive && selectedPMScenario === pmScenario;
            const isPending = run.status === "queued" || run.status === "running";
            return (
              <div
                key={pmScenario}
                role="tab"
                tabIndex={0}
                className={`top-policy-card policy-pm policy-${pmScenario.toLowerCase()} ${isSelected ? "selected" : ""}`}
                onClick={() => setSelectedPMScenario(pmScenario)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setSelectedPMScenario(pmScenario); }}
                aria-selected={isSelected}
              >
                <div className="top-policy-left">
                  <span className="top-policy-letter pm-letter">{pmScenario}</span>
                  <div className="top-policy-meta">
                    <div className="top-policy-name-row">
                      <strong>Policy {pmScenario}</strong>
                      <span className="top-policy-subtitle pm-subtitle">({PM_LABELS[pmScenario]})</span>
                    </div>
                  </div>
                </div>
                <div className="top-policy-right">
                  <span className={`top-policy-pill ${isPending ? "running" : run.feasible ? "completed" : ""}`}>
                    {isPending ? <LoaderCircle size={10} className="spin" style={{display:"inline"}} /> : null}
                    {isPending ? "Optimizing" : run.feasible ? "Feasible" : run.status}
                  </span>
                </div>
                <div className="top-policy-progress-line pm-progress" style={{ width: `${run.progress}%`, opacity: run.progress > 0 ? 1 : 0 }} />
              </div>
            );
          })}
        </div>

        {/* Center Main Active Workspace */}
        <main className="center-workspace" key={job.job_id}>
          {/* Top Sticky Re-plan Sandbox Banner */}
          {currentReplanForScenario && currentReplanForScenario.status === "completed" && (
            <div className="replan-sandbox-banner" role="region" aria-label="Re-plan Sandbox Controls">
              <div className="replan-banner-left">
                <div className="replan-banner-title-row">
                  <span className="replan-badge-sandbox">RE-PLAN SANDBOX</span>
                  <span className="replan-scenario-badge">Scenario {currentReplanForScenario.scenario}</span>
                  <span className="replan-disruption-tag">
                    {currentReplanForScenario.disruption.location_id} · W{currentReplanForScenario.disruption.start_week}–W{currentReplanForScenario.disruption.end_week} (Cap: {currentReplanForScenario.disruption.capacity})
                  </span>
                </div>
                <div className="replan-banner-stats">
                  <div className="replan-banner-stat-chip">
                    <span className="chip-label">Preserved Plan</span>
                    <strong className="chip-value cyan">{currentReplanForScenario.diff.summary?.preserved_percent ?? 100}%</strong>
                  </div>
                  <div className="replan-banner-stat-chip">
                    <span className="chip-label">Moved Activities</span>
                    <strong className={`chip-value ${(currentReplanForScenario.diff.summary?.moved_activities ?? 0) > 0 ? "amber" : "emerald"}`}>
                      {currentReplanForScenario.diff.summary?.moved_activities ?? 0}
                    </strong>
                  </div>
                  <div className="replan-banner-stat-chip">
                    <span className="chip-label">Score Delta</span>
                    <strong className={`chip-value ${Number(currentReplanForScenario.diff.summary?.score_delta ?? 0) <= 0 ? "emerald" : "rose"}`}>
                      {Number(currentReplanForScenario.diff.summary?.score_delta ?? 0) >= 0 ? `+${currentReplanForScenario.diff.summary?.score_delta ?? 0}` : currentReplanForScenario.diff.summary?.score_delta} pts
                    </strong>
                  </div>
                </div>
              </div>

              <div className="replan-banner-controls">
                {/* Baseline vs Replan Toggle */}
                <div className="replan-view-toggle">
                  <button
                    type="button"
                    className={`replan-toggle-btn ${replanViewMode === "baseline" ? "active" : ""}`}
                    onClick={() => setReplanViewMode("baseline")}
                  >
                    Baseline
                  </button>
                  <button
                    type="button"
                    className={`replan-toggle-btn ${replanViewMode === "replan" ? "active" : ""}`}
                    onClick={() => setReplanViewMode("replan")}
                  >
                    Re-plan (Revised)
                  </button>
                </div>

                {/* Action Buttons */}
                <div className="replan-action-group">
                  <button
                    type="button"
                    className={`replan-btn-apply ${isApplied ? "applied" : ""}`}
                    onClick={handleApplyReplan}
                    title="Apply this re-planned schedule as the active view and exit sandbox"
                  >
                    {isApplied ? "✓ Applied to Schedule" : "Apply to Schedule"}
                  </button>

                  {/* Re-plan Split Download Button Group */}
                  <div className="split-button-group replan-download-split">
                    <a
                      className="split-button-main"
                      href={`/api/ps1/jobs/${job.job_id}/scenarios/${currentReplanForScenario.scenario}/replans/${currentReplanForScenario.replan_id}/download`}
                      download
                      title="Download complete re-optimized ZIP package"
                    >
                      <Download size={13} />
                      Download ZIP
                    </a>
                    <button
                      type="button"
                      className="split-button-trigger"
                      onClick={() => setReplanDownloadMenuOpen(!replanDownloadMenuOpen)}
                      aria-label="More re-plan download options"
                    >
                      <MoreVertical size={13} />
                    </button>

                    {replanDownloadMenuOpen && (
                      <div className="dropdown-menu" onMouseLeave={() => setReplanDownloadMenuOpen(false)}>
                        <a
                          className="dropdown-item"
                          href={`/api/ps1/jobs/${job.job_id}/scenarios/${currentReplanForScenario.scenario}/replans/${currentReplanForScenario.replan_id}/files/SCHEDULE_ACCESS.csv`}
                          download
                        >
                          <Download size={12} /> SCHEDULE_ACCESS.csv
                        </a>
                        <a
                          className="dropdown-item"
                          href={`/api/ps1/jobs/${job.job_id}/scenarios/${currentReplanForScenario.scenario}/replans/${currentReplanForScenario.replan_id}/files/SCHEDULE_OCCUPANCY.csv`}
                          download
                        >
                          <Download size={12} /> SCHEDULE_OCCUPANCY.csv
                        </a>
                        <a
                          className="dropdown-item"
                          href={`/api/ps1/jobs/${job.job_id}/scenarios/${currentReplanForScenario.scenario}/replans/${currentReplanForScenario.replan_id}/files/RESULTS.csv`}
                          download
                        >
                          <Download size={12} /> RESULTS.csv
                        </a>
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    className="replan-btn-discard"
                    onClick={handleDiscardReplan}
                    title="Close sandbox and discard preview"
                  >
                    ✕ Discard
                  </button>
                </div>
              </div>
              <div className="replan-sandbox-highlight-line" aria-hidden="true" />
            </div>
          )}

          {isPMTabActive && selectedPMScenario && preventiveJob ? (
            <PreventiveScenarioPanel
              scenario={selectedPMScenario}
              job={preventiveJob}
              detail={preventiveDetails?.[selectedPMScenario]}
              tradeoff={pmTradeoff}
              tradeoffOpen={pmTradeoffOpen}
              onOpenTradeoff={() => setPmTradeoffOpen(true)}
              onCloseTradeoff={() => setPmTradeoffOpen(false)}
            />
          ) : (
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
              activeReplan={currentReplanForScenario}
              replanViewMode={replanViewMode}
            />
          )}
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
        activeReplan={activeReplan}
        onReplanCreated={handleReplanCreated}
      />
    </section>
  );
}

function PreventiveScenarioPanel({
  scenario,
  job,
  detail,
  tradeoff,
  tradeoffOpen,
  onOpenTradeoff,
  onCloseTradeoff,
}: {
  scenario: PreventiveScenario;
  job: Job;
  detail?: PreventiveDetail;
  tradeoff: Record<string, unknown> | null;
  tradeoffOpen: boolean;
  onOpenTradeoff: () => void;
  onCloseTradeoff: () => void;
}) {
  const run = job.scenarios[scenario];
  const scores = detail?.validation.soft_scores;
  const isPending = run?.status === "queued" || run?.status === "running";
  const bothReady = (["D", "E"] as PreventiveScenario[]).every((s) => job.scenarios[s]?.feasible);

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

  return (
    <div className="preventive-workspace-panel">
      {/* PM Banner */}
      <div className="preventive-inline-banner">
        <div className="preventive-inline-left">
          <span className="pm-eyebrow">PREVENTIVE MAINTENANCE · Policy {scenario}</span>
          <h2 className="pm-title">{scenario === "D" ? "PM Priority — Fixed Windows" : "PM Flexible — Project Protected"}</h2>
          <p className="pm-desc">
            {scenario === "D"
              ? "Every maintenance occurrence is scheduled at its planned window. Project activities work around maintenance."
              : "Project delivery is prioritised. Maintenance may be deferred by up to 7 days when windows conflict."}
          </p>
        </div>
        <div className="preventive-inline-actions">
          {bothReady && (
            <button
              className="secondary-button"
              onClick={onOpenTradeoff}
              disabled={!tradeoff}
              title={tradeoff ? "View D vs E trade-off comparison" : "Waiting for both scenarios to complete…"}
            >
              <Scale size={14} /> D vs E Trade-off
            </button>
          )}
          {detail?.validation.feasible && (
            <a
              className="split-button-main"
              href={`${API_BASE}/api/ps1/jobs/${job.job_id}/scenarios/${scenario}/files/MAINTENANCE_SCHEDULE.csv`}
              download
            >
              <Download size={13} /> Maintenance Schedule
            </a>
          )}
        </div>
      </div>

      {/* Status / Progress */}
      {isPending && (
        <div className="pm-progress-row">
          <LoaderCircle size={15} className="spin" />
          <span>{run?.message ?? "Optimizing…"}</span>
          <div className="pm-progress-bar"><div style={{ width: `${run?.progress ?? 0}%` }} /></div>
        </div>
      )}

      {/* Metrics Grid */}
      {scores && (
        <div className="pm-metrics-grid">
          <div className="pm-metric-card">
            <span>Project Overrun</span>
            <strong style={{ color: Number(scores.total_project_overrun_days ?? 0) > 0 ? "var(--rose)" : "var(--emerald)" }}>
              {scores.total_project_overrun_days ?? 0}d
            </strong>
          </div>
          <div className="pm-metric-card">
            <span>On-time Maintenance</span>
            <strong style={{ color: "var(--emerald)" }}>{scores.on_time_maintenance_count ?? "—"}</strong>
          </div>
          <div className="pm-metric-card">
            <span>Deferred Maintenance</span>
            <strong style={{ color: Number(scores.deferred_maintenance_count ?? 0) > 0 ? "var(--amber)" : "var(--emerald)" }}>
              {scores.deferred_maintenance_count ?? 0}
            </strong>
          </div>
          <div className="pm-metric-card">
            <span>Total Deferral</span>
            <strong style={{ color: Number(scores.total_maintenance_deferral_days ?? 0) > 0 ? "var(--amber)" : "var(--emerald)" }}>
              {scores.total_maintenance_deferral_days ?? 0}
            </strong>
          </div>
          <div className="pm-metric-card">
            <span>Max Deferral</span>
            <strong style={{ color: Number(scores.maximum_maintenance_deferral_days ?? 0) > 0 ? "var(--amber)" : "var(--emerald)" }}>
              {scores.maximum_maintenance_deferral_days ?? 0}
            </strong>
          </div>
          <div className="pm-metric-card">
            <span>Objective Score</span>
            <strong>{scores.project_objective_score ?? "—"}</strong>
          </div>
        </div>
      )}

      {/* Maintenance schedule table */}
      {detail?.maintenance && detail.maintenance.length > 0 && (
        <div className="pm-maintenance-table-wrap">
          <div className="subheading"><h3>Maintenance Schedule</h3><span>{detail.maintenance.length} occurrences</span></div>
          <div className="milestone-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Occurrence</th>
                  <th>Location</th>
                  <th>Day</th>
                  <th>Planned</th>
                  <th>Actual</th>
                  <th>Deferral</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {detail.maintenance.slice(0, 40).map((m) => (
                  <tr key={m.occurrence_id}>
                    <td><strong style={{ fontSize: "11px" }}>{m.occurrence_id}</strong></td>
                    <td style={{ fontSize: "11px", color: "var(--text-muted)" }}>{m.location_id}</td>
                    <td style={{ fontSize: "11px" }}>{m.start_time}–{m.end_time}</td>
                    <td style={{ fontSize: "11px" }}>{m.planned_date}</td>
                    <td style={{ fontSize: "11px", color: m.deferred ? "var(--amber)" : "var(--emerald)", fontWeight: 600 }}>
                      {m.actual_date}
                    </td>
                    <td>
                      {m.deferral_days > 0
                        ? <span style={{ fontSize: "10px", padding: "1px 5px", borderRadius: "3px", background: "rgba(245,158,11,0.2)", color: "var(--amber)", fontWeight: 700 }}>+{m.deferral_days}d</span>
                        : <span style={{ fontSize: "10px", color: "var(--emerald)" }}>On time</span>}
                    </td>
                    <td>
                      <span style={{ fontSize: "10px", color: m.conflict_driven ? "var(--rose)" : m.deferred ? "var(--amber)" : "var(--emerald)" }}>
                        {m.conflict_driven ? "Conflict" : m.deferred ? "Deferred" : "On time"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tradeoff Modal */}
      {tradeoffOpen && tradeoff && (
        <div className="tradeoff-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onCloseTradeoff(); }}>
          <section className="tradeoff-modal" role="dialog" aria-modal="true" aria-labelledby="pm-tradeoff-title">
            <header>
              <div>
                <span className="eyebrow">Validated D vs E comparison</span>
                <h2 id="pm-tradeoff-title">{String(tradeoff.title ?? "D vs E Trade-off")}</h2>
              </div>
              <button className="icon-button" aria-label="Close" onClick={onCloseTradeoff}><X size={19} /></button>
            </header>
            <div className="tradeoff-policy-copy">
              <p><strong>D</strong> fixes every maintenance occurrence at its planned window.</p>
              <p><strong>E</strong> protects the project objective first and may defer maintenance by up to seven days.</p>
            </div>
            {tradeoff.metrics ? (
              <div className="tradeoff-table-wrap">
                <table>
                  <thead><tr><th>Metric</th><th>D</th><th>E</th><th>Δ E−D</th></tr></thead>
                  <tbody>
                    {Object.entries(tradeoff.metrics as Record<string, { D: number; E: number; delta_E_minus_D: number | null }>).map(([name, values]) => (
                      <tr key={name}>
                        <th style={{ fontSize: "11px", textAlign: "left", fontWeight: 500 }}>{name.replace(/_/g, " ")}</th>
                        <td>{values.D?.toLocaleString()}</td>
                        <td>{values.E?.toLocaleString()}</td>
                        <td style={{ color: values.delta_E_minus_D == null ? undefined : values.delta_E_minus_D > 0 ? "var(--rose)" : values.delta_E_minus_D < 0 ? "var(--emerald)" : undefined }}>
                          {values.delta_E_minus_D == null ? "—" : `${values.delta_E_minus_D > 0 ? "+" : ""}${values.delta_E_minus_D}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <p className="tradeoff-conclusion">{String(tradeoff.summary ?? "")}</p>
            <footer><button className="primary-button" onClick={onCloseTradeoff}>Close</button></footer>
          </section>
        </div>
      )}
    </div>
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
  onClearWeekFilter,
  activeReplan,
  replanViewMode,
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
  activeReplan?: ReplanState | null;
  replanViewMode?: "baseline" | "replan";
}) {
  const isReplanActive = replanViewMode === "replan" && !!activeReplan && activeReplan.status === "completed";
  const replanSummary = isReplanActive ? activeReplan.diff.summary : undefined;

  const currentDetail = useMemo((): ScenarioDetail | undefined => {
    if (!detail) return undefined;
    if (!isReplanActive || !activeReplan?.solution) return detail;
    const sol = activeReplan.solution;
    return {
      ...detail,
      activity_details: sol.activity_details ?? detail.activity_details,
      accesses: sol.accesses ?? detail.accesses,
      results: (sol.results as any) ?? detail.results,
      score_breakdown: sol.score_breakdown ?? detail.score_breakdown,
      solver_stats: sol.solver_stats ?? detail.solver_stats,
      validation: {
        ...detail.validation,
        feasible: sol.validation.feasible,
        hard_violations: sol.validation.hard_violations ?? detail.validation.hard_violations,
        soft_scores: {
          ...detail.validation.soft_scores,
          ...sol.validation.soft_scores,
        },
        detail: {
          ...detail.validation.detail,
          ...sol.validation.detail,
          location_usage: sol.validation.detail?.location_usage ?? detail.validation.detail.location_usage,
          capacity_hotspots: sol.validation.detail?.capacity_hotspots ?? detail.validation.detail.capacity_hotspots,
        },
      },
    };
  }, [detail, isReplanActive, activeReplan]);

  const scores = currentDetail?.validation.soft_scores;
  const hotspots = currentDetail?.validation.detail.capacity_hotspots ?? [];
  const strainedBottlenecks = useMemo(() => {
    if (!currentDetail) return [];
    const allUsage = currentDetail.validation.detail.location_usage ?? [];
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
  }, [currentDetail, hotspots]);
  const [hoveredWeek, setHoveredWeek] = useState<{ week: number; count: number; eclo: number } | null>(null);
  const [hoveredFormulaTerm, setHoveredFormulaTerm] = useState<string | null>(null);
  const [hoveredSCurveWeek, setHoveredSCurveWeek] = useState<number | null>(null);
  const [milestoneChartMode, setMilestoneChartMode] = useState<"delay" | "completion">("delay");

  // Group scheduled accesses by week for the active policy
  const weekStats = useMemo(() => {
    const map = new Map<number, { count: number; eclo: number }>();
    currentDetail?.accesses.forEach((item) => {
      const current = map.get(item.week) || { count: 0, eclo: 0 };
      current.count += 1;
      if (item.eclo) current.eclo += 1;
      map.set(item.week, current);
    });
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [currentDetail?.accesses]);

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
    if (!currentDetail) return [];
    // Group delay_cost by contract
    const contractDelayMap = new Map<string, { days: number; cost: number; tier: string }>();
    currentDetail.activity_details.forEach((act) => {
      if (act.contract_overrun_days > 0 && act.delay_cost > 0) {
        const existing = contractDelayMap.get(act.contract_number) || {
          days: act.contract_overrun_days,
          cost: 0,
          tier: act.contract_priority === 1 ? "P1 (100×)" : act.contract_priority === 2 ? "P2 (10×)" : "P3 (1×)"
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
  }, [currentDetail]);

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

  const totalDelayScore = currentDetail?.score_breakdown.delay ?? 0;
  const excessNights = Number(currentDetail?.validation.soft_scores?.excess_access_nights_total ?? 0);
  const totalExcessScore = currentDetail?.score_breakdown.excess_supply ?? (excessNights * 7);
  const totalEcloScore = currentDetail?.score_breakdown.eclo ?? 0;
  const ecloNights = currentDetail?.validation.detail.eclo_nights ?? 0;
  const totalScoreVal = Number((totalDelayScore + totalExcessScore + totalEcloScore).toFixed(1));

  // Cumulative Milestone Completion & Delay Slip Curves (PS1 Target vs Simulated)
  const sCurveData = useMemo(() => {
    if (!currentDetail) {
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

    const contractRows = currentDetail.results.map((r) => {
      const contractActs = currentDetail.activity_details.filter((a) => a.contract_number === r.contract_number);
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
        const scDetail = sc === scenario && isReplanActive && activeReplan?.solution ? currentDetail : details[sc];
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

      const contractPriority = contractActs[0]?.contract_priority ?? 3;
      const tier = contractPriority === 1 ? "P1 (100×)" : contractPriority === 2 ? "P2 (10×)" : "P3 (1×)";
      const tierClass = contractPriority === 1 ? "tier-1" : contractPriority === 2 ? "tier-2" : "tier-3";

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
  }, [currentDetail, details, scenario, isReplanActive, activeReplan]);

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

  // 1. Penalty Score
  const baselineScore = detail ? Number(((detail.score_breakdown.delay ?? 0) + (detail.score_breakdown.excess_supply ?? (Number(detail.validation.soft_scores?.excess_access_nights_total ?? 0) * 7)) + (detail.score_breakdown.eclo ?? 0)).toFixed(1)) : 0;
  const scoreDelta = replanSummary?.score_delta ?? 0;
  const displayScore = isReplanActive ? totalScoreVal : baselineScore;

  // 2. Total Overrun Days
  const baselineOverrun = Number(detail?.validation.soft_scores?.overrun_days_total ?? 0);
  const revisedOverrun = Number(currentDetail?.validation.soft_scores?.overrun_days_total ?? baselineOverrun);
  const overrunDelta = replanSummary?.overrun_delta ?? (isReplanActive ? revisedOverrun - baselineOverrun : 0);
  const displayOverrun = isReplanActive ? revisedOverrun : baselineOverrun;

  // 3. ECLO Nights
  const baselineEclo = detail?.validation.detail.eclo_nights ?? 0;
  const revisedEclo = currentDetail?.validation.detail.eclo_nights ?? baselineEclo;
  const ecloDelta = replanSummary?.eclo_delta ?? (isReplanActive ? revisedEclo - baselineEclo : 0);
  const displayEclo = isReplanActive ? revisedEclo : baselineEclo;

  // 4. Excess Access Nights
  const baselineExcess = Number(detail?.validation.soft_scores?.excess_access_nights_total ?? 0);
  const revisedExcess = Number(currentDetail?.validation.soft_scores?.excess_access_nights_total ?? baselineExcess);
  const excessDelta = replanSummary?.excess_delta ?? (isReplanActive ? revisedExcess - baselineExcess : 0);
  const displayExcess = isReplanActive ? revisedExcess : baselineExcess;

  // 5. Possession Accesses Count
  const baselineAccesses = detail?.accesses.length ?? 0;
  const revisedAccesses = currentDetail?.accesses.length ?? baselineAccesses;
  const accessesDelta = replanSummary?.accesses_delta ?? (isReplanActive ? revisedAccesses - baselineAccesses : 0);
  const displayAccesses = isReplanActive ? revisedAccesses : baselineAccesses;

  const contractChangeMap = useMemo(() => {
    const map = new Map<string, { overrun_delta: number; after_completion: string }>();
    if (isReplanActive && activeReplan?.diff.contract_changes) {
      activeReplan.diff.contract_changes.forEach((c) => map.set(c.contract_number, c));
    }
    return map;
  }, [isReplanActive, activeReplan]);

  return (
    <>
      {/* Prominent Top KPI Metric Bar (Restored & Large) */}
      <div className="prominent-metric-strip">
        <div className={`prominent-metric-card ${isReplanActive && scoreDelta !== 0 ? "replan-highlight" : ""}`}>
          <span>Penalty Score</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
            <strong style={{ color: "var(--emerald)" }}>{displayScore}</strong>
            {replanSummary && (
              <span
                className={`replan-kpi-delta ${Number(scoreDelta) > 0 ? "rose" : Number(scoreDelta) < 0 ? "emerald" : "neutral"}`}
                title={`Re-plan score delta: ${scoreDelta} pts`}
              >
                {Number(scoreDelta) >= 0 ? `+${scoreDelta}` : scoreDelta}
              </span>
            )}
          </div>
        </div>

        <div className={`prominent-metric-card ${isReplanActive && overrunDelta !== 0 ? "replan-highlight" : ""}`}>
          <span>Total Overrun</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
            <strong style={{ color: displayOverrun > 0 ? "var(--rose)" : "var(--text-primary)" }}>
              {displayOverrun}d
            </strong>
            {isReplanActive && overrunDelta !== 0 && (
              <span
                className={`replan-kpi-delta ${overrunDelta > 0 ? "rose" : "emerald"}`}
                title={`Re-plan overrun delta: ${overrunDelta > 0 ? `+${overrunDelta}` : overrunDelta} days`}
              >
                {overrunDelta > 0 ? `+${overrunDelta}d` : `${overrunDelta}d`}
              </span>
            )}
          </div>
        </div>

        <div className={`prominent-metric-card ${isReplanActive && ecloDelta !== 0 ? "replan-highlight" : ""}`}>
          <span>ECLO Nights</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
            <strong style={{ color: displayEclo > 0 ? "var(--orange)" : "var(--text-primary)" }}>
              {displayEclo}n
            </strong>
            {isReplanActive && ecloDelta !== 0 && (
              <span
                className={`replan-kpi-delta ${ecloDelta > 0 ? "rose" : "emerald"}`}
                title={`Re-plan ECLO delta: ${ecloDelta > 0 ? `+${ecloDelta}` : ecloDelta} nights`}
              >
                {ecloDelta > 0 ? `+${ecloDelta}n` : `${ecloDelta}n`}
              </span>
            )}
          </div>
        </div>

        <div className={`prominent-metric-card ${isReplanActive && excessDelta !== 0 ? "replan-highlight" : ""}`}>
          <span>Excess Access</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
            <strong style={{ color: displayExcess > 0 ? "var(--amber)" : "var(--text-primary)" }}>
              {displayExcess}n
            </strong>
            {isReplanActive && excessDelta !== 0 && (
              <span
                className={`replan-kpi-delta ${excessDelta > 0 ? "rose" : "emerald"}`}
                title={`Re-plan excess access delta: ${excessDelta > 0 ? `+${excessDelta}` : excessDelta} nights`}
              >
                {excessDelta > 0 ? `+${excessDelta}n` : `${excessDelta}n`}
              </span>
            )}
          </div>
        </div>

        <div className={`prominent-metric-card ${isReplanActive && accessesDelta !== 0 ? "replan-highlight" : ""}`}>
          <span>Possession Accesses</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
            <strong>{displayAccesses}</strong>
            {isReplanActive && accessesDelta !== 0 && (
              <span
                className={`replan-kpi-delta ${accessesDelta > 0 ? "amber" : "emerald"}`}
                title={`Re-plan accesses delta: ${accessesDelta > 0 ? `+${accessesDelta}` : accessesDelta}`}
              >
                {accessesDelta > 0 ? `+${accessesDelta}` : `${accessesDelta}`}
              </span>
            )}
          </div>
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
                {/* Score Formulation Breakdown (§2.5: Delay + Excess Supply + ECLO) */}
                <div className="score-formula-card">
                  <div className="score-formula-header">
                    <h4><Sparkles size={14} /> Penalty Formulation Breakdown (§2.5)</h4>
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

                    {/* Excess Supply Term (7×) */}
                    <div
                      className="formula-block"
                      onMouseEnter={() => setHoveredFormulaTerm("excess")}
                      onMouseLeave={() => setHoveredFormulaTerm(null)}
                    >
                      <span>Excess Supply (7×):</span>
                      <strong>{totalExcessScore} pts</strong>
                      {hoveredFormulaTerm === "excess" && (
                        <div className="formula-popover">
                          <strong>Excess Access Nights (§2.5):</strong>
                          <div>{excessNights} excess nights × 7 pts/night = <strong>{totalExcessScore} pts</strong></div>
                          <div style={{ marginTop: "4px", fontSize: "11px", color: "var(--emerald)" }}>
                            {excessNights === 0 ? "Nominal supply respected (0 excess nights)" : "Flexible supply buffer utilized"}
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
                            return (
                              <div
                                key={week}
                                className="chart-bar-wrap"
                                onMouseEnter={() => setHoveredWeek({ week, count: stat.count, eclo: stat.eclo })}
                                onMouseLeave={() => setHoveredWeek(null)}
                                onClick={() => onSelectWeek(week)}
                                title={`Click to inspect Week ${week}`}
                              >
                                <div className={`chart-bar ${stat.eclo > 0 ? "has-eclo" : ""}`} style={{ height: `${heightPct}%` }} />
                              </div>
                            );
                          })}
                        </div>

                        {/* Interactive Floating Tooltip right above hovered bar */}
                        {hoveredWeek !== null && (() => {
                          const w = hoveredWeek.week;
                          const wIdx = weekStats.findIndex(([wk]) => wk === w);
                          const pctX = ((wIdx + 0.5) / weekStats.length) * 100;
                          const barHeightPct = Math.max(6, (hoveredWeek.count / maxWeekAccess) * 80 + 8);
                          const topPct = 100 - barHeightPct;

                          const countA = details.A?.accesses.filter((a) => a.week === w).length ?? 0;
                          const countB = details.B?.accesses.filter((a) => a.week === w).length ?? 0;
                          const countC = details.C?.accesses.filter((a) => a.week === w).length ?? 0;

                          return (
                            <div
                              style={{
                                position: "absolute",
                                left: `${pctX}%`,
                                top: `${Math.max(8, topPct)}%`,
                                transform: `translate(${pctX < 18 ? "0%" : pctX > 82 ? "-100%" : "-50%"}, -120%)`,
                                pointerEvents: "none",
                                zIndex: 20,
                                background: "rgba(15, 23, 42, 0.95)",
                                border: "1px solid var(--cyan)",
                                borderRadius: "6px",
                                padding: "5px 9px",
                                boxShadow: "0 4px 16px rgba(0, 0, 0, 0.5)",
                                whiteSpace: "nowrap",
                                backdropFilter: "blur(6px)",
                                fontSize: "11px",
                                display: "flex",
                                flexDirection: "column",
                                gap: "2px",
                              }}
                            >
                              <div style={{ fontWeight: 700, color: "#ffffff", display: "flex", alignItems: "center", gap: "6px" }}>
                                <span style={{ color: "var(--cyan)" }}>Week {w}</span>
                                <span style={{ color: activeColor }}>
                                  Pol {scenario}: {hoveredWeek.count} nights{hoveredWeek.eclo > 0 ? ` (${hoveredWeek.eclo} ECLO)` : ""}
                                </span>
                              </div>
                              <div style={{ fontSize: "10px", display: "flex", gap: "8px" }}>
                                <span style={{ color: "#10b981" }}>Pol A: {countA}n</span>
                                <span style={{ color: "#ec4899" }}>Pol B: {countB}n</span>
                                <span style={{ color: "#8b5cf6" }}>Pol C: {countC}n</span>
                              </div>
                            </div>
                          );
                        })()}
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
                activities={currentDetail?.activity_details ?? []}
                usage={currentDetail?.validation.detail.location_usage ?? []}
                view="activities"
                initialWeekFilter={weekFilter}
                onClearWeekFilter={onClearWeekFilter}
                activityChanges={isReplanActive ? activeReplan?.diff.activity_changes : undefined}
              />
            )}

            {/* TAB 3: LOCATIONS */}
            {tab === "locations" && (
              <Inspection
                activities={currentDetail?.activity_details ?? []}
                usage={currentDetail?.validation.detail.location_usage ?? []}
                view="locations"
                initialWeekFilter={weekFilter}
                onClearWeekFilter={onClearWeekFilter}
                activityChanges={isReplanActive ? activeReplan?.diff.activity_changes : undefined}
              />
            )}

            {/* TAB 4: MILESTONE & RISK (Delay Slip Trajectory / Completion S-Curve + Single-Policy Audit Table) */}
            {tab === "contracts" && (
              <div className="milestone-workspace tab-full-panel" role="tabpanel" id="panel-contracts" aria-labelledby="tab-contracts">
                {/* Chart Panel */}
                <section className="scurve-chart-panel">
                  <div className="subheading" style={{ marginBottom: "6px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <h3 style={{ margin: 0 }}>
                          {milestoneChartMode === "delay" ? "Cumulative Schedule Delay Slip Trajectory" : "Cumulative Milestone Completion S-Curve"}
                        </h3>
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

                        {/* Interactive Floating Tooltip right above hovered points */}
                        {hoveredSCurveWeek !== null && (() => {
                          const w = hoveredSCurveWeek;
                          const activePt = chartCoordinates.activeVertices.find((p) => p.week === w);
                          const pctX = (chartCoordinates.getX(w) / 500) * 100;
                          const activeDelay = sCurveData.policyDelayPoints[scenario][w - 1]?.delay ?? 0;
                          const activePct = sCurveData.policyPoints[scenario][w - 1]?.pct ?? 0;
                          const pctY = activePt ? (activePt.y / 200) * 100 : 50;

                          const delA = sCurveData.policyDelayPoints.A[w - 1]?.delay ?? 0;
                          const delB = sCurveData.policyDelayPoints.B[w - 1]?.delay ?? 0;
                          const delC = sCurveData.policyDelayPoints.C[w - 1]?.delay ?? 0;

                          const targetPct = sCurveData.targetPoints[w - 1]?.pct ?? 0;
                          const pA = sCurveData.policyPoints.A[w - 1]?.pct ?? 0;
                          const pB = sCurveData.policyPoints.B[w - 1]?.pct ?? 0;
                          const pC = sCurveData.policyPoints.C[w - 1]?.pct ?? 0;

                          return (
                            <div
                              style={{
                                position: "absolute",
                                left: `${pctX}%`,
                                top: `${Math.max(10, pctY)}%`,
                                transform: `translate(${pctX < 18 ? "0%" : pctX > 82 ? "-100%" : "-50%"}, -120%)`,
                                pointerEvents: "none",
                                zIndex: 20,
                                background: "rgba(15, 23, 42, 0.95)",
                                border: "1px solid var(--cyan)",
                                borderRadius: "6px",
                                padding: "5px 9px",
                                boxShadow: "0 4px 16px rgba(0, 0, 0, 0.5)",
                                whiteSpace: "nowrap",
                                backdropFilter: "blur(6px)",
                                fontSize: "11px",
                                display: "flex",
                                flexDirection: "column",
                                gap: "2px",
                              }}
                            >
                              <div style={{ fontWeight: 700, color: "#ffffff", display: "flex", alignItems: "center", gap: "6px" }}>
                                <span style={{ color: "var(--cyan)" }}>Week {w}</span>
                                <span style={{ color: activeColor }}>
                                  Pol {scenario}: {milestoneChartMode === "delay" ? (activeDelay > 0 ? `+${activeDelay}d` : `${activeDelay}d`) : `${activePct}%`}
                                </span>
                              </div>
                              <div style={{ fontSize: "10px", display: "flex", gap: "8px" }}>
                                {milestoneChartMode === "delay" ? (
                                  <>
                                    <span style={{ color: "#10b981" }}>Pol A: +{delA}d</span>
                                    <span style={{ color: "#ec4899" }}>Pol B: {delB}d</span>
                                    <span style={{ color: "#8b5cf6" }}>Pol C: +{delC}d</span>
                                  </>
                                ) : (
                                  <>
                                    <span style={{ color: "#94a3b8" }}>Target: {targetPct}%</span>
                                    <span style={{ color: "#10b981" }}>A: {pA}%</span>
                                    <span style={{ color: "#ec4899" }}>B: {pB}%</span>
                                    <span style={{ color: "#8b5cf6" }}>C: {pC}%</span>
                                  </>
                                )}
                              </div>
                            </div>
                          );
                        })()}
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
                              <td style={{ whiteSpace: "nowrap" }}>
                                <strong>{row.contract}</strong>
                                {contractChangeMap.has(row.contract) && (
                                  <span
                                    style={{
                                      marginLeft: "6px",
                                      fontSize: "10px",
                                      fontWeight: 700,
                                      padding: "1px 5px",
                                      borderRadius: "3px",
                                      background: "rgba(245, 158, 11, 0.2)",
                                      color: "var(--amber)",
                                      border: "1px solid rgba(245, 158, 11, 0.4)",
                                    }}
                                    title={`Re-plan finish: ${contractChangeMap.get(row.contract)!.after_completion} (Δ: ${contractChangeMap.get(row.contract)!.overrun_delta > 0 ? `+${contractChangeMap.get(row.contract)!.overrun_delta}d` : `${contractChangeMap.get(row.contract)!.overrun_delta}d`})`}
                                  >
                                    Re-plan Δ
                                  </span>
                                )}
                              </td>
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
