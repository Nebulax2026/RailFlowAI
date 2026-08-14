"use client";

import Link from "next/link";
import { AlertTriangle, CalendarDays, CheckCircle2, Database, GitBranch, Plus, RefreshCw, ShieldCheck, SlidersHorizontal, Trash2 } from "lucide-react";
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
  created_by: string;
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
  changed_jobs_count: number;
  moved_locked_count: number;
  churn_penalty: number;
  impact_summary?: string | null;
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

const engineeringHours = [
  "06:00",
  "07:00",
  "08:00",
  "09:00",
  "10:00",
  "11:00",
  "12:00",
  "13:00",
  "14:00",
  "15:00",
  "16:00",
  "17:00",
  "18:00",
  "19:00",
  "20:00",
  "21:00",
  "22:00"
];
const timelineStartMinutes = 6 * 60;
const timeSlotHeight = 88;
const fallbackTracks = ["T08", "T09", "T10", "T11", "T12", "T13", "T14"];

function formatDate(value: Date) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
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

function scheduledFor(requestId: string, schedule: ScheduledWork[]) {
  return schedule.find((item) => item.request_id === requestId);
}

function minutesFromEngineeringStart(value: string) {
  const date = new Date(value);
  return date.getHours() * 60 + date.getMinutes();
}

function calendarBlockStyle(item: ScheduledWork) {
  const start = (minutesFromEngineeringStart(item.start_time) - timelineStartMinutes) * (timeSlotHeight / 60);
  const end = (minutesFromEngineeringStart(item.end_time) - timelineStartMinutes) * (timeSlotHeight / 60);
  return {
    top: `${Math.max(0, start)}px`,
    height: `${Math.max(24, end - start)}px`
  };
}

