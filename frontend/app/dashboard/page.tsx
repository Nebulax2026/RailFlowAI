"use client";

import Link from "next/link";
import { AlertTriangle, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Database, GitBranch, Plus, RefreshCw, ShieldCheck, SlidersHorizontal, Trash2, Upload } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

import ImportDialog from "./import-dialog";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const PLANNING_TIME_ZONE = "Asia/Singapore";

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

type SchedulingSettings = {
  urgent_lead_days: number;
};

type DashboardCatalog = {
  requester_accounts: string[];
};

type BlockedTimeSlot = {
  block_id: string;
  track_sectors: string[];
  start_time: string;
  end_time: string;
  reason: string;
  created_by: string;
  status: string;
  created_at: string;
};

type Notification = {
  notification_id: string;
  owner: string;
  type: string;
  message: string;
  request_ids: string[];
  block_id?: string | null;
  approval_id?: string | null;
  read: boolean;
  created_at: string;
};

type DisplacementApproval = {
  approval_id: string;
  urgent_request_id: string;
  displaced_request_id: string;
  owner: string;
  previous_start: string;
  previous_end: string;
  proposed_start: string;
  proposed_end: string;
  status: string;
  created_at: string;
};

type Role = "requester" | "schedule_manager";
type StatusTone = "loading" | "success" | "error" | "info";
const fallbackRequesterAccounts = ["field-ops", "signal-team", "track-team", "power-team", "safety-team"];

const emptyKpis: Kpis = {
  unresolved_conflicts: 0,
  critical_jobs_scheduled: 0,
  engineering_hours_utilisation: 0,
  estimated_overtime_minutes: 0,
  schedule_stability: 100,
  robustness_score: 100
};

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
const timeSlotHeight = 144;
const fallbackTracks = ["T08", "T09", "T10", "T11", "T12", "T13", "T14"];

function formatDate(value: Date) {
  return new Intl.DateTimeFormat("en", { timeZone: PLANNING_TIME_ZONE, month: "short", day: "numeric" }).format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", { timeZone: PLANNING_TIME_ZONE, hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", { timeZone: PLANNING_TIME_ZONE, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function workLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function singaporeDateKey(value: Date | string) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: PLANNING_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date(value));
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

function sameDay(left: Date, right: Date) {
  return singaporeDateKey(left) === singaporeDateKey(right);
}

function monthDays(anchor: Date) {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function defaultBoardDate(schedule: ScheduledWork[], requests: MaintenanceRequest[], current: Date) {
  const candidates = [
    ...schedule.map((item) => item.start_time),
    ...requests.map((request) => request.earliest_start)
  ]
    .map((value) => new Date(value))
    .filter((value) => !Number.isNaN(value.getTime()))
    .sort((left, right) => left.getTime() - right.getTime());

  if (candidates.length === 0) {
    return current;
  }

  const today = startOfDay(new Date());
  return candidates.find((candidate) => candidate >= today) ?? candidates[candidates.length - 1];
}

function requestFor(item: ScheduledWork, requests: MaintenanceRequest[]) {
  return requests.find((request) => request.request_id === item.request_id);
}

function scheduledFor(requestId: string, schedule: ScheduledWork[]) {
  return schedule.find((item) => item.request_id === requestId);
}

function minutesFromEngineeringStart(value: string) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: PLANNING_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(value));
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return Number(byType.hour) * 60 + Number(byType.minute);
}

function timelineHoursFor(items: ScheduledWork[]) {
  const baselineStart = 6;
  const baselineEnd = 22;
  const earliest = items.length ? Math.min(...items.map((item) => Math.floor(minutesFromEngineeringStart(item.start_time) / 60))) : baselineStart;
  const latest = items.length ? Math.max(...items.map((item) => Math.ceil(minutesFromEngineeringStart(item.end_time) / 60))) : baselineEnd;
  const start = Math.max(0, Math.min(baselineStart, earliest));
  const end = Math.min(24, Math.max(baselineEnd, latest));

  return Array.from({ length: Math.max(1, end - start) }, (_, index) => `${String(start + index).padStart(2, "0")}:00`);
}

