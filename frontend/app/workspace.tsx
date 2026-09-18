"use client";

import { Activity, AlertTriangle, Check, CircleStop, Clock3, Download, FileSpreadsheet, Gauge, LoaderCircle, Network, Play, Radio, ShieldCheck, UploadCloud, X } from "lucide-react";
import { type DragEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Inspection, type EvidenceActivity, type LocationUsage } from "./inspection";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const REQUIRED_FILES = ["01_LINES.csv", "02_STATIONS.csv", "03_SECTORS.csv", "04_LOCATION_SUPPLY.csv", "05_BUFFER_LOCATION.csv", "06_PARAMETERS.csv", "07_PROJECT_DETAILS.csv", "08_ACTIVITY_DETAILS.csv"];
type Scenario = "A" | "B" | "C";
type Status = "queued" | "running" | "completed" | "failed" | "cancelled";
type Diagnostics = { status?: string; strategy?: string; objective?: number; global_lower_bound?: number; absolute_gap?: number; time_to_first_feasible?: number; elapsed_seconds?: number; trajectory?: { seconds: number; objective: number }[] };
type RunState = { status: Status; progress: number; message: string; error?: string | null; feasible?: boolean | null; objective_score?: number | null; diagnostics?: Diagnostics; phase: string; termination_reason?: string; solution_revision: number; solver_stats: { elapsed_seconds?: number; optimal?: boolean; relative_gap?: number }; scores?: Record<string, number> };
type Job = {
  job_id: string; status: Status; source: string; expires_at: string; error?: string | null;
  algorithm: "legacy" | "scenario_a" | "strategies";
  solver_config: { strategy?: string; time_limit_seconds?: number };
  instance: { lines: number; stations: number; sectors: number; locations: number; contracts: number; activities: number; total_accesses: number; horizon_start: string; horizon_weeks: number };
  scenarios: Partial<Record<Scenario, RunState>>;
};
type ScenarioDetail = {
  scenario: Scenario; status: string;
  solution_revision: number; phase: string; termination_reason?: string;
  solver_stats: { optimal?: boolean; relative_gap?: number; elapsed_seconds?: number };
  score_breakdown: { delay: number; excess_supply: number; eclo: number };
  activity_details: EvidenceActivity[];
  validation: {
    feasible: boolean; hard_violations: { rule: string; severity: string; detail: string }[];
    soft_scores: Record<string, number | string | Record<string, number>>;
    detail: { capacity_hotspots: LocationUsage[]; location_usage?: LocationUsage[]; nights_scheduled: number; eclo_nights: number };
  };
  explanations: string[];
  results: { scenario: string; contract_number: string; simulated_completion_date: string; overrun_days: number }[];
  accesses: { activity_id: string; week: number; eclo: number; access_night: number }[];
  diagnostics?: Diagnostics;
};
type DataMall = { configured: boolean; available: boolean; cached?: boolean; fetched_at?: string; message?: string; alerts: { status?: number; line?: string; direction?: string; stations?: string; message?: string }[] };
type Method = "legacy" | "integrated" | "alns" | "random_lns" | "greedy";
type BatchRow = { method: Method; scenario: Scenario; case_id: string; status: string; score: number | null; elapsed_seconds: number | null; termination_reason: string | null; error: string | null };
type BatchSummary = { method: Method; scenario: Scenario; total: number; finished: number; valid: number; mean_score: number | null; worst_score: number | null };
type Batch = { id: string; status: string; method: Method | "all"; seconds: number; seed: number; rows: BatchRow[]; summary: BatchSummary[]; error: string | null };
const METHOD_LABELS: Record<Method, string> = { legacy: "Existing planner", integrated: "Integrated CP-SAT", alns: "CP-SAT + adaptive LNS", random_lns: "CP-SAT + random LNS", greedy: "Greedy baseline" };

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
  const [batch, setBatch] = useState<Batch | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<Scenario>("A");
  const [details, setDetails] = useState<Partial<Record<Scenario, ScenarioDetail>>>({});
  const [dataMall, setDataMall] = useState<DataMall | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState<Method>("legacy");
  const [seconds, setSeconds] = useState(15);
  const [seed, setSeed] = useState(42);
  const active = busy || job?.status === "queued" || job?.status === "running" || batch?.status === "queued" || batch?.status === "running";
  const jobId = job?.job_id;

  const loadDataMall = useCallback(async () => {
    try { setDataMall(await api<DataMall>("/api/datamall/train-service-alerts")); }
    catch (requestError) { setDataMall({ configured: false, available: false, alerts: [], message: requestError instanceof Error ? requestError.message : "DataMall unavailable." }); }
  }, []);

  useEffect(() => { void loadDataMall(); }, [loadDataMall]);
  useEffect(() => {
    const saved = window.localStorage.getItem("railflow-benchmark-id");
    if (saved) void api<Batch>(`/api/ps1/benchmark/runs/${saved}`)
      .then((restored) => { if (window.localStorage.getItem("railflow-benchmark-id") === saved) setBatch(restored); })
      .catch(() => { if (window.localStorage.getItem("railflow-benchmark-id") === saved) window.localStorage.removeItem("railflow-benchmark-id"); });
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
      } catch (requestError) { if (!disposed) setError(requestError instanceof Error ? requestError.message : "Could not refresh the solve job."); }
      if (!disposed) timer = setTimeout(poll, 1200);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [jobId]);
  useEffect(() => {
    if (!batch?.id || !["queued", "running"].includes(batch.status)) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Batch>(`/api/ps1/benchmark/runs/${batch!.id}`);
        if (disposed) return;
        setBatch(next);
        if (["queued", "running"].includes(next.status)) timer = setTimeout(poll, 1500);
      } catch (requestError) { if (!disposed) setError(requestError instanceof Error ? requestError.message : "Could not refresh dataset scores."); }
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [batch?.id, batch?.status]);

  const allFilesReady = REQUIRED_FILES.every((name) => files.has(name)) && files.size === REQUIRED_FILES.length;
  const selected = details[selectedScenario];
  const canDownload = job && Object.values(job.scenarios).some((run) => run.feasible);

  function acceptFiles(list: FileList | File[]) {
    if (active) return;
    const next = new Map<string, File>();
    Array.from(list).forEach((file) => { if (file.name.toLowerCase().endsWith(".csv")) next.set(file.name, file); });
    setFiles(next); setError(""); setJob(null); setDetails({});
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); acceptFiles(event.dataTransfer.files); }

  async function start(publicDataset: boolean) {
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
      setDetails({}); setJob(created); setSelectedScenario("A");
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The solve job could not be started."); }
    finally { setBusy(false); }
  }
  async function startBatch(allMethods: boolean) {
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ method: allMethods ? "all" : method, time_limit_seconds: String(seconds), seed: String(seed) });
      const created = await api<Batch>(`/api/ps1/benchmark/runs?${params}`, { method: "POST" });
      window.localStorage.setItem("railflow-benchmark-id", created.id);
      setBatch(created);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not start dataset comparison."); }
    finally { setBusy(false); }
  }
  async function cancelBatch() {
    if (!batch) return;
    try { setBatch(await api<Batch>(`/api/ps1/benchmark/runs/${batch.id}`, { method: "DELETE" })); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not stop dataset comparison."); }
  }
  async function cancel() {
    if (!job) return;
    try { setJob(await api<Job>(`/api/ps1/jobs/${job.job_id}`, { method: "DELETE" })); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not stop the run."); }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup"><span className="brand-mark"><Network size={22} /></span><div><strong>RailFlowAI</strong><span>Track access control room</span></div></div>
        <div className="header-state"><span className="live-dot" /> PS1 decision support</div>
      </header>
      <section className="workspace-title">
        <div><span className="eyebrow">Railway Track Access Optimisation</span><h1>Build a possession plan that proves itself.</h1><p>Choose an algorithm, load the demand book, and compare validated schedules.</p></div>
        {job && <div className={`job-pill ${job.status}`}><Clock3 size={16} /> {job.status}<small>expires {new Date(job.expires_at).toLocaleTimeString()}</small></div>}
      </section>
      {error && <div className="alert error"><AlertTriangle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}

      <section className="intake-grid">
        <div className="tool-panel upload-panel">
          <fieldset className="algorithm-picker" disabled={active}>
            <legend>Scheduling algorithm</legend>
            <div className="solver-options">
              <label>Search method<select value={method} onChange={(event) => setMethod(event.target.value as Method)}>{(Object.keys(METHOD_LABELS) as Method[]).map((value) => <option key={value} value={value}>{METHOD_LABELS[value]}</option>)}</select></label>
              <label>Time per scenario<select value={seconds} onChange={(event) => setSeconds(Number(event.target.value))}>{[15, 30, 60, 120].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
              <label>Seed<input type="number" min={0} max={2147483647} step={1} value={seed} onChange={(event) => setSeed(Math.max(0, Math.min(2147483647, Math.trunc(Number(event.target.value)))))} /></label>
            </div>
            <p className="solver-note">Each method runs A, B and C. Existing planner uses its 30-second first pass and 90-second improvement pass for a single input. Dataset comparisons use the selected time per case and one worker for every method. Internal safety policies differ for A; official validator parity is unconfirmed.</p>
          </fieldset>
          <div className="panel-heading"><div><span className="step">01</span><h2>Demand book</h2></div><span>{files.size}/8 files</span></div>
          <label className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={handleDrop}>
            <UploadCloud size={30} /><strong>Drop the PS1 folder or select eight CSV files</strong><span>Exact official filenames, UTF-8, up to 2 MB each</span>
            <input type="file" accept=".csv,text/csv" multiple disabled={active} onChange={(event) => event.target.files && acceptFiles(event.target.files)} />
          </label>
          <div className="file-checklist">{REQUIRED_FILES.map((name) => <div key={name} className={files.has(name) ? "ready" : "missing"}>{files.has(name) ? <Check size={15} /> : <FileSpreadsheet size={15} />}<span>{name}</span><small>{files.has(name) ? `${Math.ceil(files.get(name)!.size / 1024)} KB` : "required"}</small></div>)}</div>
          <div className="button-row"><button className="primary-button" disabled={!allFilesReady || active} onClick={() => void start(false)}><Play size={17} />Run A, B and C</button><button className="secondary-button" disabled={active} onClick={() => void start(true)}>{busy ? <LoaderCircle size={17} className="spin" /> : <Activity size={17} />} Load public dataset</button></div>
        </div>
        <aside className="tool-panel context-panel">
          <div className="panel-heading"><div><Radio size={18} /><h2>Network context</h2></div><button className="icon-button" title="Refresh DataMall" onClick={() => void loadDataMall()}><Radio size={16} /></button></div>
          {!dataMall ? <p className="muted">Checking LTA DataMall...</p> : <><div className={`service-state ${dataMall.available ? "online" : "offline"}`}><span>{dataMall.available ? "Feed available" : "Context unavailable"}</span><strong>{dataMall.alerts.length ? `${dataMall.alerts.length} alert${dataMall.alerts.length === 1 ? "" : "s"}` : "No active alerts"}</strong></div>{dataMall.alerts.slice(0, 4).map((alert, index) => <div className="service-alert" key={`${alert.line}-${index}`}><strong>{alert.line || "Rail advisory"}</strong><span>{alert.stations || alert.message || "Service status update"}</span></div>)}{dataMall.message && <p className="muted">{dataMall.message}</p>}<p className="context-note">Live alerts are operational context only. They never modify the synthetic Alpha/Beta solver inputs.</p></>}
        </aside>
      </section>

      <section className="data-panel comparison-panel dataset-panel">
        <div className="subheading"><h2>30 shared test datasets · average scores</h2><span>Every dataset runs A, B and C</span></div>
        <p>Synthetic datasets with a validated feasible example for each scenario. Average scores use completed, valid runs only; the success count is shown beside each average. Scores from different scenarios have different objectives. The two Scenario A safety policies also differ.</p>
        <div className="button-row"><button className="secondary-button" disabled={active} onClick={() => void startBatch(false)}><Play size={15} /> Run selected method · 90 runs</button><button className="secondary-button" disabled={active} onClick={() => void startBatch(true)}><Play size={15} /> Compare all 5 methods · 450 runs</button></div>
        <p className="muted">At {seconds}s per run, maximum search time is about {Math.ceil((batch?.method === "all" ? 450 : 90) * seconds / 60)} minutes for this run, plus setup. Runs use one worker at a time.</p>
        <div className="csv-links dataset-downloads"><a href={`${API_BASE}/api/ps1/benchmark/datasets/download`}><Download size={14} /> Download all 30 shared datasets</a></div>
        {batch && <>
          <div className="subheading"><h3>Dataset results · {batch.status}</h3><span>{batch.rows.filter(r => ["completed", "failed", "cancelled"].includes(r.status)).length}/{batch.rows.length} finished</span></div>
          {["queued", "running"].includes(batch.status) && <button className="secondary-button" onClick={() => void cancelBatch()}><CircleStop size={15} /> Stop comparison</button>}
          {batch.error && <p className="alert error">{batch.error}</p>}
          <div className="table-wrap"><table><thead><tr><th>Method</th><th>Scenario</th><th>Average score</th><th>Valid / finished / total</th><th>Worst valid score</th></tr></thead><tbody>{batch.summary.map(row => <tr key={`${row.method}-${row.scenario}`}><td>{METHOD_LABELS[row.method]}</td><td>{row.scenario}</td><td>{row.mean_score ?? "—"}</td><td>{row.valid} / {row.finished} / {row.total}</td><td>{row.worst_score ?? "—"}</td></tr>)}</tbody></table></div>
          <details><summary>See all {batch.rows.length} dataset runs</summary><div className="table-wrap"><table><thead><tr><th>Method</th><th>Dataset</th><th>Scenario</th><th>State</th><th>Score</th><th>Seconds</th></tr></thead><tbody>{batch.rows.map(row => <tr key={`${row.method}-${row.case_id}-${row.scenario}`}><td>{METHOD_LABELS[row.method]}</td><td>{row.case_id}</td><td>{row.scenario}</td><td>{row.status}</td><td>{row.score ?? "—"}</td><td>{row.elapsed_seconds ?? "—"}</td></tr>)}</tbody></table></div></details>
          <a className="secondary-button" href={`${API_BASE}/api/ps1/benchmark/runs/${batch.id}/report`}><Download size={15} /> Download raw results</a>
        </>}
      </section>

      {job && <div className="comparison-panel data-panel"><h2>Scenario scores</h2><p>{job.algorithm === "legacy" ? "First validated result target: 30 seconds per policy. Each policy may improve for up to 120 seconds total." : `${job.solver_config.strategy}: up to ${job.solver_config.time_limit_seconds} seconds per scenario, run sequentially.`} Results are internally validated; scores have different objectives across scenarios.</p><div className="table-wrap"><table><thead><tr><th>Policy</th><th>Work complete</th><th>Overrun</th><th>Excess slots</th><th>ECLO</th><th>Score</th><th>Search state</th></tr></thead><tbody>{(Object.keys(job.scenarios) as Scenario[]).map(s => { const run = job.scenarios[s]!; return <tr key={s}><th>{s}</th><td>{run.scores ? `${run.scores.completion_percent ?? (run.feasible ? 100 : 0)}%` : "Pending"}</td><td>{run.scores?.overrun_days_total ?? "—"}</td><td>{run.scores?.excess_access_nights_total ?? "—"}</td><td>{run.scores?.eclo_nights_total ?? "—"}</td><td>{run.objective_score ?? "—"}</td><td>{["optimal", "optimal_for_policy"].includes(run.termination_reason ?? "") ? "Optimality proved" : run.phase === "improving" ? "Improving" : run.phase === "first_search" ? "Searching" : run.feasible ? "Validated result available" : run.termination_reason === "infeasible" ? "Infeasible under documented policy" : run.termination_reason === "time_limit" ? "No solution within time limit" : run.status}</td></tr>; })}</tbody></table></div><p>Downloadable policies: {Object.entries(job.scenarios).filter(([,run]) => run.feasible).map(([s,run]) => `${s} (revision ${run.solution_revision})`).join(", ") || "None yet"}. The ZIP manifest records included revisions.</p></div>}
      {job && <section className="results-workspace">
        <div className="scenario-rail">
          <div className="scenario-heading"><span className="step">02</span><div><h2>Policy runs</h2><p>{job.instance.activities} activities · {job.instance.total_accesses} accesses · {job.instance.horizon_weeks} weeks</p></div></div>
          {(Object.keys(job.scenarios) as Scenario[]).map((scenario) => { const run = job.scenarios[scenario]!; return <button key={scenario} className={`scenario-card ${selectedScenario === scenario ? "selected" : ""}`} onClick={() => setSelectedScenario(scenario)}><span className="scenario-code">{scenario}</span><span className="scenario-copy"><strong>{scenario === "A" ? "Strict supply" : scenario === "B" ? "Strict schedule" : "Balanced"}</strong><small>{run.error || run.message}</small></span><span className={`run-icon ${run.status}`}>{run.status === "running" ? <LoaderCircle size={18} className="spin" /> : run.status === "completed" ? <Check size={18} /> : run.status === "failed" ? <AlertTriangle size={18} /> : <Clock3 size={18} />}</span><span className="progress-track"><i style={{ width: `${run.progress}%` }} /></span></button>; })}
          <div className="rail-actions">{["queued", "running"].includes(job.status) && <button className="secondary-button" onClick={() => void cancel()}><CircleStop size={17} /> Stop search</button>}<a className={`primary-button ${canDownload ? "" : "disabled"}`} href={canDownload ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}><Download size={17} /> Download result ZIP</a>{job.algorithm === "strategies" && <a className="secondary-button" href={`${API_BASE}/api/ps1/jobs/${job.job_id}/diagnostics`}><Download size={17} /> Search report</a>}</div>
        </div>
        <div className="scenario-detail">{job.algorithm === "strategies" && <SearchProgress scenario={selectedScenario} diagnostics={job.scenarios[selectedScenario]?.diagnostics} />}{!selected ? <EmptyResult run={job.scenarios[selectedScenario]!} scenario={selectedScenario} /> : <ScenarioView detail={selected} jobId={job.job_id} />}</div>
      </section>}
    </main>
  );
}

function SearchProgress({ scenario, diagnostics: d }: { scenario: Scenario; diagnostics?: Diagnostics }) {
  const format = (value?: number) => value == null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return <section className="data-panel search-progress" aria-live="polite">
    <div className="subheading"><h3>Scenario {scenario} search</h3><span>{d?.status === "optimal_for_policy" ? "Optimal for configured policy" : "Best validated schedule"}</span></div>
    <div className="metric-grid"><Metric label="Best cost" value={format(d?.objective)} /><Metric label="Model lower bound" value={format(d?.global_lower_bound)} /><Metric label="Absolute gap" value={format(d?.absolute_gap)} /><Metric label="First feasible (s)" value={format(d?.time_to_first_feasible)} /></div>
    <p className="muted">Bounds and validation apply to the documented safety policy. Official validator not supplied. A feasible result does not by itself prove optimality.</p>
    {!!d?.trajectory?.length && <details><summary>Cost improvements ({d.trajectory.length})</summary><div className="table-wrap"><table><thead><tr><th>Elapsed seconds</th><th>Validated cost</th></tr></thead><tbody>{d.trajectory.map((point, index) => <tr key={index}><td>{format(point.seconds)}</td><td>{format(point.objective)}</td></tr>)}</tbody></table></div></details>}
  </section>;
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
    <p className="revision-note">Revision {detail.solution_revision} · {detail.solver_stats.optimal ? "Optimality proved for the documented model" : "Best validated result; optimum not proved"} · Cost: delay {detail.score_breakdown.delay}, excess supply {detail.score_breakdown.excess_supply}, ECLO {detail.score_breakdown.eclo}.</p>
    {detail.validation.detail.location_usage && <Inspection activities={detail.activity_details} usage={detail.validation.detail.location_usage} />}
    <div className="visual-grid">
      <section className="data-panel"><div className="subheading"><h3>Weekly access load</h3><span>{detail.accesses.length} rows</span></div><div className="week-chart">{weeks.map(([week, count]) => <div key={week} title={`Week ${week}: ${count} accesses`}><i style={{ height: `${Math.max(8, count / maxWeekAccess * 100)}%` }} /><small>{week}</small></div>)}</div></section>
      <section className="data-panel"><div className="subheading"><h3>Capacity hotspots</h3><span>{hotspots.length} at or above supply</span></div><div className="hotspot-list">{hotspots.slice(0, 8).map((item) => <div key={`${item.location_id}-${item.week}`}><span><strong>{item.location_id}</strong><small>Week {item.week}</small></span><i><b style={{ width: `${item.used / maxUsed * 100}%` }} /></i><em>{item.used}/{item.capacity}</em></div>)}{!hotspots.length && <p className="muted">No locations reach nominal capacity.</p>}</div></section>
    </div>
    <section className="data-panel results-table-panel"><div className="subheading"><h3>Contract completion</h3><div className="csv-links">{["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"].map((file) => <a key={file} title={`Download ${file}`} href={`${API_BASE}/api/ps1/jobs/${jobId}/scenarios/${detail.scenario}/files/${file}?revision=${detail.solution_revision}`}><Download size={14} />{file.replace("SCHEDULE_", "").replace(".csv", "")}</a>)}</div></div><div className="table-wrap"><table><thead><tr><th>Contract</th><th>Completion</th><th>Overrun</th><th>State</th></tr></thead><tbody>{detail.results.map((row) => <tr key={row.contract_number}><td>{row.contract_number}</td><td>{row.simulated_completion_date}</td><td>{row.overrun_days} days</td><td><span className={`row-state ${row.overrun_days ? "late" : "on-time"}`}>{row.overrun_days ? "Overrun" : "On plan"}</span></td></tr>)}</tbody></table></div></section>
  </>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
