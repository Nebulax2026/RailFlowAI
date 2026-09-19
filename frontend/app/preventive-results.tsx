"use client";

import { AlertTriangle, CheckCircle2, Clock3, Download, LoaderCircle, Scale, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api-client";
import type { Job, PreventiveDetail, PreventiveScenario, PreventiveTradeoff } from "./schedule-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const LABELS: Record<PreventiveScenario, string> = {
  D: "Preventive Maintenance Priority",
  E: "Flexible Preventive Maintenance"
};
const METRIC_LABELS: Record<string, string> = {
  project_objective_score: "Project objective score",
  total_project_overrun_days: "Project overrun days",
  priority_weighted_project_delay: "Priority-weighted delay",
  contracts_overrunning: "Contracts overrunning",
  project_accesses_moved: "Project accesses moved",
  maintenance_occurrence_count: "Maintenance occurrences",
  on_time_maintenance_count: "On-time maintenance",
  deferred_maintenance_count: "Deferred maintenance",
  total_maintenance_deferral_days: "Total deferral days",
  average_maintenance_deferral_days: "Average deferral days",
  maximum_maintenance_deferral_days: "Maximum deferral days",
  solver_elapsed_seconds: "Solver elapsed seconds"
};

export function PreventiveComparisonResults({
  job,
  details
}: {
  job: Job;
  details: Partial<Record<PreventiveScenario, PreventiveDetail>>;
}) {
  const [tradeoff, setTradeoff] = useState<PreventiveTradeoff | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [tradeoffError, setTradeoffError] = useState("");
  const openedForJob = useRef<string | null>(null);
  const viewButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const bothValidated = (["D", "E"] as PreventiveScenario[]).every((scenario) => {
    const run = job.scenarios[scenario];
    return run?.status === "completed" && run.feasible === true && details[scenario]?.validation.feasible;
  });
  const terminal = (["D", "E"] as PreventiveScenario[]).every((scenario) =>
    ["completed", "failed", "cancelled"].includes(job.scenarios[scenario]?.status ?? "queued")
  );

  useEffect(() => {
    if (!bothValidated || openedForJob.current === job.job_id) return;
    openedForJob.current = job.job_id;
    let disposed = false;
    api<PreventiveTradeoff>(`/api/ps1/jobs/${job.job_id}/preventive-tradeoff`)
      .then((result) => {
        if (disposed) return;
        setTradeoff(result);
        setModalOpen(true);
      })
      .catch((error) => { if (!disposed) setTradeoffError(error instanceof Error ? error.message : "Trade-off unavailable."); });
    return () => { disposed = true; };
  }, [bothValidated, job.job_id]);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    window.setTimeout(() => viewButtonRef.current?.focus(), 0);
  }, []);

  useEffect(() => {
    if (!modalOpen) return;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeModal();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeModal, modalOpen]);

  return (
    <section className="preventive-results" aria-label="Preventive Maintenance Comparison">
      <div className="preventive-heading">
        <div><span className="eyebrow">Experimental CP-SAT comparison</span><h1>Preventive Maintenance Comparison</h1></div>
        <div className="preventive-actions">
          <button ref={viewButtonRef} className="secondary-button" disabled={!tradeoff} onClick={() => setModalOpen(true)}>
            <Scale size={15} />View trade-off
          </button>
          <a className={`primary-button ${bothValidated ? "" : "disabled"}`} aria-disabled={!bothValidated}
             href={bothValidated ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}>
            <Download size={15} />Download D/E
          </a>
        </div>
      </div>
      <p className="preventive-note">The official A/B/C dataset and submission outputs are unchanged. This comparison dataset adds one five-access demonstration contract that forces D/E to make different choices.</p>

      <div className="preventive-grid">
        {(["D", "E"] as PreventiveScenario[]).map((scenario) => {
          const run = job.scenarios[scenario];
          const detail = details[scenario];
          const scores = detail?.validation.soft_scores;
          return (
            <article className={`preventive-card policy-${scenario.toLowerCase()}`} key={scenario}>
              <header><span className="preventive-letter">{scenario}</span><div><h2>Scenario {scenario}</h2><p>{LABELS[scenario]}</p></div>
                <span className={`preventive-status ${run?.status ?? "queued"}`}>
                  {run?.status === "running" ? <LoaderCircle size={14} className="spin" /> : run?.feasible ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}
                  {run?.status ?? "queued"}
                </span>
              </header>
              <div className="preventive-progress"><span style={{ width: `${run?.progress ?? 0}%` }} /></div>
              <p className="preventive-message">{run?.message}</p>
              <p className="preventive-worker-note">{detail?.solver_stats.search_workers ?? job.solver_config.workers ?? 8} CP-SAT workers</p>
              {run?.error && <div className="preventive-error"><AlertTriangle size={15} />{run.error}</div>}
              {scores && (
                <dl className="preventive-metrics">
                  <div><dt>Project objective</dt><dd>{formatValue(scores.project_objective_score)}</dd></div>
                  <div><dt>Project overrun</dt><dd>{formatValue(scores.total_project_overrun_days)} days</dd></div>
                  <div><dt>On-time maintenance</dt><dd>{formatValue(scores.on_time_maintenance_count)}</dd></div>
                  <div><dt>Deferred maintenance</dt><dd>{formatValue(scores.deferred_maintenance_count)}</dd></div>
                  <div><dt>Total deferral</dt><dd>{formatValue(scores.total_maintenance_deferral_days)} days</dd></div>
                  <div><dt>Maximum deferral</dt><dd>{formatValue(scores.maximum_maintenance_deferral_days)} days</dd></div>
                </dl>
              )}
              {detail?.validation.feasible && <div className="preventive-downloads">
                {detail.downloads.filter((name) => ["PROJECT_ACCESS_DETAIL.csv", "MAINTENANCE_SCHEDULE.csv", "VALIDATION.json"].includes(name)).map((name) =>
                  <a key={name} href={`${API_BASE}/api/ps1/jobs/${job.job_id}/scenarios/${scenario}/files/${name}`}><Download size={12} />{name}</a>)}
              </div>}
            </article>
          );
        })}
      </div>

      {tradeoff && <ScheduleDifferenceComparison tradeoff={tradeoff} />}

      {terminal && !bothValidated && <div className="preventive-terminal-error" role="alert"><AlertTriangle size={17} />
        D/E trade-off is unavailable because both scenarios did not finish with independently validated results.
      </div>}
      {tradeoffError && <div className="preventive-terminal-error" role="alert">{tradeoffError}</div>}

      {modalOpen && tradeoff && (
        <div className="tradeoff-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeModal(); }}>
          <section className="tradeoff-modal" role="dialog" aria-modal="true" aria-labelledby="tradeoff-title">
            <header><div><span className="eyebrow">Validated comparison</span><h2 id="tradeoff-title">{tradeoff.title}</h2></div>
              <button ref={closeButtonRef} className="icon-button" aria-label="Close trade-off" onClick={closeModal}><X size={19} /></button>
            </header>
            <div className="tradeoff-policy-copy"><p><strong>D</strong> fixes every maintenance occurrence at its planned window.</p>
              <p><strong>E</strong> protects the project objective first and may defer maintenance by up to seven days.</p></div>
            <div className="schedule-difference-counts compact" aria-label="Schedule change summary">
              <span><strong>{tradeoff.schedule_difference_summary.project_accesses_changed}</strong> project accesses differ</span>
              <span><strong>{tradeoff.schedule_difference_summary.maintenance_occurrences_changed}</strong> maintenance occurrences differ</span>
            </div>
            <div className="tradeoff-table-wrap"><table><thead><tr><th>Metric</th><th>D</th><th>E</th><th>Δ E−D</th></tr></thead>
              <tbody>{Object.entries(tradeoff.metrics).map(([name, values]) => <tr key={name}><th>{METRIC_LABELS[name] ?? name}</th>
                <td>{formatValue(values.D)}</td><td>{formatValue(values.E)}</td><td>{formatDelta(values.delta_E_minus_D)}</td></tr>)}</tbody></table></div>
            <div className="tradeoff-summaries"><div><h3>Project schedule impact</h3><p>{tradeoff.project_schedule_impact}</p></div>
              <div><h3>Preventive maintenance impact</h3><p>{tradeoff.preventive_maintenance_impact}</p></div></div>
            <p className="tradeoff-conclusion">{tradeoff.summary} The appropriate policy depends on the operational value assigned to fixed maintenance windows versus project delivery.</p>
            <footer><button className="primary-button" onClick={closeModal}>Close</button></footer>
          </section>
        </div>
      )}
    </section>
  );
}