function calendarBlockStyle(item: ScheduledWork, timelineStartMinutes: number) {
  const start = (minutesFromEngineeringStart(item.start_time) - timelineStartMinutes) * (timeSlotHeight / 60);
  const end = (minutesFromEngineeringStart(item.end_time) - timelineStartMinutes) * (timeSlotHeight / 60);
  return {
    top: `${Math.max(0, start)}px`,
    height: `${Math.max(60, end - start)}px`
  };
}

function shiftMonth(anchor: Date, direction: -1 | 1) {
  const next = new Date(anchor);
  const day = anchor.getDate();
  next.setDate(1);
  next.setMonth(next.getMonth() + direction);
  const lastDay = new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate();
  next.setDate(Math.min(day, lastDay));
  return next;
}

function isLockedStatus(status: string) {
  return status.toLowerCase() === "locked";
}

async function readResponsePayload(response: Response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function formatApiError(endpoint: string, payload: unknown) {
  const detail = typeof payload === "object" && payload && "detail" in payload ? (payload as { detail?: unknown }).detail : null;
  if (Array.isArray(detail)) {
    return detail.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).join(" ");
  }
  if (typeof detail === "string") {
    return detail;
  }
  return `${endpoint} failed.`;
}

async function fetchJson<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, init);
  const payload = await readResponsePayload(response);
  if (!response.ok) {
    throw new Error(`${endpoint}: ${formatApiError(endpoint, payload)}`);
  }
  return payload as T;
}

