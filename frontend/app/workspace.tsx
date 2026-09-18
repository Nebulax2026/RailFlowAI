"use client";

import { Activity, AlertTriangle, Check, CircleStop, Clock3, Download, FileSpreadsheet, Gauge, LoaderCircle, Network, Play, Radio, ShieldCheck, UploadCloud, X } from "lucide-react";
import { type DragEvent, useCallback, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const REQUIRED_FILES = ["01_LINES.csv", "02_STATIONS.csv", "03_SECTORS.csv", "04_LOCATION_SUPPLY.csv", "05_BUFFER_LOCATION.csv", "06_PARAMETERS.csv", "07_PROJECT_DETAILS.csv", "08_ACTIVITY_DETAILS.csv"];
type Scenario = "A" | "B" | "C";
type Status = "queued" | "running" | "completed" | "failed" | "cancelled";
type RunState = { status: Status; progress: number; message: string; error?: string | null; feasible?: boolean | null; objective_score?: number | null };
type Job = {
  job_id: string; status: Status; source: string; expires_at: string; error?: string | null;
  instance: { lines: number; stations: number; sectors: number; locations: number; contracts: number; activities: number; total_accesses: number; horizon_start: string; horizon_weeks: number };
  scenarios: Record<Scenario, RunState>;
};
type ScenarioDetail = {
  scenario: Scenario; status: string;
  validation: {
    feasible: boolean; hard_violations: { rule: string; severity: string; detail: string }[];
    soft_scores: Record<string, number | string | Record<string, number>>;
    detail: { capacity_hotspots: { location_id: string; week: number; used: number; capacity: number }[]; nights_scheduled: number; eclo_nights: number };
  };
  explanations: string[];
  results: { scenario: string; contract_number: string; simulated_completion_date: string; overrun_days: number }[];
  accesses: { activity_id: string; week: number; eclo: number; access_night: number }[];
};
type DataMall = { configured: boolean; available: boolean; cached?: boolean; fetched_at?: string; message?: string; alerts: { status?: number; line?: string; direction?: string; stations?: string; message?: string }[] };

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
  const [dataMall, setDataMall] = useState<DataMall | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadDataMall = useCallback(async () => {
    try { setDataMall(await api<DataMall>("/api/datamall/train-service-alerts")); }
    catch (requestError) { setDataMall({ configured: false, available: false, alerts: [], message: requestError instanceof Error ? requestError.message : "DataMall unavailable." }); }
  }, []);

  useEffect(() => { void loadDataMall(); }, [loadDataMall]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api<Job>(`/api/ps1/jobs/${job.job_id}`);
        setJob(next);
        for (const scenario of ["A", "B", "C"] as const) {
          if (next.scenarios[scenario].status === "completed" && !details[scenario]) {
            const detail = await api<ScenarioDetail>(`/api/ps1/jobs/${job.job_id}/scenarios/${scenario}`);
            setDetails((current) => ({ ...current, [scenario]: detail }));
          }
        }
      } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not refresh the solve job."); }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job, details]);

  const allFilesReady = REQUIRED_FILES.every((name) => files.has(name)) && files.size === REQUIRED_FILES.length;
  const selected = details[selectedScenario];
  const canDownload = job && Object.values(job.scenarios).some((run) => run.feasible);

  function acceptFiles(list: FileList | File[]) {
    const next = new Map<string, File>();
    Array.from(list).forEach((file) => { if (file.name.toLowerCase().endsWith(".csv")) next.set(file.name, file); });
    setFiles(next); setError(""); setJob(null); setDetails({});
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); acceptFiles(event.dataTransfer.files); }

  async function start(publicDataset: boolean) {
    setBusy(true); setError(""); setDetails({});
    try {
      const init: RequestInit = { method: "POST" };
      let path = "/api/ps1/jobs";
      if (publicDataset) path += "?public=true";
      else {
        const body = new FormData();
        REQUIRED_FILES.forEach((name) => body.append("files", files.get(name)!));
        init.body = body;
      }
      setJob(await api<Job>(path, init)); setSelectedScenario("A");
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The solve job could not be started."); }
    finally { setBusy(false); }
  }
  async function cancel() { if (job) setJob(await api<Job>(`/api/ps1/jobs/${job.job_id}`, { method: "DELETE" })); }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup"><span className="brand-mark"><Network size={22} /></span><div><strong>RailFlowAI</strong><span>Track access control room</span></div></div>
        <div className="header-state"><span className="live-dot" /> PS1 decision support</div>
      </header>
      <section className="workspace-title">
        <div><span className="eyebrow">Railway Track Access Optimisation</span><h1>Build a possession plan that proves itself.</h1><p>Load the eight-file demand book, solve all three operating policies, inspect the trade-offs, and export validator-ready schedules.</p></div>
        {job && <div className={`job-pill ${job.status}`}><Clock3 size={16} /> {job.status}<small>expires {new Date(job.expires_at).toLocaleTimeString()}</small></div>}
      </section>
      {error && <div className="alert error"><AlertTriangle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}

      <section className="intake-grid">
        <div className="tool-panel upload-panel">
          <div className="panel-heading"><div><span className="step">01</span><h2>Demand book</h2></div><span>{files.size}/8 files</span></div>
          <label className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={handleDrop}>
            <UploadCloud size={30} /><strong>Drop the PS1 folder or select eight CSV files</strong><span>Exact official filenames, UTF-8, up to 2 MB each</span>
            <input type="file" accept=".csv,text/csv" multiple onChange={(event) => event.target.files && acceptFiles(event.target.files)} />
          </label>
          <div className="file-checklist">{REQUIRED_FILES.map((name) => <div key={name} className={files.has(name) ? "ready" : "missing"}>{files.has(name) ? <Check size={15} /> : <FileSpreadsheet size={15} />}<span>{name}</span><small>{files.has(name) ? `${Math.ceil(files.get(name)!.size / 1024)} KB` : "required"}</small></div>)}</div>
          <div className="button-row"><button className="primary-button" disabled={!allFilesReady || busy || job?.status === "running"} onClick={() => void start(false)}><Play size={17} /> Run hidden instance</button><button className="secondary-button" disabled={busy || job?.status === "running"} onClick={() => void start(true)}><Activity size={17} /> Load public dataset</button></div>
        </div>
        <aside className="tool-panel context-panel">
          <div className="panel-heading"><div><Radio size={18} /><h2>Network context</h2></div><button className="icon-button" title="Refresh DataMall" onClick={() => void loadDataMall()}><Radio size={16} /></button></div>
          {!dataMall ? <p className="muted">Checking LTA DataMall...</p> : <><div className={`service-state ${dataMall.available ? "online" : "offline"}`}><span>{dataMall.available ? "Feed available" : "Context unavailable"}</span><strong>{dataMall.alerts.length ? `${dataMall.alerts.length} alert${dataMall.alerts.length === 1 ? "" : "s"}` : "No active alerts"}</strong></div>{dataMall.alerts.slice(0, 4).map((alert, index) => <div className="service-alert" key={`${alert.line}-${index}`}><strong>{alert.line || "Rail advisory"}</strong><span>{alert.stations || alert.message || "Service status update"}</span></div>)}{dataMall.message && <p className="muted">{dataMall.message}</p>}<p className="context-note">Live alerts are operational context only. They never modify the synthetic Alpha/Beta solver inputs.</p></>}
        </aside>
      </section>

      {job && <section className="results-workspace">
        <div className="scenario-rail">
          <div className="scenario-heading"><span className="step">02</span><div><h2>Policy runs</h2><p>{job.instance.activities} activities · {job.instance.total_accesses} accesses · {job.instance.horizon_weeks} weeks</p></div></div>
          {(["A", "B", "C"] as const).map((scenario) => { const run = job.scenarios[scenario]; return <button key={scenario} className={`scenario-card ${selectedScenario === scenario ? "selected" : ""}`} onClick={() => setSelectedScenario(scenario)}><span className="scenario-code">{scenario}</span><span className="scenario-copy"><strong>{scenario === "A" ? "Strict supply" : scenario === "B" ? "Strict schedule" : "Balanced"}</strong><small>{run.error || run.message}</small></span><span className={`run-icon ${run.status}`}>{run.status === "running" ? <LoaderCircle size={18} className="spin" /> : run.status === "completed" ? <Check size={18} /> : run.status === "failed" ? <AlertTriangle size={18} /> : <Clock3 size={18} />}</span><span className="progress-track"><i style={{ width: `${run.progress}%` }} /></span></button>; })}
          <div className="rail-actions">{job.status === "running" && <button className="secondary-button" onClick={() => void cancel()}><CircleStop size={17} /> Cancel</button>}<a className={`primary-button ${canDownload ? "" : "disabled"}`} href={canDownload ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}><Download size={17} /> Download result ZIP</a></div>
        </div>
        <div className="scenario-detail">{!selected ? <EmptyResult run={job.scenarios[selectedScenario]} scenario={selectedScenario} /> : <ScenarioView detail={selected} jobId={job.job_id} />}</div>
      </section>}
    </main>
  );
}

