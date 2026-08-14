"use client";

import Link from "next/link";
import { ArrowLeft, Clock3, MapPin, Send, Settings2, UsersRound } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Conflict = {
  conflict_id: string;
  type: string;
  severity: string;
  request_ids: string[];
  resource?: string | null;
  explanation: string;
  suggested_action?: string | null;
};

type Alternative = {
  option: string;
  label: string;
  conflicts: Conflict[];
  explanation: string;
  rank: number;
  disruption_score: number;
  overtime_score: number;
  completion_score: number;
  critical_priority_score: number;
  overall_score: number;
  changed_jobs_count: number;
  moved_locked_count: number;
  churn_penalty: number;
  impact_summary?: string | null;
};

type ScheduledWork = {
  request_id: string;
  start_time: string;
  end_time: string;
};

type ScheduleChange = {
  request_id: string;
  owner: string;
  previous_start?: string | null;
  previous_end?: string | null;
  proposed_start: string;
  proposed_end: string;
  was_locked: boolean;
  reason: string;
};

type FitResponse = {
  fits_current_schedule: boolean;
  conflicts: Conflict[];
  suggested_alternatives: Alternative[];
  scheduled_work?: ScheduledWork | null;
  requires_manager_review: boolean;
  affected_changes: ScheduleChange[];
  proposal_option?: string | null;
};

type FormState = {
  title: string;
  trackSector: string;
  workType: string;
  priority: string;
  earliestStart: string;
  deadline: string;
  durationMinutes: string;
  requiredCrew: string[];
  requiredEquipment: string[];
  notes: string;
  emergency: boolean;
};

type Catalog = {
  track_sectors: string[];
  work_types: string[];
  crews: string[];
  equipment: string[];
  priorities: number[];
  user_roles: string[];
};

const fallbackCatalog: Catalog = {
  track_sectors: ["T08", "T09", "T10", "T11", "T12", "T13", "T14"],
  work_types: [
    "inspection",
    "electrical",
    "track",
    "signal_replacement",
    "signal_test",
    "track_inspection",
    "track_renewal",
    "power_isolation",
    "electrical_repair",
    "safety_clearance",
    "service_restore"
  ],
  crews: ["E1", "E2", "TG1", "TG2", "MECH1", "MECH2", "SIG1", "SIG2", "SAFE1"],
  equipment: [
    "SignalKit-1",
    "SignalKit-2",
    "GeometryCar-1",
    "GeometryCar-2",
    "PowerUnit-1",
    "PowerUnit-2",
    "DiagnosticKit-1",
    "RailGrinder-1",
    "IsolationKit-1"
  ],
  priorities: [1, 2, 3, 4, 5],
  user_roles: ["requester", "schedule_manager"]
};

const initialForm: FormState = {
  title: "",
  trackSector: "T12",
  workType: "inspection",
  priority: "3",
  earliestStart: "",
  deadline: "",
  durationMinutes: "60",
  requiredCrew: [],
  requiredEquipment: [],
  notes: "",
  emergency: false
};

function toIsoLocal(value: string) {
  return new Date(value).toISOString();
}

function workLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function toggleValue(values: string[], value: string) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

