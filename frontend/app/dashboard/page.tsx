"use client";

import Link from "next/link";
import { AlertTriangle, CalendarDays, CheckCircle2, GitBranch, Lock, Plus, RefreshCw, ShieldCheck, SlidersHorizontal, Unlock } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type MaintenanceRequest = {
  request_id: string;
  title: string;
  track_sector: string;
  work_type: string;
  duration_minutes: number;
  earliest_start: string;
  deadline: string;
  priority: number;
  required_crew: string[];
  required_equipment: string[];
  dependencies: string[];
  approval_status: string;
  locked: boolean;
};

type ScheduledWork = {
  request_id: string;
  start_time: string;
  end_time: string;
  assigned_crew: string[];
  assigned_equipment: string[];
  track_sector: string;
  changed_from_original: boolean;
  change_reason?: string | null;
  status: string;
};

type Conflict = {
  conflict_id: string;
  type: string;
  severity: string;
  request_ids: string[];
  resource?: string | null;
  explanation: string;
  suggested_action?: string | null;
};

type Kpis = {
  unresolved_conflicts: number;
  critical_jobs_scheduled: number;
  engineering_hours_utilisation: number;
  estimated_overtime_minutes: number;
  schedule_stability: number;
  robustness_score: number;
};

type Alternative = {
  option: string;
  label: string;
  scheduled_work: ScheduledWork[];
  conflicts: Conflict[];
  kpis: Kpis;
  explanation: string;
  rank: number;
  disruption_score: number;
  overtime_score: number;
  completion_score: number;
  critical_priority_score: number;
  overall_score: number;
};

type Role = "requester" | "schedule_manager";

const emptyKpis: Kpis = {
  unresolved_conflicts: 0,
  critical_jobs_scheduled: 0,
  engineering_hours_utilisation: 0,
  estimated_overtime_minutes: 0,
  schedule_stability: 100,
  robustness_score: 100
};

const dependencyRules = [
  { work: "signal_test", prerequisite: "signal_replacement" },
  { work: "track_renewal", prerequisite: "track_inspection" },
  { work: "electrical_repair", prerequisite: "power_isolation" },
  { work: "service_restore", prerequisite: "safety_clearance" }
];

const engineeringHours = ["00:00", "01:00", "02:00", "03:00", "04:00", "05:00"];
const fallbackTracks = ["T08", "T09", "T10", "T11", "T12", "T13", "T14"];

function formatDate(value: Date) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function workLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sameDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate();
}

