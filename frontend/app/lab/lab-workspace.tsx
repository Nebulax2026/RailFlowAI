"use client";

import { Activity, AlertTriangle, Check, CircleStop, Clock3, Download, FileSpreadsheet, LoaderCircle, Network, Play, UploadCloud, X } from "lucide-react";
import { type DragEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ScheduleResults } from "../schedule-results";
import { api, ApiError } from "../api-client";
import type { Job, Scenario, ScenarioDetail } from "../schedule-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const REQUIRED_FILES = ["01_LINES.csv", "02_STATIONS.csv", "03_SECTORS.csv", "04_LOCATION_SUPPLY.csv", "05_BUFFER_LOCATION.csv", "06_PARAMETERS.csv", "07_PROJECT_DETAILS.csv", "08_ACTIVITY_DETAILS.csv"];
type Method = "legacy" | "integrated" | "alns" | "random_lns";
const METHOD_LABELS: Record<Method, string> = { legacy: "Existing planner", integrated: "Integrated CP-SAT", alns: "CP-SAT + adaptive LNS", random_lns: "CP-SAT + random LNS" };
const JOB_STORAGE_KEY = "railflow-lab-job-id";

export default function LabWorkspace() {
  const [method, setMethod] = useState<Method>("legacy");
  const [seconds, setSeconds] = useState(15);
  const [seed, setSeed] = useState(42);
  const [files, setFiles] = useState<Map<string, File>>(new Map());
  const [job, setJob] = useState<Job | null>(null);
  const [details, setDetails] = useState<Partial<Record<Scenario, ScenarioDetail>>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [intake, setIntake] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const requestPending = useRef(false);
  const jobId = job?.job_id;
  const active = restoring || busy || job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    let disposed = false;
    async function restore() {
      try {
        const saved = window.localStorage.getItem(JOB_STORAGE_KEY);
        if (!saved) return;
        const restored = await api<Job>(`/api/ps1/jobs/${encodeURIComponent(saved)}`);
        if (!disposed) { setJob(restored); setIntake(false); }
      } catch (err) {
        if (!disposed && err instanceof ApiError && [404, 410].includes(err.status)) window.localStorage.removeItem(JOB_STORAGE_KEY);
      } finally { if (!disposed) setRestoring(false); }
    }
    void restore(); return () => { disposed = true; };
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let disposed = false; let timer: ReturnType<typeof setTimeout>; const loaded = new Map<string, string>();
    async function poll() {
      try {
        const next = await api<Job>(`/api/ps1/jobs/${jobId}`);
        if (disposed) return;
        for (const scenario of Object.keys(next.scenarios) as Scenario[]) {
          const run = next.scenarios[scenario]!; const version = `${run.solution_revision}-${run.phase}-${run.termination_reason}`;
          if (run.feasible && loaded.get(scenario) !== version) {
            const detail = await api<ScenarioDetail>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}`);
            if (disposed) return;
            setDetails(current => ({ ...current, [scenario]: detail })); loaded.set(scenario, version);
          }
        }
        setJob(next);
        if (!["queued", "running"].includes(next.status)) return;
      } catch (err) { if (!disposed) setError(err instanceof Error ? err.message : "Could not refresh the solve job."); }
      if (!disposed) timer = setTimeout(poll, 1200);
    }
    void poll(); return () => { disposed = true; clearTimeout(timer); };
  }, [jobId]);

  const allFilesReady = REQUIRED_FILES.every(name => files.has(name)) && files.size === REQUIRED_FILES.length;
  const canDownload = job && Object.values(job.scenarios).some(run => run.feasible);
  function acceptFiles(list: FileList | File[]) {
    if (active) return;
    const next = new Map<string, File>();
    Array.from(list).forEach(file => { if (file.name.toLowerCase().endsWith(".csv")) next.set(file.name, file); });
    setFiles(next); setError("");
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); acceptFiles(event.dataTransfer.files); }
  async function start(publicDataset: boolean) {
    if (requestPending.current || active || (!publicDataset && !allFilesReady)) return;
    requestPending.current = true; setBusy(true); setError("");
    try {
      const init: RequestInit = { method: "POST" };
      const params = new URLSearchParams({ algorithm: method === "legacy" ? "legacy" : "strategies", strategy: method === "legacy" ? "integrated" : method, time_limit_seconds: String(seconds), seed: String(seed) });
      if (publicDataset) params.set("public", "true");
      else { const body = new FormData(); REQUIRED_FILES.forEach(name => body.append("files", files.get(name)!)); init.body = body; }
      const created = await api<Job>(`/api/ps1/jobs?${params}`, init);
      setDetails({}); setJob(created); setIntake(false); window.localStorage.setItem(JOB_STORAGE_KEY, created.job_id);
    } catch (err) { setError(err instanceof Error ? err.message : "The solve job could not be started."); }
    finally { setBusy(false); requestPending.current = false; }
  }
  async function cancel() {
    if (!job || cancelling) return;
    setCancelling(true);
    try { setJob(await api<Job>(`/api/ps1/jobs/${job.job_id}`, { method: "DELETE" })); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not cancel the job."); }
    finally { setCancelling(false); }
  }

  return <main className="app-shell lab-shell">
    <header className="app-header">
      <div className="brand-lockup"><span className="brand-mark"><Network size={22} /></span><div><strong>RailFlowAI</strong><span>Algorithm comparison</span></div></div>
      {job ? <><div className="dataset-summary"><strong>{job.source === "public" ? "Public dataset" : "Demand book"}</strong><span>{job.instance.activities} activities · {job.instance.total_accesses} accesses · {job.instance.horizon_weeks} weeks</span></div><div className="header-actions"><span className={`job-pill ${job.status}`}><Clock3 size={14} />{job.status}</span><button className="secondary-button" disabled={active} onClick={() => setIntake(!intake)}>{intake ? "Back to dashboard" : "Change data"}</button>{["queued", "running"].includes(job.status) && <button className="secondary-button" disabled={cancelling} onClick={() => void cancel()}><CircleStop size={15} />Cancel</button>}<a className={`primary-button ${canDownload ? "" : "disabled"}`} aria-disabled={!canDownload} href={canDownload ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}><Download size={15} />Download ZIP</a></div></> : <span className="header-state">Actual input only</span>}
      <Link className="test-tools-link" href="/">Back to planner</Link>
    </header>
    <div className="lab-toolbar"><fieldset className="algorithm-picker" disabled={active}><legend>Scheduling algorithm</legend><div className="solver-options"><label>Search method<select value={method} onChange={event => setMethod(event.target.value as Method)}>{(Object.keys(METHOD_LABELS) as Method[]).map(value => <option key={value} value={value}>{METHOD_LABELS[value]}</option>)}</select></label><label>Time per scenario<select value={seconds} onChange={event => setSeconds(Number(event.target.value))}>{[15, 30, 60, 120].map(value => <option key={value} value={value}>{value} seconds</option>)}</select></label><label>Seed<input type="number" min={0} max={2147483647} step={1} value={seed} onChange={event => setSeed(Math.max(0, Math.min(2147483647, Math.trunc(Number(event.target.value)))))} /></label></div><p className="solver-note">Run each method on the same input, seed, and time limit to compare its validated score and total search time. Existing planner uses its 120-second policy budget.</p></fieldset></div>
    {error && <div className="alert error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}
    {restoring && <p className="restore-notice" role="status">Restoring previous job…</p>}
    <section className="intake-screen" hidden={!intake} aria-label="Demand book input"><div className="tool-panel upload-panel"><div className="panel-heading"><h1>Demand book</h1><span>{REQUIRED_FILES.filter(name => files.has(name)).length}/8 files</span></div><p className="muted">Select the eight CSV files to run all three policies, or use the public dataset.</p><label className="drop-zone" onDragOver={event => event.preventDefault()} onDrop={handleDrop}><UploadCloud size={26} /><strong>Select or drop eight CSV files</strong><span>Official filenames · UTF-8 · up to 2 MB each</span><input aria-label="Select demand book CSV files" type="file" accept=".csv,text/csv" multiple disabled={active} onChange={event => event.target.files && acceptFiles(event.target.files)} /></label><div className="file-checklist">{REQUIRED_FILES.map(name => <div key={name} className={files.has(name) ? "ready" : "missing"}>{files.has(name) ? <Check size={15} /> : <FileSpreadsheet size={15} />}<span title={name}>{name}</span><small>{files.has(name) ? `${Math.ceil(files.get(name)!.size / 1024)} KB` : "required"}</small></div>)}</div><div className="button-row"><button className="primary-button" disabled={!allFilesReady || active} onClick={() => void start(false)}>{busy ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}Run demand book</button><button className="secondary-button" disabled={active} onClick={() => void start(true)}><Activity size={17} />Load public dataset</button></div></div></section>
    {job && <div className="results-host" hidden={intake}><ScheduleResults key={job.job_id} job={job} details={details} /></div>}
  </main>;
}