export default function DashboardPage() {
  const [role, setRole] = useState<Role>("requester");
  const [activeRequester, setActiveRequester] = useState(fallbackRequesterAccounts[0]);
  const [requesterAccounts, setRequesterAccounts] = useState(fallbackRequesterAccounts);
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
  const [settings, setSettings] = useState<SchedulingSettings>({ urgent_lead_days: 3 });
  const [urgentLeadDaysInput, setUrgentLeadDaysInput] = useState("3");
  const [blockedSlots, setBlockedSlots] = useState<BlockedTimeSlot[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [displacementApprovals, setDisplacementApprovals] = useState<DisplacementApproval[]>([]);
  const [blockTrack, setBlockTrack] = useState(fallbackTracks[0]);
  const [blockStart, setBlockStart] = useState("");
  const [blockEnd, setBlockEnd] = useState("");
  const [blockReason, setBlockReason] = useState("");
  const [status, setStatus] = useState("Loading planning board...");
  const [showImport, setShowImport] = useState(false);
  const [statusTone, setStatusTone] = useState<StatusTone>("loading");
  const [isLoading, setIsLoading] = useState(true);

  async function loadDashboard() {
    setIsLoading(true);
    setStatusTone("loading");
    setStatus("Loading planning board...");
    try {
      const ownerQuery = role === "requester" ? `?owner=${encodeURIComponent(activeRequester)}` : "";
      const approvalQuery = role === "requester" ? `?owner=${encodeURIComponent(activeRequester)}&status=pending` : "?status=pending";
      const [loadedRequests, loadedSchedule, loadedConflicts, loadedKpis, loadedSettings, loadedBlocks, loadedNotifications, loadedApprovals, loadedCatalog] = await Promise.all([
        fetchJson<MaintenanceRequest[]>("/api/requests"),
        fetchJson<ScheduledWork[]>("/api/schedule"),
        fetchJson<Conflict[]>("/api/conflicts/detect", { method: "POST" }),
        fetchJson<Kpis>("/api/kpis"),
        fetchJson<SchedulingSettings>("/api/settings/scheduling"),
        fetchJson<BlockedTimeSlot[]>("/api/schedule/blocks?active_only=true"),
        fetchJson<Notification[]>(`/api/notifications${ownerQuery}`),
        fetchJson<DisplacementApproval[]>(`/api/displacement-approvals${approvalQuery}`),
        fetchJson<DashboardCatalog>("/api/catalog")
      ]);

      setRequests(loadedRequests);
      setSchedule(loadedSchedule);
      setConflicts(loadedConflicts);
      setKpis(loadedKpis);
      setSettings(loadedSettings);
      setUrgentLeadDaysInput(String(loadedSettings.urgent_lead_days));
      setBlockedSlots(loadedBlocks);
      setNotifications(loadedNotifications);
      setDisplacementApprovals(loadedApprovals);
      setRequesterAccounts(loadedCatalog.requester_accounts.length ? loadedCatalog.requester_accounts : fallbackRequesterAccounts);
      if (loadedCatalog.requester_accounts.length && !loadedCatalog.requester_accounts.includes(activeRequester)) {
        setActiveRequester(loadedCatalog.requester_accounts[0]);
      }
      const scheduledIds = new Set(loadedSchedule.map((item) => item.request_id));
      const pendingRequests = loadedRequests.filter(
        (request) => request.approval_status === "draft" && !request.locked && !scheduledIds.has(request.request_id)
      );
      setSelectedRequestId((current) => current ?? pendingRequests[0]?.request_id ?? loadedSchedule[0]?.request_id ?? null);
      setSelectedDate((current) => {
        if ([...loadedSchedule.map((item) => item.start_time), ...loadedRequests.map((request) => request.earliest_start)].some((value) => sameDay(new Date(value), current))) {
          return current;
        }
        const next = defaultBoardDate(loadedSchedule, loadedRequests, current);
        return sameDay(current, next) ? current : next;
      });
      setStatusTone("success");
      setStatus("Planning board is synced with the backend.");
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Could not load planning board data.");
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshAfterImport(message: string) {
    await loadDashboard();
    setStatusTone("success");
    setStatus(message);
  }

  async function optimiseSchedule() {
    setStatusTone("loading");
    setStatus("Generating active feasible schedule...");
    try {
      await fetchJson<ScheduledWork[]>("/api/schedule/optimise?option=minimum_disruption", { method: "POST" });
      setSelectedAlternative(null);
      await loadDashboard();
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Could not generate schedule.");
    }
  }

  async function compareAlternatives() {
    if (selectedPendingIds.length === 0) {
      setStatus("Select one or more pending requests before showing proposals.");
      setStatusTone("info");
      return;
    }
    setStatusTone("loading");
    setStatus("Generating schedule proposals...");
    try {
      const payload = await fetchJson<Alternative[]>("/api/schedule/alternatives", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_ids: selectedPendingIds })
      });
      setAlternatives(payload);
      setSelectedAlternative(payload[0] ?? null);
      setStatusTone(payload.length ? "success" : "info");
      setStatus(payload.length ? "Top schedule proposals are ready for Schedule Manager review." : "No feasible proposals were generated.");
    } catch (error) {
      setStatusTone("error");
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
      setStatusTone("info");
      return;
    }
    setStatusTone("loading");
    setStatus(`Approving ${tentativeIds.length} selected task${tentativeIds.length === 1 ? "" : "s"}...`);
    try {
      const payload = await fetchJson<{ locked_items?: number }>(`/api/schedule/approve-selected?role=${role}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_ids: tentativeIds })
      });
      setSelectedScheduledIds([]);
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${payload.locked_items ?? tentativeIds.length} selected task${tentativeIds.length === 1 ? "" : "s"} approved.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Selected tasks could not be approved.");
    }
  }

  async function loadBestProposalFor(requestId: string | null) {
    const proposals = await fetchJson<Alternative[]>("/api/schedule/alternatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_ids: selectedPendingIds.length ? selectedPendingIds : requestId ? [requestId] : [] })
    });
    setAlternatives(proposals);
    const proposal = proposals.find(
      (alternative) => !alternative.conflicts.length && (!requestId || alternative.scheduled_work.some((item) => item.request_id === requestId))
    ) ?? proposals[0] ?? null;
    setSelectedAlternative(proposal);
    return proposal;
  }

  async function applyProposalOption(option: string) {
    return fetchJson<ScheduledWork[]>(`/api/schedule/apply?option=${option}&role=${role}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_ids: selectedPendingIds })
    });
  }

  async function applySelectedAlternative() {
    if (!selectedAlternative) {
      setStatus("Select a proposal before applying it.");
      setStatusTone("info");
      return;
    }
    if (selectedPendingIds.length === 0) {
      setStatus("Select the pending requests this proposal should apply before applying it.");
      setStatusTone("info");
      return;
    }
    setStatusTone("loading");
    setStatus(`Applying ${selectedAlternative.label}...`);
    try {
      await applyProposalOption(selectedAlternative.option);
      setSelectedAlternative(null);
      setAlternatives([]);
      setSelectedPendingIds([]);
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${selectedAlternative.label} applied as the active schedule.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Proposal could not be applied.");
    }
  }

  async function rejectSelectedRequest() {
    if (!selectedRequestId) {
      setStatus("Select a request before rejecting it.");
      setStatusTone("info");
      return;
    }
    setStatusTone("loading");
    setStatus(`Rejecting ${selectedRequestId}...`);
    try {
      await fetchJson(`/api/schedule/reject/${selectedRequestId}?role=${role}`, { method: "POST" });
      setSelectedAlternative(null);
      setSelectedPendingIds((current) => current.filter((requestId) => requestId !== selectedRequestId));
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${selectedRequestId} rejected and removed from the active schedule.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Request could not be rejected.");
    }
  }

  async function toggleSelectedLock() {
    if (!selectedRequestId || !selectedScheduledItem) {
      setStatus("Select scheduled work before changing its lock state.");
      setStatusTone("info");
      return;
    }
    const action = selectedScheduledItem.status === "locked" ? "unlock" : "lock";
    setStatusTone("loading");
    setStatus(`${action === "lock" ? "Locking" : "Unlocking"} ${selectedRequestId}...`);
    try {
      await fetchJson(`/api/schedule/${action}/${selectedRequestId}?role=${role}`, { method: "POST" });
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${selectedRequestId} is now ${action === "lock" ? "locked" : "unlocked"}.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Lock state could not be changed.");
    }
  }

  async function modifySelectedStart() {
    if (!selectedRequestId || !selectedScheduledItem || !selectedRequest) {
      setStatus("Select scheduled work before modifying it.");
      setStatusTone("info");
      return;
    }
    const current = selectedScheduledItem.start_time.slice(0, 16);
    const nextStart = window.prompt("New start time", current);
    if (!nextStart) {
      return;
    }
    const start = new Date(nextStart);
    const end = new Date(start.getTime() + selectedRequest.duration_minutes * 60_000);
    setStatusTone("loading");
    setStatus(`Modifying ${selectedRequestId}...`);
    try {
      const payload = await fetchJson<ScheduledWork>(`/api/schedule/modify/${selectedRequestId}?role=${role}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          changed_from_original: true,
          change_reason: "Modified by Schedule Manager during decision review."
        })
      });
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${selectedRequestId} moved to ${formatTime(payload.start_time)}.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Scheduled work could not be modified.");
    }
  }

  async function seedDemoData() {
    setStatusTone("loading");
    setStatus("Loading demo data...");
    try {
      const payload = await fetchJson<{ requests: number; tentative_schedule_items?: number; locked_schedule_items: number }>("/api/demo/seed", { method: "POST" });
      setSelectedAlternative(null);
      setAlternatives([]);
      setSelectedPendingIds([]);
      setSelectedScheduledIds([]);
      setSelectedRequestId(null);
      await loadDashboard();
      setStatusTone("success");
      setStatus(
        `Demo data loaded: ${payload.requests} requests, ${payload.tentative_schedule_items ?? 0} tentative items, and ${payload.locked_schedule_items} locked items.`
      );
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Demo data could not be loaded.");
    }
  }

  async function resetDemoData() {
    setStatusTone("loading");
    setStatus("Resetting demo data...");
    try {
      await fetchJson("/api/demo/reset", { method: "POST" });
      setSelectedAlternative(null);
      setAlternatives([]);
      setSelectedPendingIds([]);
      setSelectedScheduledIds([]);
      setSelectedRequestId(null);
      await loadDashboard();
      setStatusTone("success");
      setStatus("Demo state reset.");
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Demo data could not be reset.");
    }
  }

  async function updateUrgentLeadDays() {
    const nextValue = Number(urgentLeadDaysInput);
    if (!Number.isInteger(nextValue) || nextValue < 1) {
      setStatus("Urgent lead days must be a positive whole number.");
      setStatusTone("info");
      return;
    }
    setStatusTone("loading");
    setStatus("Updating scheduling settings...");
    try {
      const payload = await fetchJson<SchedulingSettings>(`/api/settings/scheduling?role=${role}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urgent_lead_days: nextValue })
      });
      setSettings(payload);
      setUrgentLeadDaysInput(String(payload.urgent_lead_days));
      setStatusTone("success");
      setStatus(`Urgent lead window set to ${payload.urgent_lead_days} day${payload.urgent_lead_days === 1 ? "" : "s"}.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Scheduling settings could not be updated.");
    }
  }

  async function createBlockedSlot() {
    if (!blockStart || !blockEnd || !blockReason.trim()) {
      setStatus("Choose a start, end, and reason before blocking track time.");
      setStatusTone("info");
      return;
    }
    setStatusTone("loading");
    setStatus(`Blocking ${blockTrack}...`);
    try {
      await fetchJson<BlockedTimeSlot>(`/api/schedule/blocks?role=${role}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          track_sectors: [blockTrack],
          start_time: new Date(blockStart).toISOString(),
          end_time: new Date(blockEnd).toISOString(),
          reason: blockReason.trim()
        })
      });
      setBlockReason("");
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${blockTrack} blocked for manager review.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Blocked slot could not be created.");
    }
  }

  async function cancelBlockedSlot(blockId: string) {
    setStatusTone("loading");
    setStatus(`Cancelling ${blockId}...`);
    try {
      await fetchJson<BlockedTimeSlot>(`/api/schedule/blocks/${blockId}?role=${role}`, { method: "DELETE" });
      await loadDashboard();
      setStatusTone("success");
      setStatus(`${blockId} cancelled.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Blocked slot could not be cancelled.");
    }
  }

  async function decideDisplacement(approval: DisplacementApproval, decision: "approve" | "reject") {
    setStatusTone("loading");
    setStatus(`${decision === "approve" ? "Approving" : "Rejecting"} displacement...`);
    try {
      await fetchJson<DisplacementApproval>(`/api/displacement-approvals/${approval.approval_id}/${decision}?owner=${encodeURIComponent(approval.owner)}`, { method: "POST" });
      await loadDashboard();
      setStatusTone("success");
      setStatus(`Displacement ${decision === "approve" ? "approved" : "rejected"}.`);
    } catch (error) {
      setStatusTone("error");
      setStatus(error instanceof Error ? error.message : "Displacement decision could not be saved.");
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, [activeRequester, role]);

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
  const visibleHours = timelineHoursFor(todayItems);
  const timelineStartMinutes = Number(visibleHours[0].slice(0, 2)) * 60;
  const dayTracks = Array.from(new Set([...fallbackTracks, ...todayItems.map((item) => item.track_sector)])).sort();
  const calendarVars = {
    "--track-count": dayTracks.length,
    "--slot-count": visibleHours.length,
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
  const urgencyCutoff = Date.now() + settings.urgent_lead_days * 24 * 60 * 60 * 1000;
  const urgentRequestIds = new Set(
    requests.filter((request) => new Date(request.deadline).getTime() <= urgencyCutoff).map((request) => request.request_id)
  );

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
          {role === "requester" && (
            <select className="role-select" value={activeRequester} onChange={(event) => setActiveRequester(event.target.value)} aria-label="Requester account">
              {requesterAccounts.map((account) => (
                <option key={account} value={account}>{account}</option>
              ))}
            </select>
          )}
          <Link className="secondary" href="/request/new">
            <Plus size={18} />
            New Request
          </Link>
          <button className="button secondary" onClick={() => setShowImport(true)}>
            <Upload size={18} />
            Import Data
          </button>
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

      <section className={`status-strip ${statusTone}`} role="status">
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
                {new Intl.DateTimeFormat("en", { timeZone: PLANNING_TIME_ZONE, month: "long", year: "numeric" }).format(selectedDate)}
              </h2>
            </div>
            <div className="month-actions">
              <span className="legend"><i /> conflict</span>
              <button className="icon-button" onClick={() => setSelectedDate((current) => shiftMonth(current, -1))} type="button" aria-label="Previous month">
                <ChevronLeft size={18} />
              </button>
              <button className="icon-button" onClick={() => setSelectedDate((current) => shiftMonth(current, 1))} type="button" aria-label="Next month">
                <ChevronRight size={18} />
              </button>
            </div>
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
              {visibleHours.map((hour) => (
                <div className="time-tick" key={hour}>{hour}</div>
              ))}
            </div>
            <div className="calendar-grid" style={calendarVars}>
              {dayTracks.map((track) => (
                <div className="track-column" key={track}>
                  {visibleHours.map((hour) => (
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
                          style={calendarBlockStyle(item, timelineStartMinutes)}
                        >
                          <strong>
                            <span>{item.request_id}</span>
                            <span className="event-status">{isLockedStatus(item.status) ? "Locked" : "Tentative"}</span>
                          </strong>
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
            {isLoading && (
              <>
                <div className="skeleton-line tall" />
                <div className="skeleton-line tall" />
              </>
            )}
            {!isLoading && pendingRequests.length === 0 && <p className="muted">No pending requests. Approved work stays visible on the calendar.</p>}
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
                {urgentRequestIds.has(request.request_id) && <span className="badge warning">Urgent</span>}
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
            <span>Manager Controls</span>
            <small>{settings.urgent_lead_days} day urgent window</small>
          </div>
          <div className="panel-body decision-stack">
            <div className="review-block">
              <span className="eyebrow">Urgency</span>
              <div className="compact-form">
                <input
                  min="1"
                  type="number"
                  value={urgentLeadDaysInput}
                  onChange={(event) => setUrgentLeadDaysInput(event.target.value)}
                  aria-label="Urgent lead days"
                />
                <button className="button secondary" disabled={role !== "schedule_manager"} onClick={updateUrgentLeadDays}>
                  Save
                </button>
              </div>
            </div>
            <div className="review-block">
              <span className="eyebrow">Block Track Time</span>
              <div className="compact-form vertical">
                <select value={blockTrack} onChange={(event) => setBlockTrack(event.target.value)}>
                  {dayTracks.map((track) => (
                    <option key={track} value={track}>{track}</option>
                  ))}
                </select>
                <input type="datetime-local" value={blockStart} onChange={(event) => setBlockStart(event.target.value)} aria-label="Block start" />
                <input type="datetime-local" value={blockEnd} onChange={(event) => setBlockEnd(event.target.value)} aria-label="Block end" />
                <input value={blockReason} onChange={(event) => setBlockReason(event.target.value)} placeholder="Reason" />
                <button className="button secondary" disabled={role !== "schedule_manager"} onClick={createBlockedSlot}>
                  Block Slot
                </button>
              </div>
            </div>
            <div className="review-block">
              <span className="eyebrow">Active Blocks</span>
              {blockedSlots.length === 0 && <p>No active manager blocks.</p>}
              {blockedSlots.map((slot) => (
                <p key={slot.block_id}>
                  {slot.track_sectors.join(", ")} / {formatDateTime(slot.start_time)}-{formatDateTime(slot.end_time)}
                  <button className="inline-action" disabled={role !== "schedule_manager"} onClick={() => cancelBlockedSlot(slot.block_id)}>
                    Cancel
                  </button>
                </p>
              ))}
            </div>
            <div className="review-block">
              <span className="eyebrow">In-App Alerts</span>
              {notifications.length === 0 && <p>No alerts yet.</p>}
              {notifications.slice(0, 4).map((notification) => (
                <p key={notification.notification_id}>
                  {notification.read ? "" : "[new] "}{notification.message}
                </p>
              ))}
            </div>
            <div className="review-block">
              <span className="eyebrow">Displacement Approvals</span>
              {displacementApprovals.length === 0 && <p>No pending displacement approvals.</p>}
              {displacementApprovals.map((approval) => (
                <div className="approval-row" key={approval.approval_id}>
                  <p>
                    {approval.urgent_request_id} needs {approval.displaced_request_id}:{" "}
                    {formatDateTime(approval.previous_start)}-{formatDateTime(approval.previous_end)} {"->"}{" "}
                    {formatDateTime(approval.proposed_start)}-{formatDateTime(approval.proposed_end)}
                  </p>
                  <button className="button secondary" onClick={() => decideDisplacement(approval, "approve")}>
                    Approve
                  </button>
                  <button className="button secondary" onClick={() => decideDisplacement(approval, "reject")}>
                    Reject
                  </button>
                </div>
              ))}
            </div>
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
            {isLoading && (
              <div className="selection-summary" aria-hidden="true">
                <span className="skeleton-line short" />
                <span className="skeleton-line" />
                <span className="skeleton-line" />
              </div>
            )}
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

      {showImport && (
        <ImportDialog
          apiBase={API_BASE}
          onClose={() => setShowImport(false)}
          onImported={refreshAfterImport}
        />
      )}

    </main>
  );
}