function monthDays(anchor: Date) {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 35 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

function requestFor(item: ScheduledWork, requests: MaintenanceRequest[]) {
  return requests.find((request) => request.request_id === item.request_id);
}

function minutesFromEngineeringStart(value: string) {
  const date = new Date(value);
  return date.getHours() * 60 + date.getMinutes();
}

function calendarBlockStyle(item: ScheduledWork) {
  const start = minutesFromEngineeringStart(item.start_time);
  const end = minutesFromEngineeringStart(item.end_time);
  return {
    top: `${Math.max(0, start)}px`,
    height: `${Math.max(24, end - start)}px`
  };
}

export default function DashboardPage() {
  const [role, setRole] = useState<Role>("requester");
  const [requests, setRequests] = useState<MaintenanceRequest[]>([]);
  const [schedule, setSchedule] = useState<ScheduledWork[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [kpis, setKpis] = useState<Kpis>(emptyKpis);
  const [alternatives, setAlternatives] = useState<Alternative[]>([]);
  const [selectedAlternative, setSelectedAlternative] = useState<Alternative | null>(null);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [status, setStatus] = useState("Loading planning board...");

  async function loadDashboard() {
    try {
      const [requestResponse, scheduleResponse, conflictResponse, kpiResponse] = await Promise.all([
        fetch(`${API_BASE}/api/requests`),
        fetch(`${API_BASE}/api/schedule`),
        fetch(`${API_BASE}/api/conflicts/detect`, { method: "POST" }),
        fetch(`${API_BASE}/api/kpis`)
      ]);

      if (!requestResponse.ok || !scheduleResponse.ok || !conflictResponse.ok || !kpiResponse.ok) {
        throw new Error("Could not load planning board data.");
      }

      const loadedRequests = await requestResponse.json();
      setRequests(loadedRequests);
      setSchedule(await scheduleResponse.json());
      setConflicts(await conflictResponse.json());
      setKpis(await kpiResponse.json());
      setSelectedRequestId((current) => current ?? loadedRequests[0]?.request_id ?? null);
      setStatus("Planning board is synced with the backend.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not load planning board data.");
    }
  }

  async function optimiseSchedule() {
    setStatus("Generating active feasible schedule...");
    try {
      const response = await fetch(`${API_BASE}/api/schedule/optimise?option=minimum_disruption`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
          : payload.detail;
        throw new Error(detail || "Could not generate schedule.");
      }
      setSelectedAlternative(null);
      await loadDashboard();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not generate schedule.");
    }
  }

  async function compareAlternatives() {
    setStatus("Generating alternatives...");
    try {
      const response = await fetch(`${API_BASE}/api/schedule/alternatives`, { method: "POST" });
      if (!response.ok) {
        throw new Error("Could not generate alternatives.");
      }
      const payload = await response.json();
      setAlternatives(payload);
      setSelectedAlternative(payload[0] ?? null);
        setStatus(payload.length ? "Top feasible alternatives are ready for Schedule Manager review." : "No feasible alternatives were generated.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not generate alternatives.");
    }
  }

  async function approveSchedule() {
    setStatus("Checking approval authority...");
    try {
      const response = await fetch(`${API_BASE}/api/schedule/approve?role=${role}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
          : payload.detail;
        throw new Error(detail || "Schedule could not be approved.");
      }
      setStatus(
        payload.approved
          ? `Schedule approved and locked by Schedule Manager. ${payload.locked_items ?? 0} items fixed.`
          : `${payload.unresolved_conflicts} resource contentions remain before approval.`
      );
      await loadDashboard();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Schedule could not be approved.");
    }
  }

  async function applySelectedAlternative() {
    if (!selectedAlternative) {
      setStatus("Select an alternative before applying it.");
      return;
    }
    setStatus(`Applying ${selectedAlternative.label}...`);
    try {
      const response = await fetch(`${API_BASE}/api/schedule/apply?option=${selectedAlternative.option}&role=${role}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
          : payload.detail;
        throw new Error(detail || "Alternative could not be applied.");
      }
      setSelectedAlternative(null);
      setAlternatives([]);
      await loadDashboard();
      setStatus(`${selectedAlternative.label} applied as the active schedule.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Alternative could not be applied.");
    }
  }

  async function rejectSelectedRequest() {
    if (!selectedRequestId) {
      setStatus("Select a request before rejecting it.");
      return;
    }
    setStatus(`Rejecting ${selectedRequestId}...`);
    try {
      const response = await fetch(`${API_BASE}/api/schedule/reject/${selectedRequestId}?role=${role}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Request could not be rejected.");
      }
      setSelectedAlternative(null);
      await loadDashboard();
      setStatus(`${selectedRequestId} rejected and removed from the active schedule.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Request could not be rejected.");
    }
  }

  async function toggleSelectedLock() {
    if (!selectedRequestId || !selectedScheduledItem) {
      setStatus("Select scheduled work before changing its lock state.");
      return;
    }
    const action = selectedScheduledItem.status === "locked" ? "unlock" : "lock";
    setStatus(`${action === "lock" ? "Locking" : "Unlocking"} ${selectedRequestId}...`);
    try {
      const response = await fetch(`${API_BASE}/api/schedule/${action}/${selectedRequestId}?role=${role}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Lock state could not be changed.");
      }
      await loadDashboard();
      setStatus(`${selectedRequestId} is now ${action === "lock" ? "locked" : "unlocked"}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Lock state could not be changed.");
    }
  }

  async function modifySelectedStart() {
    if (!selectedRequestId || !selectedScheduledItem || !selectedRequest) {
      setStatus("Select scheduled work before modifying it.");
      return;
    }
    const current = selectedScheduledItem.start_time.slice(0, 16);
    const nextStart = window.prompt("New start time", current);
    if (!nextStart) {
      return;
    }
    const start = new Date(nextStart);
    const end = new Date(start.getTime() + selectedRequest.duration_minutes * 60_000);
    setStatus(`Modifying ${selectedRequestId}...`);
    try {
      const response = await fetch(`${API_BASE}/api/schedule/modify/${selectedRequestId}?role=${role}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          changed_from_original: true,
          change_reason: "Modified by Schedule Manager during decision review."
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
          : payload.detail;
        throw new Error(detail || "Scheduled work could not be modified.");
      }
      await loadDashboard();
      setStatus(`${selectedRequestId} moved to ${formatTime(payload.start_time)}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Scheduled work could not be modified.");
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const visibleSchedule = selectedAlternative?.scheduled_work ?? schedule;
  const visibleConflicts = selectedAlternative?.conflicts ?? conflicts;
  const displayedKpis = selectedAlternative?.kpis ?? kpis;
  const selectedRequest = selectedRequestId ? requests.find((request) => request.request_id === selectedRequestId) ?? null : null;
  const selectedScheduledItem = selectedRequestId
    ? visibleSchedule.find((item) => item.request_id === selectedRequestId) ?? null
    : null;
  const days = monthDays(selectedDate);
  const todayItems = visibleSchedule
    .filter((item) => sameDay(new Date(item.start_time), selectedDate))
    .sort((left, right) => new Date(left.start_time).getTime() - new Date(right.start_time).getTime());
  const dayTracks = Array.from(new Set([...fallbackTracks, ...todayItems.map((item) => item.track_sector)])).sort();

  const conflictsByRequest = useMemo(() => {
    const map = new Map<string, Conflict[]>();
    for (const conflict of visibleConflicts) {
      for (const requestId of conflict.request_ids) {
        map.set(requestId, [...(map.get(requestId) ?? []), conflict]);
      }
    }
    return map;
  }, [visibleConflicts]);
  const selectedConflicts = selectedRequestId ? conflictsByRequest.get(selectedRequestId) ?? [] : visibleConflicts;

  function dayItems(day: Date) {
    return visibleSchedule.filter((item) => sameDay(new Date(item.start_time), day));
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">RailFlowAI Planning Board</div>
          <div className="subtitle">Monthly capacity, today&apos;s engineering work, and feasible alternatives.</div>
        </div>
        <nav className="nav">
          <select className="role-select" value={role} onChange={(event) => setRole(event.target.value as Role)}>
            <option value="requester">Requester</option>
            <option value="schedule_manager">Schedule Manager</option>
          </select>
          <Link className="secondary" href="/request/new">
            <Plus size={18} />
            New Request
          </Link>
          <button className="button secondary" onClick={loadDashboard}>
            <RefreshCw size={18} />
            Refresh
          </button>
          <button className="button" onClick={optimiseSchedule}>
            <SlidersHorizontal size={18} />
            Generate Schedule
          </button>
        </nav>
      </header>

      <section className="status-strip" role="status">
        <CheckCircle2 size={16} />
        {status}
      </section>

      <section className="page-intro">
        <div>
          <span className="eyebrow">Live schedule control</span>
          <h1>Plan capacity, review risks, and approve feasible railway work.</h1>
        </div>
        <div className="intro-meta">
          <span>{visibleSchedule.length} scheduled items</span>
          <span>{visibleConflicts.length} active contentions</span>
        </div>
      </section>

      <section className="planning-hero">
        <section className="month-board">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Calendar</span>
              <h2>
                <CalendarDays size={18} />
                {new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(selectedDate)}
              </h2>
            </div>
            <span className="legend"><i /> contention</span>
          </div>
          <div className="month-grid">
            {days.map((day) => {
              const items = dayItems(day);
              const hasConflict = items.some((item) => conflictsByRequest.has(item.request_id));
              return (
                <button
                  className={`day-cell ${sameDay(day, selectedDate) ? "selected" : ""} ${day.getMonth() !== selectedDate.getMonth() ? "muted-day" : ""}`}
                  key={day.toISOString()}
                  onClick={() => setSelectedDate(day)}
                  aria-label={`${formatDate(day)}, ${items.length} scheduled item${items.length === 1 ? "" : "s"}${hasConflict ? ", has contention" : ""}`}
                >
                  <span>{day.getDate()}</span>
                  <strong>{items.length}</strong>
                  {hasConflict && <em />}
                </button>
              );
            })}
          </div>
        </section>

        <section className="today-board">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Selected day</span>
              <h2>Track Calendar / {formatDate(selectedDate)}</h2>
            </div>
          </div>
          <div className="day-calendar">
            <div className="calendar-corner">Time</div>
            <div className="track-columns" style={{ "--track-count": dayTracks.length } as CSSProperties}>
              {dayTracks.map((track) => (
                <div className="track-column-header" key={track}>{track}</div>
              ))}
            </div>
            <div className="time-axis">
              {engineeringHours.map((hour) => (
                <div className="time-tick" key={hour}>{hour}</div>
              ))}
            </div>
            <div className="calendar-grid" style={{ "--track-count": dayTracks.length } as CSSProperties}>
              {dayTracks.map((track) => (
                <div className="track-column" key={track}>
                  {engineeringHours.slice(0, -1).map((hour) => (
                    <span className="hour-line" key={hour} />
                  ))}
                  {todayItems
                    .filter((item) => item.track_sector === track)
                    .map((item) => {
                      const request = requestFor(item, requests);
                      const conflict = conflictsByRequest.get(item.request_id)?.[0];
                      return (
                        <button
                          className={`calendar-event ${conflict ? "has-conflict" : ""} ${selectedRequestId === item.request_id ? "selected" : ""}`}
                          key={`${item.request_id}-${item.start_time}`}
                          onClick={() => setSelectedRequestId(item.request_id)}
                          style={calendarBlockStyle(item)}
                        >
                          <strong>{item.request_id}</strong>
                          <span>{formatTime(item.start_time)}-{formatTime(item.end_time)}</span>
                          <span>{workLabel(request?.work_type ?? "work")}</span>
                        </button>
                      );
                    })}
                </div>
              ))}
              {todayItems.length === 0 && (
                <p className="calendar-empty">No scheduled work for this date. Add pending requests, then generate the batch schedule.</p>
              )}
            </div>
          </div>
        </section>
      </section>

      <section className="kpis">
        <div className="kpi danger"><span>Resource Contentions</span><strong>{displayedKpis.unresolved_conflicts}</strong></div>
        <div className="kpi"><span>Critical Jobs Scheduled</span><strong>{displayedKpis.critical_jobs_scheduled}</strong></div>
        <div className="kpi"><span>Window Utilisation</span><strong>{displayedKpis.engineering_hours_utilisation}%</strong></div>
        <div className="kpi warning"><span>Estimated Overtime</span><strong>{displayedKpis.estimated_overtime_minutes}m</strong></div>
        <div className="kpi success"><span>Schedule Stability</span><strong>{displayedKpis.schedule_stability}%</strong></div>
        <div className="kpi success"><span>Robustness Score</span><strong>{displayedKpis.robustness_score}</strong></div>
      </section>

      <section className="ops-grid">
        <section className="panel">
          <div className="panel-header">
            <span>Request Queue</span>
            <small>{requests.length} total</small>
          </div>
          <div className="panel-body request-list">
            {requests.length === 0 && <p className="muted">No requests yet. Create one from New Request.</p>}
            {requests.map((request) => (
              <button
                className={`request-item select-card ${selectedRequestId === request.request_id ? "selected" : ""}`}
                key={request.request_id}
                onClick={() => setSelectedRequestId(request.request_id)}
              >
                <strong>{request.request_id} / {request.title}</strong>
                <span>
                  {request.track_sector} / {workLabel(request.work_type)} / Priority {request.priority}
                </span>
                <span className={`badge ${request.locked ? "success" : "neutral"}`}>
                  {request.locked ? "Locked" : "Pending"}
                </span>
                {request.dependencies.length > 0 && (
                  <span className="dependency-line">
                    <GitBranch size={14} />
                    after {request.dependencies.join(", ")}
                  </span>
                )}
                {conflictsByRequest.has(request.request_id) && <span className="badge danger">Contention</span>}
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span>Predefined Dependencies</span>
            <small>sequencing rules</small>
          </div>
          <div className="panel-body dependency-list">
            {dependencyRules.map((rule) => (
              <div className="dependency-rule" key={rule.work}>
                <span>{workLabel(rule.prerequisite)}</span>
                <strong>{workLabel(rule.work)}</strong>
              </div>
            ))}
          </div>
        </section>

        <aside className="panel">
          <div className="panel-header">
            <span>Decision Review</span>
            {visibleConflicts.length > 0 && (
              <small className="danger-text">
                <AlertTriangle size={13} />
                action needed
              </small>
            )}
          </div>
          <div className="panel-body decision-stack">
            <div className="selection-summary">
              <span className="eyebrow">Selected item</span>
              {selectedRequest ? (
                <>
                  <h3>{selectedRequest.request_id} / {selectedRequest.title}</h3>
                  <p>
                    {selectedRequest.track_sector} / {workLabel(selectedRequest.work_type)} / Priority {selectedRequest.priority}
                  </p>
                  {selectedScheduledItem ? (
                    <p>
                      Scheduled {formatTime(selectedScheduledItem.start_time)}-{formatTime(selectedScheduledItem.end_time)}
                      {selectedScheduledItem.changed_from_original ? " / moved from requested start" : " / requested slot preserved"}
                    </p>
                  ) : (
                    <p>This request is pending and is not in the visible schedule candidate yet.</p>
                  )}
                </>
              ) : (
                <p>Select a request, today card, or alternative to inspect exactly what the actions apply to.</p>
              )}
            </div>
            <div className="review-block">
              <span className="eyebrow">Review finding</span>
              <p>
                {selectedConflicts.length > 0
                  ? selectedConflicts[0].explanation
                  : "No active resource contention is reported for the selected item."}
              </p>
              {selectedConflicts[0]?.suggested_action && <p>{selectedConflicts[0].suggested_action}</p>}
            </div>
            {selectedAlternative && (
              <div className="review-block">
                <span className="eyebrow">Selected alternative</span>
                <p>{selectedAlternative.label}: {selectedAlternative.explanation}</p>
              </div>
            )}
            <button className="button secondary" onClick={compareAlternatives}>
              <SlidersHorizontal size={18} />
              Show Best Alternatives
            </button>
            {selectedAlternative && (
              <p>Alternative preview is selected. Generate the active schedule before approval, or clear the preview with Refresh.</p>
            )}
            <button className="button" disabled={role !== "schedule_manager" || !selectedAlternative} onClick={applySelectedAlternative}>
              <ShieldCheck size={18} />
              Apply Selected Alternative
            </button>
            <button className="button" disabled={role !== "schedule_manager" || Boolean(selectedAlternative)} onClick={approveSchedule}>
              <ShieldCheck size={18} />
              Approve Active Schedule
            </button>
            <button className="button secondary" disabled={role !== "schedule_manager" || !selectedScheduledItem} onClick={modifySelectedStart}>
              Modify
            </button>
            <button className="button secondary" disabled={role !== "schedule_manager" || !selectedRequestId} onClick={rejectSelectedRequest}>
              Reject
            </button>
            <button className="button secondary" disabled={role !== "schedule_manager" || !selectedScheduledItem} onClick={toggleSelectedLock} title="Lock schedule">
              {selectedScheduledItem?.status === "locked" ? <Unlock size={18} /> : <Lock size={18} />}
              {selectedScheduledItem?.status === "locked" ? "Unlock" : "Lock"}
            </button>
          </div>
        </aside>
      </section>

      {alternatives.length > 0 && (
        <section className="alternatives" aria-label="Schedule alternatives">
          {alternatives.map((alternative) => (
            <button
              className={`alternative ${selectedAlternative?.option === alternative.option ? "selected" : ""}`}
              key={alternative.option}
              onClick={() => {
                setSelectedAlternative(alternative);
                setStatus(`${alternative.label} selected for review. Approve only applies to the active generated schedule.`);
              }}
            >
              <strong>{alternative.label}</strong>
              <span>{alternative.overall_score}/100 overall</span>
              <span>{alternative.disruption_score} disruption</span>
              <span>{alternative.overtime_score} overtime</span>
              <span>{alternative.completion_score} completion</span>
              <span>{alternative.critical_priority_score} critical priority</span>
              <span>{alternative.conflicts.length} contentions</span>
            </button>
          ))}
        </section>
      )}
    </main>
  );
}
