"use client";
import { useMemo, useRef, useState } from "react";
import { Download, Gauge, LoaderCircle, ShieldCheck, X } from "lucide-react";
import { Inspection } from "./inspection";
import { BonusTools } from "./bonus-tools";
import { API_BASE } from "./api-client";
import { POLICIES, TABS, type Scenario, type Job, type ScenarioDetail, type RunState, type Diagnostics, type DetailTab, type SolverConfig } from "./schedule-types";

export function ScheduleResults({ job, details }: { job: Job; details: Partial<Record<Scenario, ScenarioDetail>> }) {
  const [choice, setSelectedScenario] = useState<Scenario>("A");
  const selectedScenario = job.scenarios[choice] ? choice : (Object.keys(job.scenarios)[0] as Scenario ?? "A");
  const [tab, setTab] = useState<DetailTab>("overview");
  const selected = details[selectedScenario];
  if (!job.scenarios[selectedScenario]) return <div className="empty-result">No policies available for this job.</div>;
  return (      <section className="dashboard" aria-label="Results dashboard">
        <section className="comparison-panel data-panel" aria-label="Policy comparison">
          <div className="subheading"><h2>Policy comparison</h2><span>Select a policy to inspect its results</span></div>
          <div className="table-wrap"><table><thead><tr><th>Policy</th><th>Work complete</th><th>Overrun days</th><th>Excess slots</th><th>ECLO nights</th><th>Score</th><th>Search state</th></tr></thead>
            <tbody>{(Object.keys(job.scenarios) as Scenario[]).map(scenario => {
              const run = job.scenarios[scenario]!;
              return <tr key={scenario} className={selectedScenario === scenario ? "selected-policy" : ""} onClick={() => setSelectedScenario(scenario)}>
                <th scope="row"><button className="policy-select" aria-pressed={selectedScenario === scenario} onClick={() => setSelectedScenario(scenario)}><span className="scenario-code">{scenario}</span>{POLICIES[scenario]}</button></th>
                <td>{run.scores ? `${run.scores.completion_percent}%` : "Pending"}</td><td>{run.scores?.overrun_days_total ?? "—"}</td><td>{run.scores?.excess_access_nights_total ?? "—"}</td><td>{run.scores?.eclo_nights_total ?? "—"}</td><td>{run.objective_score ?? "—"}</td>
                <td className="search-state"><span title={run.error || run.message}>{runLabel(run)}</span><progress aria-label={`Policy ${scenario} progress`} value={run.progress} max={100} /></td>
              </tr>;
            })}</tbody>
          </table></div>
        </section>
        <div className="scenario-detail" key={job.job_id}>
          <ScenarioView detail={selected} run={job.scenarios[selectedScenario]!} scenario={selectedScenario} jobId={job.job_id} job={job} details={details} tab={tab} onTabChange={setTab} />
        </div>
      </section>);
}
function runLabel(run: RunState) {
  if (["optimal", "optimal_for_policy"].includes(run.termination_reason ?? "")) return "Optimality proved";
  if (run.phase === "improving") return "Improving";
  if (run.phase === "first_search") return "Searching";
  if (run.feasible) return "Validated result available";
  if (run.phase === "waiting_improvement") return "Waiting for extended search";
  if (run.termination_reason === "infeasible") return "Infeasible under documented policy";
  if (["time_limit", "no_solution_within_budget"].includes(run.termination_reason ?? "")) return "No solution within time limit";
  return run.status;
}

function SearchProgress({ scenario, diagnostics: d, requested }: { scenario: Scenario; diagnostics?: Diagnostics; requested?: SolverConfig }) {
  const format = (value?: number | null) => value == null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  const config = d?.config ?? requested;
  // Only diagnostic configuration is evidence of the resolved worker count.
  const workers = d?.config?.workers;
  return <section className="data-panel search-progress" aria-live="polite">
    <div className="subheading"><h3>Scenario {scenario} search</h3><span>{d?.status === "optimal_for_policy" ? "Optimal for configured policy" : d ? "Search diagnostics" : "No search diagnostics available"}</span></div>
    <dl className="execution-config">
      <div><dt>Search method</dt><dd>{d?.strategy ?? config?.strategy ?? "Not reported"}</dd></div>
      <div><dt>Solver workers</dt><dd>{typeof workers === "number" ? workers : workers === "auto" || requested?.workers === "auto" ? "Auto · resolved count not reported" : "Not reported"}</dd></div>
      <div><dt>Time budget</dt><dd>{config?.time_limit_seconds == null ? "Not reported" : `${config.time_limit_seconds}s`}</dd></div>
      <div><dt>Seed</dt><dd>{config?.seed ?? "Not reported"}</dd></div>
    </dl>
    <div className="metric-grid"><Metric label="Best cost" value={format(d?.objective)} /><Metric label="Model lower bound" value={format(d?.global_lower_bound)} /><Metric label="Absolute gap" value={format(d?.absolute_gap)} /><Metric label="First feasible (s)" value={format(d?.time_to_first_feasible)} /></div>
    <p className="muted">Bounds and validation apply to the documented safety policy. Official validator not supplied. A feasible result does not by itself prove optimality.</p>
    {!!d?.trajectory?.length && <details><summary>Cost improvements ({d.trajectory.length})</summary><div className="table-wrap"><table><thead><tr><th>Elapsed seconds</th><th>Validated cost</th></tr></thead><tbody>{d.trajectory.map((point, index) => <tr key={index}><td>{format(point.seconds)}</td><td>{format(point.objective)}</td></tr>)}</tbody></table></div></details>}
  </section>;
}

