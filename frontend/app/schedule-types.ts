import type { EvidenceActivity, LocationUsage } from "./inspection";

export type StandardScenario = "A" | "B" | "C";
export type PreventiveScenario = "D" | "E";
export type Scenario = StandardScenario;
export type AnyScenario = StandardScenario | PreventiveScenario;
export const POLICIES: Record<Scenario, string> = {
  A: "Strict supply",
  B: "Strict schedule",
  C: "Balanced"
};

export const TABS = [
  { id: "overview", label: "Overview & Metrics" },
  { id: "activities", label: "Activities" },
  { id: "locations", label: "Locations" },
  { id: "contracts", label: "Milestone & Risk" }
] as const;

export type DetailTab = typeof TABS[number]["id"];
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled";
export type SolverConfig = { strategy?: string; initialization?: string; workers?: number | "auto"; time_limit_seconds?: number; seed?: number };
export type Diagnostics = { status?: string; strategy?: string; config?: SolverConfig; objective?: number | null; global_lower_bound?: number | null; absolute_gap?: number | null; elapsed_seconds?: number; trajectory?: { seconds: number; objective: number }[] };
export type SolverStats = { elapsed_seconds?: number; optimal?: boolean; relative_gap?: number; search_workers?: number };
export type RunState = { status: Status; progress: number; message: string; error?: string | null; feasible?: boolean | null; objective_score?: number | null; diagnostics?: Diagnostics; phase: string; termination_reason?: string; solution_revision: number; solver_stats: SolverStats; scores?: Record<string, number> };