export default function NewRequestPage() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<FitResponse | null>(null);
  const [catalog, setCatalog] = useState<Catalog>(fallbackCatalog);

  useEffect(() => {
    async function loadCatalog() {
      try {
        const response = await fetch(`${API_BASE}/api/catalog`);
        if (response.ok) {
          setCatalog(await response.json());
        }
      } catch {
        setCatalog(fallbackCatalog);
      }
    }

    void loadCatalog();
  }, []);

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("submitting");
    setMessage("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE}/api/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: `M-${Date.now().toString().slice(-6)}`,
          title: form.title,
          track_sector: form.trackSector,
          work_type: form.emergency ? "emergency" : form.workType,
          duration_minutes: Number(form.durationMinutes),
          earliest_start: toIsoLocal(form.earliestStart),
          deadline: toIsoLocal(form.deadline),
          priority: form.emergency ? 5 : Number(form.priority),
          required_crew: form.requiredCrew,
          required_equipment: form.requiredEquipment,
          notes: form.notes || null,
          source: form.emergency ? "emergency" : "manual"
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
          : payload.detail;
        throw new Error(detail || "Request could not be submitted.");
      }

      setResult(payload);
      setStatus("success");
      setMessage(
        payload.fits_current_schedule
          ? "Request placed into a tentative slot."
          : "Request needs manager review because fitting it requires schedule changes."
      );
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Request could not be submitted.");
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">New Request</div>
        </div>
        <nav className="nav">
          <Link className="secondary" href="/dashboard">
            <ArrowLeft size={18} />
            Schedule Dashboard
          </Link>
        </nav>
      </header>
      <section className="form-page">
        <form className="panel form" onSubmit={submitRequest}>
          <div className="panel-header">
            <span>Maintenance Request</span>
            <small>{form.emergency ? "emergency priority" : "standard intake"}</small>
          </div>
          <div className="panel-body form">
            <section className="form-section">
              <div className="form-section-title">
                <Settings2 size={18} />
                Work details
              </div>
              <div className="form-grid">
                <div className="field wide">
                  <label htmlFor="title">Title</label>
                  <input
                    id="title"
                    required
                    value={form.title}
                    onChange={(event) => setForm({ ...form, title: event.target.value })}
                    placeholder="Signal relay inspection"
                  />
                </div>
                <div className="field">
                  <label htmlFor="workType">Work Type</label>
                  <select id="workType" value={form.workType} onChange={(event) => setForm({ ...form, workType: event.target.value })}>
                    {catalog.work_types
                      .filter((workType) => workType !== "emergency")
                      .map((workType) => (
                        <option key={workType} value={workType}>
                          {workLabel(workType)}
                        </option>
                      ))}
                  </select>
                  <span className="help-text">
                    Some work types require scheduled prerequisites on the same track sector.
                  </span>
                </div>
                <div className="field">
                  <label htmlFor="trackSector">Track Sector</label>
                  <select id="trackSector" value={form.trackSector} onChange={(event) => setForm({ ...form, trackSector: event.target.value })}>
                    {catalog.track_sectors.map((sector) => (
                      <option key={sector} value={sector}>
                        {sector}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="priority">Priority</label>
                  <select
                    id="priority"
                    value={form.priority}
                    onChange={(event) => setForm({ ...form, priority: event.target.value })}
                    disabled={form.emergency}
                  >
                    {catalog.priorities
                      .slice()
                      .sort((left, right) => right - left)
                      .map((priority) => (
                        <option key={priority} value={priority}>
                          {priority} {priority === 5 ? "- Critical" : priority === 4 ? "- High" : priority === 3 ? "- Normal" : ""}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
            </section>

            <section className="form-section">
              <div className="form-section-title">
                <Clock3 size={18} />
                Timing
              </div>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="earliestStart">Earliest Start</label>
                  <input
                    id="earliestStart"
                    required
                    type="datetime-local"
                    value={form.earliestStart}
                    onChange={(event) => setForm({ ...form, earliestStart: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="deadline">Deadline</label>
                  <input
                    id="deadline"
                    required
                    type="datetime-local"
                    value={form.deadline}
                    onChange={(event) => setForm({ ...form, deadline: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="durationMinutes">Estimated Duration</label>
                  <input
                    id="durationMinutes"
                    required
                    min="1"
                    type="number"
                    value={form.durationMinutes}
                    onChange={(event) => setForm({ ...form, durationMinutes: event.target.value })}
                  />
                </div>
              </div>
            </section>

            <section className="form-section">
              <div className="form-section-title">
                <UsersRound size={18} />
                Resources
              </div>
            <div className="field">
              <label>Required Crew</label>
              <div className="choice-grid">
                {catalog.crews.map((crew) => (
                  <label className="choice-chip" key={crew}>
                    <input
                      checked={form.requiredCrew.includes(crew)}
                      type="checkbox"
                      onChange={() => setForm({ ...form, requiredCrew: toggleValue(form.requiredCrew, crew) })}
                    />
                    {crew}
                  </label>
                ))}
              </div>
            </div>
            <div className="field">
              <label>Required Equipment</label>
              <div className="choice-grid">
                {catalog.equipment.map((item) => (
                  <label className="choice-chip" key={item}>
                    <input
                      checked={form.requiredEquipment.includes(item)}
                      type="checkbox"
                      onChange={() => setForm({ ...form, requiredEquipment: toggleValue(form.requiredEquipment, item) })}
                    />
                    {item}
                  </label>
                ))}
              </div>
            </div>
            </section>

            <section className="form-section">
              <div className="form-section-title">
                <MapPin size={18} />
                Notes and status
              </div>
            <label className="check-row">
              <input
                checked={form.emergency}
                type="checkbox"
                onChange={(event) => setForm({ ...form, emergency: event.target.checked })}
              />
              Mark as emergency
            </label>
            <div className="field">
              <label htmlFor="notes">Notes</label>
              <textarea
                id="notes"
                rows={4}
                value={form.notes}
                onChange={(event) => setForm({ ...form, notes: event.target.value })}
              />
            </div>
            </section>
            <button className="button" disabled={status === "submitting"} type="submit">
              <Send size={18} />
              {status === "submitting" ? "Submitting" : "Submit"}
            </button>
            {message && <div className={`notice ${status}`}>{message}</div>}
            {result && (
              <div className="result-list">
                <strong>{result.fits_current_schedule ? "Fits Current Schedule" : "Needs Decision Review"}</strong>
                <p>
                  {result.fits_current_schedule
                    ? "No active conflict is reported for this requested slot."
                    : "The requested slot has a conflict. A manager can apply the proposed reschedule from the Planning Board."}
                </p>
                {result.scheduled_work && (
                  <p>
                    Your proposed slot: {formatDateTime(result.scheduled_work.start_time)}-{formatDateTime(result.scheduled_work.end_time)}
                  </p>
                )}
              </div>
            )}
            {result && result.requires_manager_review && result.affected_changes.length > 0 && (
              <div className="result-list">
                <strong>Affected Schedule Changes</strong>
                {result.affected_changes.map((change) => (
                  <p key={`${change.request_id}-${change.proposed_start}`}>
                    {change.request_id} / owner {change.owner}:{" "}
                    {change.previous_start && change.previous_end
                      ? `${formatDateTime(change.previous_start)}-${formatDateTime(change.previous_end)} -> `
                      : "new slot "}
                    {formatDateTime(change.proposed_start)}-{formatDateTime(change.proposed_end)}
                    {change.was_locked ? " / currently locked" : ""}
                  </p>
                ))}
              </div>
            )}
            {result && result.conflicts.length > 0 && (
              <div className="result-list">
                <strong>Resource Contention</strong>
                {result.conflicts.map((conflict) => (
                  <p key={conflict.conflict_id}>
                    {conflict.explanation} {conflict.suggested_action}
                  </p>
                ))}
              </div>
            )}
            {result && result.suggested_alternatives.length > 0 && (
              <div className="result-list">
                <strong>Schedule Proposals</strong>
                {result.suggested_alternatives.map((alternative) => (
                  <p key={alternative.option}>
                    #{alternative.rank} {alternative.label}: {alternative.overall_score}/100 overall. {alternative.explanation}
                    {alternative.impact_summary ? ` ${alternative.impact_summary}` : ""}
                  </p>
                ))}
              </div>
            )}
          </div>
        </form>
      </section>
    </main>
  );
}