function EmptyResult({ run, scenario }: { run: RunState; scenario: string }) {
  return <div className="empty-result">{run.status === "running" ? <LoaderCircle size={34} className="spin" /> : <Gauge size={34} />}<h2>Policy {scenario}</h2><p>{run.error || run.message || runLabel(run)}</p></div>;
}

function ScenarioView({ detail, run, scenario, jobId, job, details, tab, onTabChange }: { job: Job; details: Partial<Record<Scenario, ScenarioDetail>>; detail?: ScenarioDetail; run: RunState; scenario: Scenario; jobId: string; tab: DetailTab; onTabChange: (tab: DetailTab) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const detailButton = useRef<HTMLButtonElement>(null);
  const scores = detail?.validation.soft_scores;
  const hotspots = detail?.validation.detail.capacity_hotspots ?? [];
  const maxUsed = Math.max(1, ...hotspots.map(item => item.used));
  const weeks = useMemo(() => {
    const count = new Map<number, number>();
    detail?.accesses.forEach(item => count.set(item.week, (count.get(item.week) || 0) + 1));
    return Array.from(count.entries()).sort((a, b) => a[0] - b[0]);
  }, [detail?.accesses]);
  const maxWeekAccess = Math.max(1, ...weeks.map(item => item[1]));

  return <>
    <div className="detail-header"><div><span className="eyebrow">Policy {scenario}</span><h2>{POLICIES[scenario]}</h2></div><div className="detail-actions">
      {detail && <span className={`validation-badge ${detail.validation.feasible ? "valid" : "invalid"}`}><ShieldCheck size={15} />{detail.validation.feasible ? "Internally validated" : "Hard violations"}</span>}
      <button ref={detailButton} className="secondary-button" disabled={!detail && !run.diagnostics} onClick={() => dialog.current?.showModal()}>Result details</button>
    </div></div>
    <div className="metric-grid"><Metric label="Objective score" value={String(scores?.objective_score ?? "—")} /><Metric label="Overrun days" value={String(scores?.overrun_days_total ?? "—")} /><Metric label="Excess access" value={String(scores?.excess_access_nights_total ?? "—")} /><Metric label="ECLO nights" value={String(scores?.eclo_nights_total ?? "—")} /></div>
    <div className="detail-tabs" role="tablist" aria-label="Policy details">{TABS.map((item, index) => <button key={item.id} id={`tab-${item.id}`} role="tab" aria-selected={tab === item.id} aria-controls={`panel-${item.id}`} tabIndex={tab === item.id ? 0 : -1} onClick={() => onTabChange(item.id)} onKeyDown={event => {
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % TABS.length;
      else if (event.key === "ArrowLeft") next = (index + TABS.length - 1) % TABS.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = TABS.length - 1;
      else return;
      event.preventDefault(); onTabChange(TABS[next].id);
      document.getElementById(`tab-${TABS[next].id}`)?.focus();
    }}>{item.label}</button>)}</div>
    {!detail && <div className="tab-content" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}><EmptyResult run={run} scenario={scenario} /></div>}
    <div className="tab-content" hidden={!detail}>
      <div className="tab-panel" role="tabpanel" id={detail ? "panel-overview" : undefined} aria-labelledby="tab-overview" tabIndex={0} hidden={tab !== "overview" || !detail}>
        <div className="visual-grid">
          <section className="data-panel"><div className="subheading"><h3>Weekly access load</h3><span>{detail?.accesses.length ?? 0} accesses</span></div><div className="week-chart">{weeks.map(([week, count]) => <div key={week} title={`Week ${week}: ${count} accesses`}><i style={{ height: `${Math.max(8, count / maxWeekAccess * 100)}%` }} /><small>{week}</small></div>)}{!weeks.length && <p className="muted">No scheduled accesses.</p>}</div></section>
          <section className="data-panel"><div className="subheading"><h3>Capacity hotspots</h3><span>{hotspots.length} at or above supply</span></div><div className="hotspot-list">{hotspots.map(item => <div key={`${item.location_id}-${item.week}`}><span><strong>{item.location_id}</strong><small>Week {item.week}</small></span><i><b style={{ width: `${item.used / maxUsed * 100}%` }} /></i><em>{item.used}/{item.capacity}</em></div>)}{!hotspots.length && <p className="muted">No locations reach nominal capacity.</p>}</div></section>
        </div>

      </div>
      <div className="tab-panel" role="tabpanel" id={detail ? "panel-operations" : undefined} aria-labelledby="tab-operations" hidden={tab !== "operations" || !detail} tabIndex={0}>
        {(Object.keys(details) as Scenario[]).map(policy => {
          const saved = details[policy]!;
          return <div className="operations-policy" hidden={policy !== scenario} key={policy}><BonusTools jobId={jobId} scenario={policy} runStatus={job.scenarios[policy]?.status ?? "queued"} usage={saved.validation.detail.location_usage ?? []} hotspots={saved.validation.detail.capacity_hotspots} locations={saved.locations ?? []} /></div>;
        })}
      </div>
      <Inspection activities={detail?.activity_details ?? []} usage={detail?.validation.detail.location_usage ?? []} view={detail ? tab : null} />
      <div className="tab-panel" role="tabpanel" id={detail ? "panel-contracts" : undefined} aria-labelledby="tab-contracts" tabIndex={0} hidden={tab !== "contracts" || !detail}>
        <section className="data-panel results-table-panel"><div className="subheading"><h3>Contract completion</h3><div className="csv-links">{["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"].map(file => <a key={file} title={`Download ${file}`} href={`${API_BASE}/api/ps1/jobs/${jobId}/scenarios/${scenario}/files/${file}?revision=${detail?.solution_revision}`}><Download size={14} />{file.replace("SCHEDULE_", "").replace(".csv", "")}</a>)}</div></div>
          <div className="table-wrap"><table><thead><tr><th>Contract</th><th>Completion</th><th>Overrun</th><th>State</th></tr></thead><tbody>{detail?.results.map(row => <tr key={row.contract_number}><td>{row.contract_number}</td><td>{row.simulated_completion_date}</td><td>{row.overrun_days} days</td><td><span className={`row-state ${row.overrun_days ? "late" : "on-time"}`}>{row.overrun_days ? "Overrun" : "On plan"}</span></td></tr>)}{!detail?.results.length && <tr><td colSpan={4}>No contract results.</td></tr>}</tbody></table></div>
        </section>
      </div>
    </div>
    <dialog ref={dialog} className="result-dialog" aria-labelledby="result-dialog-title" onClose={() => detailButton.current?.focus()}>
      <div className="subheading"><h2 id="result-dialog-title">Policy {scenario} result details</h2><button className="secondary-button" autoFocus onClick={() => dialog.current?.close()} aria-label="Close result details"><X size={17} /></button></div>
      <div className="dialog-content"><SearchProgress scenario={scenario} diagnostics={run.diagnostics ?? detail?.diagnostics} requested={job.solver_config} /><a className="secondary-button" href={`${API_BASE}/api/ps1/jobs/${jobId}/diagnostics`}>Download search diagnostics</a>{detail && <>
        <p>Revision {detail.solution_revision} · {detail.solver_stats.optimal ? "Optimality proved for the documented model" : "Best validated result; optimum not proved"}</p>
        <p>Cost: delay {detail.score_breakdown.delay}, excess supply {detail.score_breakdown.excess_supply}, ECLO {detail.score_breakdown.eclo}.</p>
        {detail.explanations.map(item => <p key={item}>{item}</p>)}
        {detail.validation.hard_violations.map((item, index) => <p key={index}><strong>{item.rule} ({item.severity})</strong>: {item.detail}</p>)}
        <p className="muted">{job.algorithm === "legacy" ? "Policies run sequentially: A, then B, then C, with up to 120 seconds each. Validated results appear during search; proven optimal results finish early." : `Search budget: ${job.solver_config?.time_limit_seconds ?? "configured"} seconds per policy.`} The ZIP manifest records included revisions.</p>
      </>}</div>
    </dialog>
  </>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