function isLockedStatus(status: string) {
  return status.toLowerCase() === "locked";
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
  const [selectedPendingIds, setSelectedPendingIds] = useState<string[]>([]);
  const [selectedScheduledIds, setSelectedScheduledIds] = useState<string[]>([]);
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

      const loadedRequests: MaintenanceRequest[] = await requestResponse.json();
      const loadedSchedule: ScheduledWork[] = await scheduleResponse.json();
      setRequests(loadedRequests);
      setSchedule(loadedSchedule);
      setConflicts(await conflictResponse.json());
      setKpis(await kpiResponse.json());
      const scheduledIds = new Set(loadedSchedule.map((item) => item.request_id));
      const pendingRequests = loadedRequests.filter(
        (request) => request.approval_status === "draft" && !request.locked && !scheduledIds.has(request.request_id)
      );
      setSelectedRequestId((current) => current ?? pendingRequests[0]?.request_id ?? loadedSchedule[0]?.request_id ?? null);
      const firstVisibleDate = loadedSchedule[0]?.start_time ?? loadedRequests[0]?.earliest_start;
      if (firstVisibleDate) {
        setSelectedDate((current) => {
          const next = new Date(firstVisibleDate);
          return sameDay(current, next) ? current : next;
        });
      }
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
    if (selectedPendingIds.length === 0) {
      setStatus("Select one or more pending requests before showing proposals.");
      return;
    }
    setStatus("Generating schedule proposals...");
    try {
      const response = await fetch(`${API_BASE}/api/schedule/alternatives`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_ids: selectedPendingIds })
      });
      if (!response.ok) {
        throw new Error("Could not generate proposals.");
      }
      const payload = await response.json();
      setAlternatives(payload);
      setSelectedAlternative(payload[0] ?? null);
      setStatus(payload.length ? "Top schedule proposals are ready for Schedule Manager review." : "No feasible proposals were generated.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not generate proposals.");
    }
  }

  async function approveSelectedSchedule() {
    const tentativeIds = selectedScheduledIds.filter((requestId) => {
      const item = schedule.find((scheduledItem) => scheduledItem.request_id === requestId);
      return item && !isLockedStatus(item.status);
    });
    if (tentativeIds.length === 0) {
      setStatus("Select one or more tentative calendar tasks to approve.");
      return;
    }
    setStatus(`Approving ${tentativeIds.length} selected task${tentativeIds.length === 1 ? "" : "s"}...`);
    try {
      const response = await fetch(`${API_BASE}/api/schedule/approve-selected?role=${role}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_ids: tentativeIds })
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
          : payload.detail;
        throw new Error(detail || "Selected tasks could not be approved.");
      }
      setSelectedScheduledIds([]);
      await loadDashboard();
      setStatus(`${payload.locked_items ?? tentativeIds.length} selected task${tentativeIds.length === 1 ? "" : "s"} approved.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Selected tasks could not be approved.");
    }
  }

  async function loadBestProposalFor(requestId: string | null) {
    const response = await fetch(`${API_BASE}/api/schedule/alternatives`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_ids: selectedPendingIds.length ? selectedPendingIds : requestId ? [requestId] : [] })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Could not generate proposals.");
    }
    const proposals = payload as Alternative[];
    setAlternatives(proposals);
    const proposal = proposals.find(
      (alternative) => !alternative.conflicts.length && (!requestId || alternative.scheduled_work.some((item) => item.request_id === requestId))
    ) ?? proposals[0] ?? null;
    setSelectedAlternative(proposal);
    return proposal;
  }

  async function applyProposalOption(option: string) {
    const response = await fetch(`${API_BASE}/api/schedule/apply?option=${option}&role=${role}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_ids: selectedPendingIds })
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item: unknown) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ")
        : payload.detail;
      throw new Error(detail || "Proposal could not be applied.");
    }
    return payload as ScheduledWork[];
  }

  async function applySelectedAlternative() {
    if (!selectedAlternative) {
      setStatus("Select a proposal before applying it.");
      return;
    }
    if (selectedPendingIds.length === 0) {
      setStatus("Select the pending requests this proposal should apply before applying it.");
      return;
    }
    setStatus(`Applying ${selectedAlternative.label}...`);
    try {
      await applyProposalOption(selectedAlternative.option);
      setSelectedAlternative(null);
      setAlternatives([]);
      setSelectedPendingIds([]);
      await loadDashboard();
      setStatus(`${selectedAlternative.label} applied as the active schedule.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Proposal could not be applied.");
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
      setSelectedPendingIds((current) => current.filter((requestId) => requestId !== selectedRequestId));
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

  async function seedDemoData() {
    setStatus("Loading demo data...");
    try {
      const response = await fetch(`${API_BASE}/api/demo/seed`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Demo data could not be loaded.");
      }
      setSelectedAlternative(null);
      setAlternatives([]);
      setSelectedPendingIds([]);
      setSelectedScheduledIds([]);
      setSelectedRequestId(null);
      await loadDashboard();
      setStatus(
        `Demo data loaded: ${payload.requests} requests, ${payload.tentative_schedule_items ?? 0} tentative items, and ${payload.locked_schedule_items} locked items.`
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Demo data could not be loaded.");
    }
  }

  async function resetDemoData() {
    setStatus("Resetting demo data...");
    try {
      const response = await fetch(`${API_BASE}/api/demo/reset`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Demo data could not be reset.");
      }
      setSelectedAlternative(null);
      setAlternatives([]);
      setSelectedPendingIds([]);
      setSelectedScheduledIds([]);
      setSelectedRequestId(null);
      await loadDashboard();
      setStatus("Demo state reset.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Demo data could not be reset.");
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const visibleSchedule = selectedAlternative?.scheduled_work ?? schedule;
  const visibleConflicts = selectedAlternative?.conflicts ?? conflicts;
  const displayedKpis = selectedAlternative?.kpis ?? kpis;
  const scheduledIds = new Set(schedule.map((item) => item.request_id));
  const pendingRequests = requests.filter(
    (request) => request.approval_status === "draft" && !request.locked && !scheduledIds.has(request.request_id)
  );
  const selectedRequest = selectedRequestId ? requests.find((request) => request.request_id === selectedRequestId) ?? null : null;
  const selectedScheduledItem = selectedRequestId
    ? visibleSchedule.find((item) => item.request_id === selectedRequestId) ?? null
    : null;
  const days = monthDays(selectedDate);
  const todayItems = visibleSchedule
    .filter((item) => sameDay(new Date(item.start_time), selectedDate))
    .sort((left, right) => new Date(left.start_time).getTime() - new Date(right.start_time).getTime());
  const dayTracks = Array.from(new Set([...fallbackTracks, ...todayItems.map((item) => item.track_sector)])).sort();
  const calendarVars = {
    "--track-count": dayTracks.length,
    "--slot-count": engineeringHours.length - 1,
    "--slot-height": `${timeSlotHeight}px`
  } as CSSProperties;

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
  const selectedPendingRequests = pendingRequests.filter((request) => selectedPendingIds.includes(request.request_id));
  const selectedScheduledItems = schedule.filter((item) => selectedScheduledIds.includes(item.request_id));
  const selectedTentativeCount = selectedScheduledItems.filter((item) => !isLockedStatus(item.status)).length;
  const selectedLockedCount = selectedScheduledItems.filter((item) => isLockedStatus(item.status)).length;

  function dayItems(day: Date) {
    return visibleSchedule.filter((item) => sameDay(new Date(item.start_time), day));
  }

  function togglePendingSelection(requestId: string) {
    setSelectedRequestId(requestId);
    setSelectedScheduledIds([]);
    setSelectedAlternative(null);
    setAlternatives([]);
    setSelectedPendingIds((current) =>
      current.includes(requestId) ? current.filter((item) => item !== requestId) : [...current, requestId]
    );
  }

  function toggleScheduledSelection(requestId: string) {
    const activeItem = schedule.find((item) => item.request_id === requestId);
    if (!activeItem) {
      setStatus("Apply the selected proposal before approving proposed calendar items.");
      return;
    }
    setSelectedAlternative(null);
    setAlternatives([]);
    setSelectedRequestId(requestId);
    setSelectedPendingIds([]);
    setSelectedScheduledIds((current) =>
      current.includes(requestId) ? current.filter((item) => item !== requestId) : [...current, requestId]
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">RailFlowAI Planning Board</div>
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
          <button className="button secondary" onClick={seedDemoData}>
            <Database size={18} />
            Seed Demo
          </button>
          <button className="button secondary" onClick={resetDemoData}>
            <Trash2 size={18} />
            Reset
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
            <span className="legend"><i /> conflict</span>
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
                  aria-label={`${formatDate(day)}, ${items.length} scheduled item${items.length === 1 ? "" : "s"}${hasConflict ? ", has conflict" : ""}`}
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
            <div className="time-axis" style={calendarVars}>
              {engineeringHours.slice(0, -1).map((hour) => (
                <div className="time-tick" key={hour}>{hour}</div>
              ))}
            </div>
            <div className="calendar-grid" style={calendarVars}>
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
                          className={`calendar-event ${conflict ? "has-conflict" : ""} ${selectedScheduledIds.includes(item.request_id) ? "selected" : ""}`}
                          key={`${item.request_id}-${item.start_time}`}
                          onClick={() => toggleScheduledSelection(item.request_id)}
                          style={calendarBlockStyle(item)}
                        >
                          <strong>{item.request_id}</strong>
                          <span>{formatTime(item.start_time)}-{formatTime(item.end_time)}</span>
                          <span>{workLabel(request?.work_type ?? "work")}</span>
                          <span>{isLockedStatus(item.status) ? "Locked" : "Tentative"}</span>
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
        <div className="kpi danger"><span>Open Conflicts</span><strong>{displayedKpis.unresolved_conflicts}</strong></div>
        <div className="kpi"><span>Window Utilisation</span><strong>{displayedKpis.engineering_hours_utilisation}%</strong></div>
        <div className="kpi warning"><span>Estimated Overtime</span><strong>{displayedKpis.estimated_overtime_minutes}m</strong></div>
        <div className="kpi success"><span>Schedule Stability</span><strong>{displayedKpis.schedule_stability}%</strong></div>
      </section>

      <section className="ops-grid">
        <section className="panel">
          <div className="panel-header">
            <span>Request Queue</span>
            <small>{pendingRequests.length} pending</small>
          </div>
          <div className="panel-body request-list">
            {pendingRequests.length === 0 && <p className="muted">No pending requests. Approved work stays visible on the calendar.</p>}
            {pendingRequests.map((request) => (
              <button
                className={`request-item select-card ${selectedPendingIds.includes(request.request_id) ? "selected" : ""}`}
                key={request.request_id}
                onClick={() => togglePendingSelection(request.request_id)}
              >
                <strong>{request.request_id} / {request.title}</strong>
                <span>
                  {request.track_sector} / {workLabel(request.work_type)} / Priority {request.priority}
                </span>
                <span>{formatDateTime(request.earliest_start)}-{formatDateTime(request.deadline)}</span>
                <span className="badge neutral">Pending</span>
                {request.dependencies.length > 0 && (
                  <span className="dependency-line">
                    <GitBranch size={14} />
                    after {request.dependencies.join(", ")}
                  </span>
                )}
                {conflictsByRequest.has(request.request_id) && <span className="badge danger">Conflict</span>}
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
              <span className="eyebrow">Selection</span>
              <p>
                {selectedPendingIds.length} pending selected / {selectedTentativeCount} tentative selected / {selectedLockedCount} locked selected
              </p>
              {selectedPendingRequests.length === 0 && selectedScheduledItems.length === 0 && !selectedRequest && (
                <p>Select a request, calendar item, or proposal to inspect exactly what the actions apply to.</p>
              )}
              {selectedPendingRequests.length > 0 && (
                <div className="selected-list">
                  <strong>Pending requests</strong>
                  {selectedPendingRequests.map((request) => (
                    <p key={request.request_id}>
                      {request.request_id} / {request.title}: {formatDateTime(request.earliest_start)}-{formatDateTime(request.deadline)}
                    </p>
                  ))}
                </div>
              )}
              {selectedScheduledItems.length > 0 && (
                <div className="selected-list">
                  <strong>Calendar tasks</strong>
                  {selectedScheduledItems.map((item) => {
                    const request = requestFor(item, requests);
                    return (
                      <p key={item.request_id}>
                        {item.request_id} / {request?.title ?? "Scheduled work"}: {formatDateTime(item.start_time)}-{formatDateTime(item.end_time)} /{" "}
                        {isLockedStatus(item.status) ? "Locked" : "Tentative"}
                      </p>
                    );
                  })}
                </div>
              )}
              {selectedRequest && selectedPendingRequests.length === 0 && selectedScheduledItems.length === 0 && (
                <div className="selected-list">
                  <strong>{selectedRequest.request_id} / {selectedRequest.title}</strong>
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
                </div>
              )}
            </div>
            <div className="review-block">
              <span className="eyebrow">Review finding</span>
              <p>
                {selectedConflicts.length > 0
                  ? selectedConflicts[0].explanation
                  : "No active conflict is reported for the selected item."}
              </p>
              {selectedConflicts[0]?.suggested_action && <p>{selectedConflicts[0].suggested_action}</p>}
            </div>
            {selectedAlternative && (
              <div className="review-block">
                <span className="eyebrow">Selected proposal</span>
                <p>{selectedAlternative.label}: {selectedAlternative.explanation}</p>
                {selectedAlternative.impact_summary && <p>{selectedAlternative.impact_summary}</p>}
                {selectedAlternative.scheduled_work
                  .filter((item) => item.changed_from_original)
                  .map((item) => {
                    const request = requestFor(item, requests);
                    const current = scheduledFor(item.request_id, schedule);
                    return (
                      <p key={`${item.request_id}-${item.start_time}`}>
                        {item.request_id} / owner {request?.created_by ?? "field"}:{" "}
                        {current ? `${formatTime(current.start_time)}-${formatTime(current.end_time)} -> ` : "new slot "}
                        {formatTime(item.start_time)}-{formatTime(item.end_time)}
                      </p>
                    );
                  })}
              </div>
            )}
            {alternatives.length > 0 && (
              <div className="proposal-list" aria-label="Schedule proposals">
                <span className="eyebrow">Proposal options</span>
                {alternatives.map((alternative) => (
                  <button
                    className={`alternative ${selectedAlternative?.option === alternative.option ? "selected" : ""}`}
                    key={alternative.option}
                    onClick={() => {
                      setSelectedAlternative(alternative);
                      setStatus(`${alternative.label} selected for review.`);
                    }}
                  >
                    <strong>{alternative.label}</strong>
                    <span>{alternative.overall_score}/100 overall</span>
                    <span>{alternative.changed_jobs_count} moved / {alternative.moved_locked_count} locked moved</span>
                    <span>{alternative.conflicts.length} conflicts / {alternative.churn_penalty} churn penalty</span>
                  </button>
                ))}
              </div>
            )}
            <button className="button secondary" disabled={selectedPendingIds.length === 0} onClick={compareAlternatives}>
              <SlidersHorizontal size={18} />
              Show Proposals
            </button>
            {selectedAlternative && (
              <p>Selected proposal applies only to the selected pending request{selectedPendingIds.length === 1 ? "" : "s"}.</p>
            )}
            <button className="button" disabled={role !== "schedule_manager" || !selectedAlternative || selectedPendingIds.length === 0} onClick={applySelectedAlternative}>
              <ShieldCheck size={18} />
              Apply Proposal
            </button>
            <button className="button" disabled={role !== "schedule_manager" || selectedTentativeCount === 0} onClick={approveSelectedSchedule}>
              <ShieldCheck size={18} />
              Approve Selected
            </button>
            <button className="button secondary" disabled={role !== "schedule_manager" || !selectedScheduledItem} onClick={modifySelectedStart}>
              Modify
            </button>
            <button className="button secondary" disabled={role !== "schedule_manager" || !selectedRequestId} onClick={rejectSelectedRequest}>
              Reject
            </button>
          </div>
        </aside>
      </section>

    </main>
  );
}
