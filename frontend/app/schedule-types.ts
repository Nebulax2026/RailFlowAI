import type { EvidenceActivity, LocationUsage } from "./inspection";
export type Scenario = "A" | "B" | "C";
export const POLICIES = { A: "Strict supply", B: "Strict schedule", C: "Balanced" };
export const TABS = [{ id: "overview", label: "Overview" }, { id: "activities", label: "Activities" }, { id: "capacity", label: "Location & capacity" }, { id: "contracts", label: "Contract results" }, { id: "operations", label: "Operations" }] as const;
export type DetailTab = typeof TABS[number]["id"];
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled";
export type SolverConfig = { strategy?: string; initialization?: string; workers?: number | "auto"; time_limit_seconds?: number; seed?: number };
export type Diagnostics = { status?: string; strategy?: string; config?: SolverConfig; objective?: number | null; global_lower_bound?: number | null; absolute_gap?: number | null; time_to_first_feasible?: number | null; elapsed_seconds?: number; trajectory?: { seconds: number; objective: number }[] };
export type RunState = { status: Status; progress: number; message: string; error?: string | null; feasible?: boolean | null; objective_score?: number | null; diagnostics?: Diagnostics; phase: string; termination_reason?: string; solution_revision: number; solver_stats: { elapsed_seconds?: number; optimal?: boolean; relative_gap?: number }; scores?: Record<string, number> };
export type Job = {
  job_id: string; status: Status; source: string; expires_at: string; error?: string | null;
  algorithm: "legacy" | "scenario_a" | "strategies";
  solver_config: SolverConfig;
  instance: { lines: number; stations: number; sectors: number; locations: number; contracts: number; activities: number; total_accesses: number; horizon_start: string; horizon_weeks: number };
  scenarios: Partial<Record<Scenario, RunState>>;
};
export type ScenarioDetail = {
  scenario: Scenario; status: string;
  solution_revision: number; phase: string; termination_reason?: string;
  solver_stats: { optimal?: boolean; relative_gap?: number; elapsed_seconds?: number };
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
