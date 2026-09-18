"use client";

import { Download, LoaderCircle, Send, Wrench } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import type { LocationUsage } from "./inspection";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
type Scenario = "A" | "B" | "C";
type Status = "queued" | "running" | "completed" | "failed";
type Change = { activity_id: string; contract_number: string; before: { week: number; eclo: number; access_night: number }[]; after: { week: number; eclo: number; access_night: number }[]; reason: string };
type Replan = {
  replan_id: string; status: Status; message: string; error?: string | null;
  disruption: { location_id: string; start_week: number; end_week: number; capacity: number; reason: string };
  disruption_audit: { feasible?: boolean };
  diff: { summary?: { moved_activities: number; preserved_percent: number; contracts_impacted: number; score_delta: number; baseline_score: number; revised_score: number }; activity_changes?: Change[] };
  solution?: { validation: { feasible: boolean; soft_scores: Record<string, number> }; solver_stats: { churn_score?: number } };
};
type Answer = { answer: string; intent: string; evidence: string[]; mode: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(Array.isArray(payload.detail) ? payload.detail.join(" ") : payload.detail || `Request failed (${response.status}).`);
  return payload as T;
}

export function BonusTools({ jobId, scenario, runStatus, usage, hotspots, locations }: { jobId: string; scenario: Scenario; runStatus: string; usage: LocationUsage[]; hotspots: LocationUsage[]; locations: { location_id: string; capacity: number }[] }) {
  const suggested = hotspots[0] ?? usage[0];
  const [location, setLocation] = useState("");
  const [startWeek, setStartWeek] = useState(1);
  const [endWeek, setEndWeek] = useState(1);
  const [capacity, setCapacity] = useState(0);
  const [reason, setReason] = useState("urgent_maintenance");
  const [replan, setReplan] = useState<Replan | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<"baseline" | "revised">("baseline");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    if (!location && suggested) {
      setLocation(suggested.location_id); setStartWeek(suggested.week); setEndWeek(suggested.week);
      setCapacity(Math.max(0, suggested.capacity - 1));
    }
  }, [location, suggested]);
  const nominal = locations.find(item => item.location_id === location)?.capacity ?? 1;
  useEffect(() => { if (capacity >= nominal) setCapacity(Math.max(0, nominal - 1)); }, [capacity, nominal]);

  useEffect(() => {
    if (!replan || !["queued", "running"].includes(replan.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await request<Replan>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans/${replan.replan_id}`);
        setReplan(next); if (next.status === "completed") setView("revised");
      } catch (err) { setError(err instanceof Error ? err.message : "Could not refresh the re-plan."); }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [jobId, replan, scenario]);

  async function startReplan(event: FormEvent) {
    event.preventDefault(); setError(""); setAnswer(null);
    try {
      const next = await request<Replan>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ location_id: location, start_week: startWeek, end_week: endWeek, capacity, reason }),
      });
      setReplan(next); setView("baseline");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not start the re-plan."); }
  }

  async function ask(text = question) {
    if (!text.trim()) return;
    setAsking(true); setError(""); setQuestion(text);
    try {
      setAnswer(await request<Answer>(`/api/ps1/jobs/${jobId}/assistant/query`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario, replan_id: view === "revised" ? replan?.replan_id : null, question: text.trim() }),
      }));
    } catch (err) { setError(err instanceof Error ? err.message : "Schedule Assistant could not answer."); }
    finally { setAsking(false); }
  }

  const summary = replan?.diff.summary;
  return <div className="bonus-workspace">
    <section className="data-panel replan-panel">
      <div className="subheading"><h3>Disruption re-plan</h3><span>{replan?.status ?? "Ready"}</span></div>
      <form className="disruption-form" onSubmit={startReplan}>
        <label>Location<select value={location} onChange={event => setLocation(event.target.value)} required>{locations.map(item => <option key={item.location_id}>{item.location_id}</option>)}</select></label>
        <label>Start week<input type="number" min={1} value={startWeek} onChange={event => setStartWeek(Number(event.target.value))} /></label>
        <label>End week<input type="number" min={startWeek} value={endWeek} onChange={event => setEndWeek(Number(event.target.value))} /></label>
        <label>Emergency capacity<input type="number" min={0} max={Math.max(0, nominal - 1)} value={capacity} onChange={event => setCapacity(Number(event.target.value))} /></label>
        <label>Reason<select value={reason} onChange={event => setReason(event.target.value)}><option value="urgent_maintenance">Urgent maintenance</option><option value="defect">Infrastructure defect</option><option value="access_restriction">Access restriction</option><option value="other">Other</option></select></label>
        <button className="primary-button" disabled={runStatus !== "completed" || !location || replan?.status === "running" || replan?.status === "queued"}>{replan && ["running", "queued"].includes(replan.status) ? <LoaderCircle size={16} className="spin" /> : <Wrench size={16} />}Re-plan</button>
      </form>
      {error && <p className="inline-error">{error}</p>}
      {replan && <p className="muted">{replan.error || replan.message}</p>}
      {summary && <>
        <div className="segmented-control" role="group" aria-label="Schedule version"><button type="button" className={view === "baseline" ? "active" : ""} onClick={() => setView("baseline")}>Baseline</button><button type="button" className={view === "revised" ? "active" : ""} onClick={() => setView("revised")}>Revised</button></div>
        <div className="replan-metrics"><span><strong>{summary.moved_activities}</strong> moved activities</span><span><strong>{summary.preserved_percent}%</strong> preserved</span><span><strong>{summary.contracts_impacted}</strong> impacted contracts</span><span><strong>{summary.score_delta >= 0 ? "+" : ""}{summary.score_delta}</strong> score delta</span></div>
        <div className="table-wrap change-table"><table><thead><tr><th>Activity</th><th>Before</th><th>After</th><th>Reason</th></tr></thead><tbody>{(replan.diff.activity_changes ?? []).map(item => <tr key={item.activity_id}><td>{item.activity_id}</td><td>{item.before.map(row => `W${row.week}`).join(", ")}</td><td>{item.after.map(row => `W${row.week}`).join(", ")}</td><td>{item.reason.replaceAll("_", " ")}</td></tr>)}</tbody></table></div>
        {replan.status === "completed" && replan.disruption_audit.feasible && <div className="csv-links revised-downloads">{["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"].map(file => <a key={file} href={`${API_BASE}/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans/${replan.replan_id}/files/${file}`}><Download size={14} />{file.replace("SCHEDULE_", "").replace(".csv", "")}</a>)}</div>}
      </>}
    </section>

    <section className="data-panel assistant-panel">
      <div className="subheading"><h3>Schedule Assistant</h3><span>{answer?.mode ?? "Deterministic ready"}</span></div>
      <div className="query-suggestions">{["Why was A001 moved?", "What is the downstream delay risk?", `Capacity at ${location || "SEC:ALP:S01_S02:EB"} week ${startWeek}`, "Who co-shares with A001?", `Handover brief for week ${startWeek}`].map(item => <button type="button" key={item} onClick={() => void ask(item)}>{item}</button>)}</div>
      <form className="assistant-form" onSubmit={event => { event.preventDefault(); void ask(); }}><input value={question} maxLength={500} onChange={event => setQuestion(event.target.value)} placeholder="Ask about this schedule" /><button className="primary-button" disabled={asking || !question.trim()} aria-label="Ask Schedule Assistant">{asking ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}</button></form>
      {answer && <div className="assistant-answer"><p>{answer.answer}</p><small>{answer.intent} · Evidence: {answer.evidence.join(", ") || "schedule summary"}</small></div>}
    </section>
  </div>;
}