function EmptyResult({ run, scenario }: { run: RunState; scenario: string }) {
  return <div className="empty-result">{run.status === "running" ? <LoaderCircle size={34} className="spin" /> : <Gauge size={34} />}<h2>Scenario {scenario}</h2><p>{run.error || run.message}</p></div>;
}

function ScenarioView({ detail, jobId }: { detail: ScenarioDetail; jobId: string }) {
  const scores = detail.validation.soft_scores;
  const hotspots = detail.validation.detail.capacity_hotspots;
  const maxUsed = Math.max(1, ...hotspots.map((item) => item.used));
  const weeks = useMemo(() => { const count = new Map<number, number>(); detail.accesses.forEach((item) => count.set(item.week, (count.get(item.week) || 0) + 1)); return Array.from(count.entries()).sort((a, b) => a[0] - b[0]); }, [detail.accesses]);
  const maxWeekAccess = Math.max(1, ...weeks.map((item) => item[1]));
  return <>
    <div className="detail-header"><div><span className="eyebrow">Scenario {detail.scenario}</span><h2>{detail.scenario === "A" ? "Strict supply, flexible schedule" : detail.scenario === "B" ? "Strict schedule, flexible supply" : "Balanced trade-off"}</h2></div><span className={`validation-badge ${detail.validation.feasible ? "valid" : "invalid"}`}><ShieldCheck size={17} />{detail.validation.feasible ? "Internally validated" : "Hard violations"}</span></div>
    <div className="metric-grid"><Metric label="Objective score" value={String(scores.objective_score ?? "-")} /><Metric label="Overrun days" value={String(scores.overrun_days_total ?? 0)} /><Metric label="Excess access" value={String(scores.excess_access_nights_total ?? 0)} /><Metric label="ECLO nights" value={String(scores.eclo_nights_total ?? 0)} /></div>
    <div className="explanation-strip">{detail.explanations.map((item) => <p key={item}>{item}</p>)}</div>
    <div className="visual-grid">
      <section className="data-panel"><div className="subheading"><h3>Weekly access load</h3><span>{detail.accesses.length} rows</span></div><div className="week-chart">{weeks.map(([week, count]) => <div key={week} title={`Week ${week}: ${count} accesses`}><i style={{ height: `${Math.max(8, count / maxWeekAccess * 100)}%` }} /><small>{week}</small></div>)}</div></section>
      <section className="data-panel"><div className="subheading"><h3>Capacity hotspots</h3><span>{hotspots.length} at or above supply</span></div><div className="hotspot-list">{hotspots.slice(0, 8).map((item) => <div key={`${item.location_id}-${item.week}`}><span><strong>{item.location_id}</strong><small>Week {item.week}</small></span><i><b style={{ width: `${item.used / maxUsed * 100}%` }} /></i><em>{item.used}/{item.capacity}</em></div>)}{!hotspots.length && <p className="muted">No locations reach nominal capacity.</p>}</div></section>
    </div>
    <section className="data-panel results-table-panel"><div className="subheading"><h3>Contract completion</h3><div className="csv-links">{["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"].map((file) => <a key={file} title={`Download ${file}`} href={`${API_BASE}/api/ps1/jobs/${jobId}/scenarios/${detail.scenario}/files/${file}`}><Download size={14} />{file.replace("SCHEDULE_", "").replace(".csv", "")}</a>)}</div></div><div className="table-wrap"><table><thead><tr><th>Contract</th><th>Completion</th><th>Overrun</th><th>State</th></tr></thead><tbody>{detail.results.map((row) => <tr key={row.contract_number}><td>{row.contract_number}</td><td>{row.simulated_completion_date}</td><td>{row.overrun_days} days</td><td><span className={`row-state ${row.overrun_days ? "late" : "on-time"}`}>{row.overrun_days ? "Overrun" : "On plan"}</span></td></tr>)}</tbody></table></div></section>
  </>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