function ScheduleDifferenceComparison({ tradeoff }: { tradeoff: PreventiveTradeoff }) {
  const projects = [...tradeoff.project_schedule_differences]
    .sort((left, right) => Number(!left.activity_id.startsWith("PMD")) - Number(!right.activity_id.startsWith("PMD"))
      || Math.abs(right.moved_days_E_minus_D) - Math.abs(left.moved_days_E_minus_D))
    .slice(0, 20);
  const maintenance = tradeoff.maintenance_schedule_differences.slice(0, 20);
  return (
    <section className="schedule-comparison" aria-labelledby="schedule-comparison-title">
      <header><div><span className="eyebrow">Validated row-by-row comparison</span><h2 id="schedule-comparison-title">What changed between D and E?</h2></div>
        <div className="schedule-difference-counts">
          <span><strong>{tradeoff.schedule_difference_summary.project_accesses_changed}</strong> project changes</span>
          <span><strong>{tradeoff.schedule_difference_summary.maintenance_occurrences_changed}</strong> maintenance changes</span>
        </div>
      </header>
      <div className="schedule-difference-legend"><span className="legend-d">D · maintenance fixed</span><span className="legend-e">E · project protected</span></div>
      <div className="schedule-difference-panels">
        <div className="schedule-difference-panel">
          <h3>Project access movements</h3>
          {projects.length ? <div className="schedule-difference-table-wrap"><table><thead><tr><th>Access</th><th>Scenario D</th><th aria-label="moves to" /><th>Scenario E</th><th>Shift</th></tr></thead>
            <tbody>{projects.map((row) => <tr key={`${row.activity_id}-${row.access_seq}`}><th>{row.activity_id}<small>Access {row.access_seq}</small></th>
              <td><ScheduleSlot kind="d" date={row.D.access_date} note={`Week ${row.D.week} · ${dayName(row.D.physical_day)}`} /></td>
              <td className="schedule-arrow">→</td>
              <td><ScheduleSlot kind="e" date={row.E.access_date} note={`Week ${row.E.week} · ${dayName(row.E.physical_day)}`} /></td>
              <td><ShiftBadge days={row.moved_days_E_minus_D} /></td></tr>)}</tbody></table></div>
            : <p className="empty-difference">No project access dates differ.</p>}
          {tradeoff.project_schedule_differences.length > projects.length && <p className="difference-overflow">Showing 20 of {tradeoff.project_schedule_differences.length} project changes.</p>}
        </div>
        <div className="schedule-difference-panel">
          <h3>Maintenance movements</h3>
          {maintenance.length ? <div className="schedule-difference-table-wrap"><table><thead><tr><th>Location / occurrence</th><th>Scenario D</th><th aria-label="moves to" /><th>Scenario E</th><th>Shift</th></tr></thead>
            <tbody>{maintenance.map((row) => <tr key={row.occurrence_id}><th title={row.location_id}>{row.location_id}<small>{row.occurrence_id}</small></th>
              <td><ScheduleSlot kind="d" date={row.D.actual_date} note={row.D.deferral_days ? `+${row.D.deferral_days}d` : "On time"} /></td>
              <td className="schedule-arrow">→</td>
              <td><ScheduleSlot kind="e" date={row.E.actual_date} note={row.E.deferral_days ? `+${row.E.deferral_days}d deferred` : "On time"} /></td>
              <td><ShiftBadge days={row.moved_days_E_minus_D} /></td></tr>)}</tbody></table></div>
            : <p className="empty-difference">No maintenance dates differ.</p>}
          {tradeoff.maintenance_schedule_differences.length > maintenance.length && <p className="difference-overflow">Showing 20 of {tradeoff.maintenance_schedule_differences.length} maintenance changes.</p>}
        </div>
      </div>
    </section>
  );
}

function ScheduleSlot({ kind, date, note }: { kind: "d" | "e"; date: string; note: string }) {
  return <span className={`schedule-slot slot-${kind}`}><strong>{formatDate(date)}</strong><small>{note}</small></span>;
}

function ShiftBadge({ days }: { days: number }) {
  return <span className={`shift-badge ${days < 0 ? "earlier" : days > 0 ? "later" : "same"}`}>
    {days === 0 ? "Same day" : `${days > 0 ? "+" : ""}${days}d`}
  </span>;
}

function dayName(day: number) {
  return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day - 1] ?? `Day ${day}`;
}

function formatDate(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatValue(value: number | string | null | undefined) {
  if (value == null) return "—";
  return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : value;
}

function formatDelta(value: number | null) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toLocaleString(undefined, { maximumFractionDigits: 3 })}`;
}
