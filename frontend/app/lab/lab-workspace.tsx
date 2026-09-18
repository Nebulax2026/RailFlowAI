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
type BatchRow = { method: Method; scenario: Scenario; case_id: string; status: string; score: number | null; elapsed_seconds: number | null; termination_reason: string | null; error: string | null };
type BatchSummary = { method: Method; scenario: Scenario; total: number; finished: number; valid: number; mean_score: number | null; worst_score: number | null };
type Batch = { id: string; status: string; method: Method | "all"; seconds: number; seed: number; cp_sat_workers?: number; rows: BatchRow[]; summary: BatchSummary[]; error: string | null };
const METHOD_LABELS: Record<Method, string> = { legacy: "Existing planner", integrated: "Integrated CP-SAT", alns: "CP-SAT + adaptive LNS", random_lns: "CP-SAT + random LNS" };

const JOB_STORAGE_KEY = "railflow-lab-job-id";

export default function LabWorkspace() {
  const [labTab, setLabTab] = useState<"single" | "suite">("single");
  const [method, setMethod] = useState<Method>("legacy");
  const [seconds, setSeconds] = useState(15);
  const [seed, setSeed] = useState(42);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [batchError, setBatchError] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchRestoring, setBatchRestoring] = useState(true);
  const [batchCancelling, setBatchCancelling] = useState(false);
  const batchPending = useRef(false);
  const [files, setFiles] = useState<Map<string, File>>(new Map());
  const [job, setJob] = useState<Job | null>(null);
  const [details, setDetails] = useState<Partial<Record<Scenario, ScenarioDetail>>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [intake, setIntake] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const requestPending = useRef(false);
  const [restoring, setRestoring] = useState(true);
  const batchActive = batch?.status === "queued" || batch?.status === "running";
  const active = batchActive || batchBusy || batchRestoring || restoring || busy || job?.status === "queued" || job?.status === "running";
  const jobId = job?.job_id;


  useEffect(() => {
    let disposed = false;
    async function restore() {
      try {
        const saved = window.localStorage.getItem(JOB_STORAGE_KEY);
        if (!saved) return;
        const restored = await api<Job>(`/api/ps1/jobs/${encodeURIComponent(saved)}`);
        if (!disposed) { setJob(restored); setIntake(false); }
      } catch (err) {
        if (disposed) return;
        if (err instanceof ApiError && [404, 410].includes(err.status)) {
          try { window.localStorage.removeItem(JOB_STORAGE_KEY); } catch {}
          setError("The previous job expired or is no longer available. Load a demand book to begin.");
        } else setError("Could not restore the previous job. Refresh to retry.");
      } finally { if (!disposed) setRestoring(false); }
    }
    void restore();
    return () => { disposed = true; };
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const loaded = new Map<string, string>();
    async function poll() {
      try {
        const next = await api<Job>(`/api/ps1/jobs/${jobId}`);
        if (disposed) return;
        for (const scenario of Object.keys(next.scenarios) as Scenario[]) {
          const run = next.scenarios[scenario]!;
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
      } catch (requestError) {
        if (disposed) return;
        if (requestError instanceof ApiError && [404, 410].includes(requestError.status)) {
          try { window.localStorage.removeItem(JOB_STORAGE_KEY); } catch {}
          setJob(null); setDetails({}); setIntake(true); setError("This job expired or is no longer available. Load a demand book to begin.");
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Could not refresh the solve job.");
      }
      if (!disposed) timer = setTimeout(poll, 1200);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [jobId]);
  const allFilesReady = REQUIRED_FILES.every((name) => files.has(name)) && files.size === REQUIRED_FILES.length;
  const canDownload = job && Object.values(job.scenarios).some((run) => run.feasible);

  function acceptFiles(list: FileList | File[]) {
    if (busy || active) return;
    const next = new Map<string, File>();
    Array.from(list).forEach((file) => { if (file.name.toLowerCase().endsWith(".csv")) next.set(file.name, file); });
    setFiles(next); setError("");
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); acceptFiles(event.dataTransfer.files); }

  async function start(publicDataset: boolean) {
    if (requestPending.current || batchPending.current || active || (!publicDataset && !allFilesReady)) return;
    requestPending.current = true;
    setBusy(true); setError("");
    try {
      const init: RequestInit = { method: "POST" };
      const params = new URLSearchParams({ algorithm: method === "legacy" ? "legacy" : "strategies", strategy: method === "legacy" ? "alns" : method, time_limit_seconds: String(seconds), seed: String(seed) });
      if (publicDataset) params.set("public", "true");
      else {
        const body = new FormData();
        REQUIRED_FILES.forEach((name) => body.append("files", files.get(name)!));
        init.body = body;
      }
      const created = await api<Job>(`/api/ps1/jobs?${params}`, init);
      setDetails({}); setJob(created); setIntake(false);
      try { window.localStorage.setItem(JOB_STORAGE_KEY, created.job_id); } catch { setError("Job started, but this browser could not save it for re-entry."); }
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

  useEffect(() => {
    let disposed = false;
    async function restoreBatch() {
      try {
        const saved = window.localStorage.getItem("railflow-benchmark-id");
        if (!saved) return;
        const restored = await api<Batch>(`/api/ps1/benchmark/runs/${encodeURIComponent(saved)}`);
        if (!disposed) { setBatch(restored); if (["queued", "running"].includes(restored.status)) setLabTab("suite"); }
      } catch (err) {
        if (disposed) return;
        if (err instanceof ApiError && [404, 410].includes(err.status)) {
          try { window.localStorage.removeItem("railflow-benchmark-id"); } catch {}
          setBatchError("The previous dataset run expired or is no longer available.");
        } else setBatchError("Could not restore the previous dataset run. Refresh to retry.");
      } finally { if (!disposed) setBatchRestoring(false); }
    }
    void restoreBatch();
    return () => { disposed = true; };
  }, []);
  useEffect(() => {
    if (!batch?.id || !batchActive) return;
    const id = batch.id;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Batch>(`/api/ps1/benchmark/runs/${id}`);
        if (disposed) return;
        setBatch(next);
        if (!["queued", "running"].includes(next.status)) return;
      } catch (err) {
        if (disposed) return;
        if (err instanceof ApiError && [404, 410].includes(err.status)) {
          try { window.localStorage.removeItem("railflow-benchmark-id"); } catch {}
          setBatch(null); setBatchError("This dataset run expired or is no longer available."); return;
        }
        setBatchError(err instanceof Error ? err.message : "Could not refresh dataset results.");
      }
      if (!disposed) timer = setTimeout(poll, 1500);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [batch?.id, batchActive]);
  async function startBatch(allMethods: boolean) {
    if (active || batchPending.current || requestPending.current) return;
    batchPending.current = true; setBatchBusy(true); setBatchError("");
    try {
      const params = new URLSearchParams({ method: allMethods ? "all" : method, time_limit_seconds: String(seconds), seed: String(seed) });
      const created = await api<Batch>(`/api/ps1/benchmark/runs?${params}`, { method: "POST" });
      setBatch(created);
      try { window.localStorage.setItem("railflow-benchmark-id", created.id); } catch { setBatchError("Comparison started, but this browser could not save it for re-entry."); }
    } catch (err) { setBatchError(err instanceof Error ? err.message : "Could not start dataset comparison."); }
    finally { setBatchBusy(false); batchPending.current = false; }
  }
  async function cancelBatch() {
    if (!batch || batchCancelling) return;
    setBatchCancelling(true);
    try { setBatch(await api<Batch>(`/api/ps1/benchmark/runs/${batch.id}`, { method: "DELETE" })); }
    catch (err) { setBatchError(err instanceof Error ? err.message : "Could not stop dataset comparison."); }
    finally { setBatchCancelling(false); }
  }

  return (
    <main className="app-shell lab-shell">
      <header className="app-header">
        <div className="brand-lockup"><span className="brand-mark"><Network size={22} /></span><div><strong>RailFlowAI</strong><span>Temporary test tools</span></div></div>
        {job && labTab === "single" ? <>
          <div className="dataset-summary"><strong>{job.source === "public" ? "Public dataset" : "Demand book"}</strong><span>{job.instance.activities} activities · {job.instance.total_accesses} accesses · {job.instance.horizon_weeks} weeks</span></div>
          <div className="header-actions">
            <span className={`job-pill ${job.status}`} title={`Expires ${new Date(job.expires_at).toLocaleString()}`}><Clock3 size={14} />{job.status}</span>
            <button className="secondary-button" disabled={active || busy} onClick={() => setIntake(!intake)}>{intake ? "Back to dashboard" : "Change data"}</button>
            {(job.status === "queued" || job.status === "running") && <button className="secondary-button" disabled={cancelling} onClick={() => void cancel()}><CircleStop size={15} />{cancelling ? "Cancelling…" : "Cancel"}</button>}
            <a className={`primary-button ${canDownload ? "" : "disabled"}`} aria-disabled={!canDownload} href={canDownload ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}><Download size={15} />Download ZIP</a>
          </div>
        </> : <span className="header-state">Lab · temporary</span>}
        <Link className="test-tools-link" href="/">Back to planner</Link>
      </header>
      <div className="lab-toolbar">
        <nav className="lab-tabs" aria-label="Test workspace">{(["single", "suite"] as const).map(value => <button key={value} className="secondary-button" aria-pressed={labTab === value} onClick={() => setLabTab(value)}>{value === "single" ? "Single input" : "Dataset suite"}</button>)}</nav>
                  <fieldset className="algorithm-picker" disabled={active}>
            <legend>Scheduling algorithm</legend>
            <div className="solver-options">
              <label>Search method<select value={method} onChange={(event) => setMethod(event.target.value as Method)}>{(Object.keys(METHOD_LABELS) as Method[]).map((value) => <option key={value} value={value}>{METHOD_LABELS[value]}</option>)}</select></label>
              <label>Time per scenario<select value={seconds} onChange={(event) => setSeconds(Number(event.target.value))}>{[15, 30, 60, 120].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
              <label>Seed<input type="number" min={0} max={2147483647} step={1} value={seed} onChange={(event) => setSeed(Math.max(0, Math.min(2147483647, Math.trunc(Number(event.target.value)))))} /></label>
            </div>
            <p className="solver-note">All methods use the server CP-SAT worker configuration. Existing planner runs A, B and C sequentially, with one uninterrupted search of up to 120 seconds each; other methods use the selected time per scenario. Dataset runs are serial; the current server configures eight CP-SAT workers per run. Every method uses the same closure policy and exported-CSV validation gate.</p>
          </fieldset>
      </div>
      {labTab === "single" && error && <div className="alert error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}

      {restoring && <p className="restore-notice" role="status">Restoring previous job…</p>}
      <section className="intake-screen" hidden={!intake || labTab !== "single"} aria-label="Demand book input">
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

      <section className="data-panel dataset-panel" hidden={labTab !== "suite"}>
        <div className="subheading"><h2>30 shared test datasets · average scores</h2><span>Every dataset runs A, B and C</span></div>
        <p>Synthetic datasets with an internally validated feasible example for each scenario. Average scores use completed, valid runs only; the success count is shown beside each average. Scores from different scenarios have different objectives. Every method uses the same closure policy and exported-CSV validation gate.</p>
        <div className="button-row"><button className="secondary-button" disabled={active} onClick={() => void startBatch(false)}><Play size={15} /> Run selected method · 90 runs</button><button className="secondary-button" disabled={active} onClick={() => void startBatch(true)}><Play size={15} /> Compare all 4 methods · 360 runs</button></div>
        <p className="muted">At {seconds}s per run: selected method up to {Math.ceil(90 * seconds / 60)} minutes; all methods up to {Math.ceil(360 * seconds / 60)} minutes, plus setup. Runs execute sequentially.{batch && ` Current run: ${batch.seconds}s per run, seed ${batch.seed}; CP-SAT workers: ${batch.cp_sat_workers ?? "not reported"}.`}</p>
        <div className="csv-links dataset-downloads"><a href={`${API_BASE}/api/ps1/benchmark/datasets/download`}><Download size={14} />Download all 30 shared datasets</a></div>
        {batchRestoring && <p role="status">Restoring previous dataset run…</p>}
        {batchError && <p className="inline-error" role="alert">{batchError}</p>}
        {batch && <>
          <div className="subheading"><h3>Dataset results · {batch.status}</h3><span>{batch.rows.filter(r => ["completed", "failed", "cancelled"].includes(r.status)).length}/{batch.rows.length} finished</span></div>
          {["queued", "running"].includes(batch.status) && <button className="secondary-button" disabled={batchCancelling} onClick={() => void cancelBatch()}><CircleStop size={15} /> Stop comparison</button>}
          {batch.error && <p className="alert error">{batch.error}</p>}
          <div className="batch-summary table-wrap"><table><thead><tr><th>Method</th><th>Scenario</th><th>Average score</th><th>Valid / finished / total</th><th>Worst valid score</th></tr></thead><tbody>{batch.summary.map(row => <tr key={`${row.method}-${row.scenario}`}><td>{METHOD_LABELS[row.method]}</td><td>{row.scenario}</td><td>{row.mean_score ?? "—"}</td><td>{row.valid} / {row.finished} / {row.total}</td><td>{row.worst_score ?? "—"}</td></tr>)}</tbody></table></div>
          <div className="batch-detail"><h3>Individual runs · {batch.rows.length}</h3><div className="table-wrap"><table><thead><tr><th>Method</th><th>Dataset</th><th>Scenario</th><th>State</th><th>Score</th><th>Seconds</th></tr></thead><tbody>{batch.rows.map(row => <tr key={`${row.method}-${row.case_id}-${row.scenario}`}><td>{METHOD_LABELS[row.method]}</td><td>{row.case_id}</td><td>{row.scenario}</td><td>{row.status}</td><td>{row.score ?? "—"}</td><td>{row.elapsed_seconds ?? "—"}</td></tr>)}</tbody></table></div></div>
          <a className="secondary-button" href={`${API_BASE}/api/ps1/benchmark/runs/${batch.id}/report`}><Download size={15} /> Download raw results</a>
        </>}
      </section>

      {job && <div className="results-host" hidden={intake || labTab !== "single"}><ScheduleResults key={job.job_id} job={job} details={details} /></div>}
    </main>
  );
}
