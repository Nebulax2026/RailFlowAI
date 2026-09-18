"use client";

import { Activity, AlertTriangle, Check, CircleStop, Clock3, Download, FileSpreadsheet, Gauge, LoaderCircle, Network, Play, ShieldCheck, UploadCloud, X } from "lucide-react";
import { type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { Inspection, type EvidenceActivity, type LocationUsage } from "./inspection";
import { BonusTools } from "./bonus-tools";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const REQUIRED_FILES = ["01_LINES.csv", "02_STATIONS.csv", "03_SECTORS.csv", "04_LOCATION_SUPPLY.csv", "05_BUFFER_LOCATION.csv", "06_PARAMETERS.csv", "07_PROJECT_DETAILS.csv", "08_ACTIVITY_DETAILS.csv"];
type Scenario = "A" | "B" | "C";
const POLICIES = { A: "Strict supply", B: "Strict schedule", C: "Balanced" };
const TABS = [{ id: "overview", label: "Overview" }, { id: "activities", label: "Activities" }, { id: "capacity", label: "Location & capacity" }, { id: "contracts", label: "Contract results" }] as const;
type DetailTab = typeof TABS[number]["id"];
type Status = "queued" | "running" | "completed" | "failed" | "cancelled";
type RunState = { status: Status; progress: number; message: string; error?: string | null; feasible?: boolean | null; objective_score?: number | null; phase: string; termination_reason?: string; solution_revision: number; solver_stats: { elapsed_seconds?: number; optimal?: boolean; relative_gap?: number }; scores?: Record<string, number> };
type Job = {
  job_id: string; status: Status; source: string; expires_at: string; error?: string | null;
  instance: { lines: number; stations: number; sectors: number; locations: number; contracts: number; activities: number; total_accesses: number; horizon_start: string; horizon_weeks: number };
  scenarios: Record<Scenario, RunState>;
};
type ScenarioDetail = {
  scenario: Scenario; status: string;
  solution_revision: number; phase: string; termination_reason?: string;
  solver_stats: { optimal?: boolean; relative_gap?: number; elapsed_seconds?: number };
  score_breakdown: { delay: number; excess_supply: number; eclo: number };
  activity_details: EvidenceActivity[];
  locations: { location_id: string; capacity: number }[];
  validation: {
    feasible: boolean; hard_violations: { rule: string; severity: string; detail: string }[];
    soft_scores: Record<string, number | string | Record<string, number>>;
    detail: { capacity_hotspots: LocationUsage[]; location_usage: LocationUsage[]; nights_scheduled: number; eclo_nights: number };
  };
  explanations: string[];
  results: { scenario: string; contract_number: string; simulated_completion_date: string; overrun_days: number }[];
  accesses: { activity_id: string; week: number; eclo: number; access_night: number }[];
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(Array.isArray(detail) ? detail.join(" ") : detail || `Request failed (${response.status}).`);
  }
  return payload as T;
}