export type Job = {
  job_id: string; status: Status; source: string; expires_at: string; error?: string | null;
  job_kind: "standard" | "preventive";
  algorithm: "legacy" | "strategies" | "preventive_cp_sat";
  solver_config: SolverConfig;
  instance: { lines: number; stations: number; sectors: number; locations: number; contracts: number; activities: number; total_accesses: number; horizon_start: string; horizon_weeks: number };
  scenarios: Partial<Record<AnyScenario, RunState>>;
};
export type ContractResult = { contract_number: string; simulated_completion_date: string; overrun_days: number };
export type ReplanState = {
  replan_id: string; scenario: Scenario; status: Status; message: string; error?: string | null;
  phase: string; progress: number; elapsed_seconds?: number | null; budget_seconds?: number | null;
  disruption: { location_id: string; start_week: number; end_week: number; capacity: number; reason: string };
  disruption_audit?: { feasible?: boolean };
  diff: {
    summary?: {
      moved_activities: number;
      preserved_percent: number;
      score_delta: number;
      contracts_impacted?: number;
      baseline_score?: number;
      revised_score?: number;
      overrun_delta?: number;
      baseline_overrun?: number;
      revised_overrun?: number;
      eclo_delta?: number;
      baseline_eclo?: number;
      revised_eclo?: number;
      excess_delta?: number;
      baseline_excess?: number;
      revised_excess?: number;
      accesses_delta?: number;
      baseline_accesses?: number;
      revised_accesses?: number;
    };
    activity_changes?: { activity_id: string; contract_number: string; before: { week: number; eclo: number; access_night: number }[]; after: { week: number; eclo: number; access_night: number }[]; reason: string }[];
    contract_changes?: { contract_number: string; before_completion: string; after_completion: string; before_overrun: number; after_overrun: number; overrun_delta: number }[];
  };
  solution?: {
    validation: {
      feasible: boolean;
      detail: {
        safety_status?: string;
        eclo_nights?: number;
        location_usage?: LocationUsage[];
        capacity_hotspots?: LocationUsage[];
        nights_scheduled?: number;
      };
      soft_scores: {
        objective_score?: number;
        completion_percent?: number;
        overrun_days_total?: number;
        excess_access_nights_total?: number;
        eclo_nights_total?: number;
        delay?: number;
        excess_supply?: number;
        eclo?: number;
      };
      hard_violations?: { rule: string; severity: string; detail: string }[];
    };
    results: { scenario: string; contract_number: string; simulated_completion_date: string; overrun_days: number }[];
    accesses?: { activity_id: string; week: number; eclo: number; access_night: number }[];
    occupancy?: { activity_id: string; week: number; location_id: string; co_share_group: string }[];
    activity_details?: EvidenceActivity[];
    score_breakdown?: { delay: number; excess_supply: number; eclo: number };
    solver_stats?: SolverStats;
  };
};
export type ScenarioDetail = {
  scenario: Scenario; status: string;
  solution_revision: number; phase: string; termination_reason?: string;
  solver_stats: SolverStats;
  score_breakdown: { delay: number; excess_supply: number; eclo: number };
  activity_details: EvidenceActivity[];
  locations: { location_id: string; capacity: number }[];
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

export type MaintenanceAssignment = {
  occurrence_id: string; rule_id: string; location_id: string;
  planned_date: string; actual_date: string; start_time: string; end_time: string;
  deferral_days: number; deferred: boolean; conflict_driven: boolean;
};

export type PreventiveDetail = {
  scenario: PreventiveScenario; job_kind: "preventive"; status: Status;
  solution_revision: number; phase: string; termination_reason?: string;
  solver_stats: SolverStats & { objective_hierarchy?: { name: string; value: number; optimal: boolean }[] };
  validation: {
    feasible: boolean;
    hard_violations: { rule: string; severity: string; detail: string }[];
    soft_scores: Record<string, number | string>;
    detail: { safety_status?: string; experimental?: boolean };
  };
  project_results: ContractResult[];
  project_accesses: { activity_id: string; access_seq: number; week: number; physical_day: number; access_date: string; start_time: string; end_time: string }[];
  maintenance: MaintenanceAssignment[];
  downloads: string[];
};

export type TradeoffMetric = { D: number | null; E: number | null; delta_E_minus_D: number | null };
export type PreventiveTradeoff = {
  title: string;
  metrics: Record<string, TradeoffMetric>;
  project_schedule_impact: string;
  preventive_maintenance_impact: string;
  summary: string;
  optimality_proved: { D: boolean; E: boolean };
  schedule_difference_summary: { project_accesses_changed: number; maintenance_occurrences_changed: number };
  project_schedule_differences: {
    activity_id: string; access_seq: number;
    D: { week: number; physical_day: number; access_date: string };
    E: { week: number; physical_day: number; access_date: string };
    moved_days_E_minus_D: number;
  }[];
  maintenance_schedule_differences: {
    occurrence_id: string; location_id: string; planned_date: string;
    D: { actual_date: string; deferral_days: number };
    E: { actual_date: string; deferral_days: number };
    moved_days_E_minus_D: number;
  }[];
};

export function formatLocationName(locId: string): { primary: string; secondary: string; isHub: boolean; typeTag: string } {
  if (!locId) return { primary: "Unknown Location", secondary: locId, isHub: false, typeTag: "Track" };
  const parts = locId.split(":");
  if (parts.length >= 3) {
    const isPlatform = parts[0] === "PLAT" || parts[0] === "STN";
    const isTunnel = parts[0] === "SEC";
    const kind = isTunnel ? "Tunnel Sector" : isPlatform ? "Platform Sector" : parts[0];
    const typeTag = isTunnel ? "Tunnel" : isPlatform ? "Platform" : "Track";
    const line = parts[1] === "ALP" ? "Alpha Line" : parts[1] === "BET" ? "Beta Line" : parts[1];
    const section = parts[2].replace("_", " ↔ ");
    const isHub = parts[2].includes("H01") || parts[2].includes("H02");
    const bound = parts[3] ? (parts[3] === "EB" ? "Eastbound" : parts[3] === "WB" ? "Westbound" : parts[3]) : "";
    const primary = `${line}${bound ? ` (${bound})` : ""} · ${section}`;
    const secondary = `${kind} · ${locId}`;
    return { primary, secondary, isHub, typeTag };
  }
  return { primary: locId, secondary: locId, isHub: false, typeTag: "Track" };
}
