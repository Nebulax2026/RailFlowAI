"use client";

import {
  Activity,
  AlertTriangle,
  Check,
  CircleStop,
  Clock3,
  Download,
  FileSpreadsheet,
  LoaderCircle,
  MoreVertical,
  Network,
  Play,
  UploadCloud,
  X
} from "lucide-react";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { ScheduleResults } from "./schedule-results";
import { api, ApiError } from "./api-client";
import type { Job, Scenario, ScenarioDetail } from "./schedule-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const REQUIRED_FILES = [
  "01_LINES.csv",
  "02_STATIONS.csv",
  "03_SECTORS.csv",
  "04_LOCATION_SUPPLY.csv",
  "05_BUFFER_LOCATION.csv",
  "06_PARAMETERS.csv",
  "07_PROJECT_DETAILS.csv",
  "08_ACTIVITY_DETAILS.csv"
];
const JOB_STORAGE_KEY = "railflow-planner-job-id";

export default function Workspace() {
  const [files, setFiles] = useState<Map<string, File>>(new Map());
  const [publicDatasetSelected, setPublicDatasetSelected] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [details, setDetails] = useState<Partial<Record<Scenario, ScenarioDetail>>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [intake, setIntake] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const [isSandboxActive, setIsSandboxActive] = useState(false);
  const requestPending = useRef(false);
  const [restoring, setRestoring] = useState(true);

  const active = restoring || busy || job?.status === "queued" || job?.status === "running";
  const jobId = job?.job_id;

  useEffect(() => {
    let disposed = false;
    async function restore() {
      try {
        const saved = window.localStorage.getItem(JOB_STORAGE_KEY);
        if (!saved) return;
        const restored = await api<Job>(`/api/ps1/jobs/${encodeURIComponent(saved)}`);
        if (!disposed) {
          setJob(restored);
          setIntake(false);
        }
      } catch (err) {
        if (disposed) return;
        if (err instanceof ApiError && [404, 410].includes(err.status)) {
          try { window.localStorage.removeItem(JOB_STORAGE_KEY); } catch {}
          setError("The previous job expired or is no longer available. Load a demand book to begin.");
        } else {
          setError("Could not restore the previous job. Refresh to retry.");
        }
      } finally {
        if (!disposed) setRestoring(false);
      }
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
          setJob(null);
          setDetails({});
          setIntake(true);
          setError("This job expired or is no longer available. Load a demand book to begin.");
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Could not refresh solve job.");
      }
      if (!disposed) timer = setTimeout(poll, 1200);
    }

    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [jobId]);

  const allFilesReady = publicDatasetSelected || (REQUIRED_FILES.every((name) => files.has(name)) && files.size === REQUIRED_FILES.length);
  const canDownload = Boolean(
    job &&
    Object.values(job.scenarios).some((run) => run.feasible) &&
    !isSandboxActive
  );

  function acceptFiles(list: FileList | File[]) {
    if (busy || active) return;
    const next = new Map<string, File>();
    Array.from(list).forEach((file) => {
      if (file.name.toLowerCase().endsWith(".csv")) next.set(file.name, file);
    });
    setFiles(next);
    setPublicDatasetSelected(false);
    setError("");
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    acceptFiles(event.dataTransfer.files);
  }

  function selectPublicDataset() {
    if (busy || active) return;
    setPublicDatasetSelected(true);
    setFiles(new Map());
    setError("");
  }

  async function start() {
    if (requestPending.current || active || !allFilesReady) return;
    requestPending.current = true;
    setBusy(true);
    setError("");
    try {
      const init: RequestInit = { method: "POST" };
      const params = new URLSearchParams({ algorithm: "legacy" });
      if (publicDatasetSelected) {
        params.set("public", "true");
      } else {
        const body = new FormData();
        REQUIRED_FILES.forEach((name) => body.append("files", files.get(name)!));
        init.body = body;
      }
      const created = await api<Job>(`/api/ps1/jobs?${params}`, init);
      setDetails({});
      setJob(created);
      setIntake(false);
      try {
        window.localStorage.setItem(JOB_STORAGE_KEY, created.job_id);
      } catch {
        setError("Job started, but this browser could not save it for re-entry.");
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The solve job could not be started.");
    } finally {
      setBusy(false);
      requestPending.current = false;
    }
  }

  async function cancel() {
    if (!job || cancelling) return;
    setCancelling(true);
    try {
      setJob(await api<Job>(`/api/ps1/jobs/${job.job_id}`, { method: "DELETE" }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not cancel the job.");
    } finally {
      setCancelling(false);
    }
  }

  return (
    <main className="app-shell">
      {/* App Header */}
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark"><Network size={18} /></span>
          <strong>RailFlowAI</strong>
        </div>

        {/* Hide previous job summary/downloads when in intake mode */}
        {!intake && job ? (
          <>
            <div className="dataset-summary">
              <strong>{job.source === "public" ? "Public Dataset" : "Demand Book"}</strong>
              <span>
                {job.instance.activities} activities · {job.instance.total_accesses} accesses · {job.instance.horizon_weeks} weeks
              </span>
            </div>

            <div className="header-actions">
              <span className={`job-pill ${job.status}`} title={`Expires ${new Date(job.expires_at).toLocaleString()}`}>
                <Clock3 size={13} />
                {job.status}
              </span>

              <button className="secondary-button" disabled={active || busy} onClick={() => setIntake(true)}>
                Change Data
              </button>

              {(job.status === "queued" || job.status === "running") && (
                <button className="secondary-button" disabled={cancelling} onClick={() => void cancel()}>
                  <CircleStop size={14} />
                  {cancelling ? "Cancelling…" : "Cancel"}
                </button>
              )}

              {/* Integrated Split Download Button Group */}
              <div
                className={`split-button-group ${isSandboxActive ? "sandbox-blocked" : ""}`}
                title={isSandboxActive ? "Resolve or discard active Re-plan Sandbox first" : undefined}
              >
                <a
                  className={`split-button-main ${canDownload ? "" : "disabled"}`}
                  aria-disabled={!canDownload}
                  href={canDownload ? `${API_BASE}/api/ps1/jobs/${job.job_id}/download` : undefined}
                >
                  <Download size={14} />
                  Download ZIP
                </a>
                <button
                  className="split-button-trigger"
                  disabled={!canDownload}
                  onClick={() => setDownloadMenuOpen(!downloadMenuOpen)}
                  aria-label="More download options"
                >
                  <MoreVertical size={14} />
                </button>

                {downloadMenuOpen && canDownload && (
                  <div className="dropdown-menu" onMouseLeave={() => setDownloadMenuOpen(false)}>
                    <a
                      className="dropdown-item"
                      href={`${API_BASE}/api/ps1/jobs/${job.job_id}/scenarios/A/files/SCHEDULE_ACCESS.csv`}
                      download
                    >
                      <Download size={12} /> SCHEDULE_ACCESS.csv
                    </a>
                    <a
                      className="dropdown-item"
                      href={`${API_BASE}/api/ps1/jobs/${job.job_id}/scenarios/A/files/SCHEDULE_OCCUPANCY.csv`}
                      download
                    >
                      <Download size={12} /> SCHEDULE_OCCUPANCY.csv
                    </a>
                    <a
                      className="dropdown-item"
                      href={`${API_BASE}/api/ps1/jobs/${job.job_id}/scenarios/A/files/RESULTS.csv`}
                      download
                    >
                      <Download size={12} /> RESULTS.csv
                    </a>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="header-actions">
            {!intake && (
              <button className="secondary-button" onClick={() => setIntake(true)}>
                Demand Book
              </button>
            )}
            {job && intake && (
              <button className="secondary-button" onClick={() => setIntake(false)}>
                Back to Dashboard
              </button>
            )}
          </div>
        )}
      </header>

      {error && (
        <div className="alert error" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button aria-label="Dismiss error" onClick={() => setError("")}><X size={15} /></button>
        </div>
      )}

      {restoring && <p className="restore-notice" role="status" style={{ padding: "12px 20px" }}>Restoring previous session…</p>}

      {/* Demand Book Intake Screen */}
      <section className="intake-screen" hidden={!intake} aria-label="Demand book input">
        <div className="tool-panel upload-panel">
          <div className="panel-heading">
            <h1>Demand Book Configuration</h1>
            <span>
              {publicDatasetSelected ? "8/8 Public Files Selected" : `${REQUIRED_FILES.filter((name) => files.has(name)).length}/8 custom files`}
            </span>
          </div>
          <p className="muted">
            Drop or select the eight official CSV files to optimize across all three operational policies, or choose the verified public dataset.
          </p>

          <label className="drop-zone" onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}>
            <UploadCloud size={28} color="var(--cyan)" />
            <strong style={{ fontSize: "14px", color: "var(--text-primary)" }}>Select or drop eight CSV files</strong>
            <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>Official filenames · UTF-8 · up to 2 MB each</span>
            <input
              aria-label="Select demand book CSV files"
              type="file"
              accept=".csv,text/csv"
              multiple
              disabled={busy || active}
              onChange={(e) => e.target.files && acceptFiles(e.target.files)}
            />
          </label>

          {/* 2-Column Checklist for full visibility */}
          <div className="file-checklist-2col">
            {REQUIRED_FILES.map((name) => {
              const isReady = publicDatasetSelected || files.has(name);
              return (
                <div key={name} className={isReady ? "ready" : "missing"}>
                  {isReady ? <Check size={14} /> : <FileSpreadsheet size={14} />}
                  <span title={name}>{name}</span>
                  <small style={{ color: isReady ? "var(--emerald)" : "var(--text-dim)" }}>
                    {publicDatasetSelected ? "Public Ready" : files.has(name) ? `${Math.ceil(files.get(name)!.size / 1024)} KB` : "Required"}
                  </small>
                </div>
              );
            })}
          </div>

          <div className="button-row" style={{ marginTop: "20px" }}>
            <button
              className="primary-button"
              disabled={!allFilesReady || busy || active}
              onClick={() => void start()}
            >
              {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
              Run Demand Book
            </button>
            <button
              className={`secondary-button ${publicDatasetSelected ? "active" : ""}`}
              disabled={busy || active}
              onClick={selectPublicDataset}
              style={{ borderColor: publicDatasetSelected ? "var(--cyan)" : undefined }}
            >
              <Activity size={16} />
              Load Public Dataset
            </button>
          </div>
        </div>
      </section>

      {/* Main Results Dashboard (3-Column Layout) */}
      {job && (
        <div className="results-host" hidden={intake}>
          <ScheduleResults
            key={job.job_id}
            job={job}
            details={details}
            onSandboxStateChange={setIsSandboxActive}
          />
        </div>
      )}
    </main>
  );
}