export default function Workspace() {
  const [files, setFiles] = useState<Map<string, File>>(new Map());
  const [job, setJob] = useState<Job | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<Scenario>("A");
  const [details, setDetails] = useState<Partial<Record<Scenario, ScenarioDetail>>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [intake, setIntake] = useState(true);
  const [tab, setTab] = useState<DetailTab>("overview");
  const [cancelling, setCancelling] = useState(false);
  const requestPending = useRef(false);
  const active = job?.status === "running" || job?.status === "queued";

  useEffect(() => {
    const jobId = job?.job_id;
    if (!jobId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const loaded = new Map<string, string>();
    async function poll() {
      try {
        const next = await api<Job>(`/api/ps1/jobs/${jobId}`);
        if (disposed) return;
        for (const scenario of ["A", "B", "C"] as const) {
          const run = next.scenarios[scenario];
          const version = `${run.solution_revision}-${run.phase}-${run.termination_reason}`;
          if (run.feasible && loaded.get(scenario) !== version) {
            const detail = await api<ScenarioDetail>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}`);
            if (disposed) return;
            setDetails((current) => ({ ...current, [scenario]: detail }));
            loaded.set(scenario, version);
          }
        }
        setJob(next);
        if (!["queued", "running"].includes(next.status)) return;
      } catch (requestError) { if (!disposed) setError(requestError instanceof Error ? requestError.message : "Could not refresh the solve job."); }
      if (!disposed) timer = setTimeout(poll, 1200);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [job?.job_id]);

  const allFilesReady = REQUIRED_FILES.every((name) => files.has(name)) && files.size === REQUIRED_FILES.length;
  const selected = details[selectedScenario];
  const canDownload = job && Object.values(job.scenarios).some((run) => run.feasible);

  function acceptFiles(list: FileList | File[]) {
    if (busy || active) return;
    const next = new Map<string, File>();
    Array.from(list).forEach((file) => { if (file.name.toLowerCase().endsWith(".csv")) next.set(file.name, file); });
    setFiles(next); setError("");
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); acceptFiles(event.dataTransfer.files); }

  async function start(publicDataset: boolean) {
    if (requestPending.current || active || (!publicDataset && !allFilesReady)) return;
    requestPending.current = true;
    setBusy(true); setError("");
    try {
      const init: RequestInit = { method: "POST" };
      let path = "/api/ps1/jobs";
      if (publicDataset) path += "?public=true";
      else {
        const body = new FormData();
        REQUIRED_FILES.forEach((name) => body.append("files", files.get(name)!));
        init.body = body;
      }
      const next = await api<Job>(path, init);
      setJob(next); setDetails({}); setSelectedScenario("A"); setTab("overview"); setIntake(false);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The solve job could not be started."); }
    finally { setBusy(false); requestPending.current = false; }
  }
  async function cancel() {
    if (!job || cancelling) return;
    setCancelling(true);
    try { setJob(await api<Job>(`/api/ps1/jobs/${job.job_id}`, { method: "DELETE" })); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not cancel the job."); }
    finally { setCancelling(false); }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup"><span className="brand-mark"><Network size={22} /></span><div><strong>RailFlowAI</strong><span>Track access control room</span></div></div>
        {job ? <>
          <div className="dataset-summary"><strong>{job.source === "public" ? "Public dataset" : "Demand book"}</strong><span>{job.instance.activities} activities · {job.instance.total_accesses} accesses · {job.instance.horizon_weeks} weeks</span></div>
          <div className="header-actions">
            <span className={`job-pill ${job.status}`} title={`Expires ${new Date(job.expires_at).toLocaleString()}`}><Clock3 size={14} />{job.status}</span>
            <button className="secondary-button" disabled={active || busy} onClick={() => setIntake(!intake)}>{intake ? "Back to dashboard" : "Change data"}</button>
            {active && <button className="secondary-button" disabled={cancelling} onClick={() => void cancel()}><CircleStop size={15} />{cancelling ? "Cancelling…" : "Cancel"}</button>}
            <a className={`primary-button ${canDownload ? "" : "disabled"}`} aria-disabled={!canDownload} href={canDownload ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}><Download size={15} />Download ZIP</a>
          </div>
        </> : <span className="header-state">PS1 decision support</span>}
      </header>
      {error && <div className="alert error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}

      <section className="intake-screen" hidden={!intake} aria-label="Demand book input">
        <div className="tool-panel upload-panel">
          <div className="panel-heading"><h1>Demand book</h1><span>{REQUIRED_FILES.filter(name => files.has(name)).length}/8 files</span></div>
          <p className="muted">Select the eight CSV files to run all three policies, or use the public dataset.</p>
          <label className="drop-zone" onDragOver={event => event.preventDefault()} onDrop={handleDrop}>
            <UploadCloud size={26} /><strong>Select or drop eight CSV files</strong><span>Official filenames · UTF-8 · up to 2 MB each</span>
            <input aria-label="Select demand book CSV files" type="file" accept=".csv,text/csv" multiple disabled={busy || active} onChange={event => event.target.files && acceptFiles(event.target.files)} />
          </label>
          <div className="file-checklist">{REQUIRED_FILES.map(name => <div key={name} className={files.has(name) ? "ready" : "missing"}>{files.has(name) ? <Check size={15} /> : <FileSpreadsheet size={15} />}<span title={name}>{name}</span><small>{files.has(name) ? `${Math.ceil(files.get(name)!.size / 1024)} KB` : "required"}</small></div>)}</div>
          {[...files.keys()].some(name => !REQUIRED_FILES.includes(name)) && <p className="muted">Unexpected CSV filenames. Select only the eight required files.</p>}
          <div className="button-row"><button className="primary-button" disabled={!allFilesReady || busy || active} onClick={() => void start(false)}>{busy ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}Run demand book</button><button className="secondary-button" disabled={busy || active} onClick={() => void start(true)}><Activity size={17} />Load public dataset</button></div>
        </div>
      </section>

      {job && <section className="dashboard" hidden={intake} aria-label="Results dashboard">
        <section className="comparison-panel data-panel" aria-label="Policy comparison">
          <div className="subheading"><h2>Policy comparison</h2><span>Select a policy to inspect its results</span></div>
          <div className="table-wrap"><table><thead><tr><th>Policy</th><th>Work complete</th><th>Overrun days</th><th>Excess slots</th><th>ECLO nights</th><th>Score</th><th>Search state</th></tr></thead>
            <tbody>{(["A", "B", "C"] as const).map(scenario => {
              const run = job.scenarios[scenario];
              return <tr key={scenario} className={selectedScenario === scenario ? "selected-policy" : ""} onClick={() => setSelectedScenario(scenario)}>
                <th scope="row"><button className="policy-select" aria-pressed={selectedScenario === scenario} onClick={() => setSelectedScenario(scenario)}><span className="scenario-code">{scenario}</span>{POLICIES[scenario]}</button></th>
                <td>{run.scores ? `${run.scores.completion_percent}%` : "Pending"}</td><td>{run.scores?.overrun_days_total ?? "—"}</td><td>{run.scores?.excess_access_nights_total ?? "—"}</td><td>{run.scores?.eclo_nights_total ?? "—"}</td><td>{run.objective_score ?? "—"}</td>
                <td className="search-state"><span title={run.error || run.message}>{runLabel(run)}</span><progress aria-label={`Policy ${scenario} progress`} value={run.progress} max={100} /></td>
              </tr>;
            })}</tbody>
          </table></div>
        </section>
        <div className="scenario-detail" key={job.job_id}>
          <ScenarioView detail={selected} run={job.scenarios[selectedScenario]} scenario={selectedScenario} jobId={job.job_id} tab={tab} onTabChange={setTab} />
        </div>
      </section>}
    </main>
  );
}

function runLabel(run: RunState) {
  if (run.termination_reason === "optimal") return "Optimality proved";
  if (run.phase === "improving") return "Improving";
  if (run.phase === "first_search") return "Searching";
  if (run.feasible) return "Validated result available";
  if (run.termination_reason === "infeasible") return "Infeasible under documented policy";
  if (run.termination_reason === "time_limit") return "No solution within time limit";
  return run.status;
}

function EmptyResult({ run, scenario }: { run: RunState; scenario: string }) {
  return <div className="empty-result">{run.status === "running" ? <LoaderCircle size={34} className="spin" /> : <Gauge size={34} />}<h2>Policy {scenario}</h2><p>{run.error || run.message || runLabel(run)}</p></div>;
}

function ScenarioView({ detail, run, scenario, jobId, tab, onTabChange }: { detail?: ScenarioDetail; run: RunState; scenario: Scenario; jobId: string; tab: DetailTab; onTabChange: (tab: DetailTab) => void }) {
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
      <button ref={detailButton} className="secondary-button" disabled={!detail} onClick={() => dialog.current?.showModal()}>Result details</button>
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
        {detail && <BonusTools key={`${jobId}-${scenario}`} jobId={jobId} scenario={scenario} runStatus={run.status} usage={detail.validation.detail.location_usage} hotspots={hotspots} locations={detail.locations} />}
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
      <div className="dialog-content">{detail && <>
        <p>Revision {detail.solution_revision} · {detail.solver_stats.optimal ? "Optimality proved for the documented model" : "Best validated result; optimum not proved"}</p>
        <p>Cost: delay {detail.score_breakdown.delay}, excess supply {detail.score_breakdown.excess_supply}, ECLO {detail.score_breakdown.eclo}.</p>
        {detail.explanations.map(item => <p key={item}>{item}</p>)}
        {detail.validation.hard_violations.map((item, index) => <p key={index}><strong>{item.rule} ({item.severity})</strong>: {item.detail}</p>)}
        <p className="muted">First validated result target: 30 seconds per policy. Each policy may improve for up to 120 seconds total. The ZIP manifest records included revisions.</p>
      </>}</div>
    </dialog>
  </>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
