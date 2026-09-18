"use client";

import { Download, LoaderCircle, Send, Sparkles, Wrench } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import type { LocationUsage } from "./inspection";
import { formatLocationName, type Scenario } from "./schedule-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
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

export function AIAssistantPanel({
  jobId,
  scenario,
  runStatus,
  usage,
  hotspots,
  locations
}: {
  jobId: string;
  scenario: Scenario;
  runStatus: string;
  usage: LocationUsage[];
  hotspots: LocationUsage[];
  locations: { location_id: string; capacity: number }[];
}) {
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
  const [assistantError, setAssistantError] = useState("");
  const [conversation, setConversation] = useState<{ question: string; answer: Answer }[]>([]);
  const [starting, setStarting] = useState(false);
  const startingRef = useRef(false);
  const askingRef = useRef(false);
  const [mode, setMode] = useState<"chat" | "replan">("chat");

  useEffect(() => {
    if (!location && suggested) {
      setLocation(suggested.location_id);
      setStartWeek(suggested.week);
      setEndWeek(suggested.week);
      setCapacity(Math.max(0, suggested.capacity - 1));
    }
  }, [location, suggested]);

  const nominal = locations.find((item) => item.location_id === location)?.capacity ?? 1;
  useEffect(() => {
    if (capacity >= nominal) setCapacity(Math.max(0, nominal - 1));
  }, [capacity, nominal]);

  useEffect(() => {
    if (!replan || !["queued", "running"].includes(replan.status)) return;
    const replanId = replan.replan_id;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request<Replan>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans/${replanId}`);
        if (disposed) return;
        setReplan(next);
        if (next.status === "completed") setView("revised");
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : "Could not refresh re-plan.");
          timer = setTimeout(poll, 1500);
        }
      }
    }
    timer = setTimeout(poll, 1500);
    return () => { disposed = true; clearTimeout(timer); };
  }, [jobId, replan, scenario]);

  async function startReplan(event: FormEvent) {
    event.preventDefault();
    if (startingRef.current || runStatus !== "completed" || (replan && ["queued", "running"].includes(replan.status))) return;
    startingRef.current = true;
    setStarting(true);
    setError("");
    try {
      const next = await request<Replan>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ location_id: location, start_week: startWeek, end_week: endWeek, capacity, reason }),
      });
      setReplan(next);
      setView("baseline");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start re-plan.");
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }

  async function ask(text = question) {
    if (!text.trim() || askingRef.current) return;
    askingRef.current = true;
    setAsking(true);
    setAssistantError("");
    setQuestion(text);
    try {
      const next = await request<Answer>(`/api/ps1/jobs/${jobId}/assistant/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario, replan_id: view === "revised" ? replan?.replan_id : null, question: text.trim() }),
      });
      setAnswer(next);
      setConversation((current) => [...current, { question: text.trim(), answer: next }]);
    } catch (err) {
      setAssistantError(err instanceof Error ? err.message : "Schedule Assistant could not answer.");
    } finally {
      setAsking(false);
      askingRef.current = false;
    }
  }

  const summary = replan?.diff.summary;

  return (
    <aside className="permanent-ai-sidebar" aria-label="AI Schedule Assistant">
      <div className="ai-sidebar-header">
        <h3>
          <Sparkles size={16} color="var(--cyan)" />
          RailFlow AI Assistant
        </h3>
        <div className="segmented-control" role="group">
          <button
            type="button"
            className={`secondary-button ${mode === "chat" ? "primary-button" : ""}`}
            style={{ fontSize: "11px", padding: "3px 8px" }}
            onClick={() => setMode("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            className={`secondary-button ${mode === "replan" ? "primary-button" : ""}`}
            style={{ fontSize: "11px", padding: "3px 8px" }}
            onClick={() => setMode("replan")}
          >
            Re-plan
          </button>
        </div>
      </div>

      <div className="ai-sidebar-body">
        {mode === "chat" ? (
          <>
            <div className="query-suggestions">
              {[
                "Why was A001 moved?",
                "What is the downstream delay risk?",
                `Capacity at ${location || "SEC:ALP:S01_S02:EB"} week ${startWeek}`,
                `Handover brief for week ${startWeek}`
              ].map((item) => (
                <button type="button" key={item} onClick={() => void ask(item)}>
                  {item}
                </button>
              ))}
            </div>

            <form
              className="assistant-form"
              onSubmit={(e) => { e.preventDefault(); void ask(); }}
            >
              <input
                value={question}
                maxLength={500}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask schedule assistant..."
              />
              <button
                className="primary-button"
                disabled={asking || !question.trim()}
                aria-label="Send query"
                style={{ padding: "6px 10px" }}
              >
                {asking ? <LoaderCircle size={14} className="spin" /> : <Send size={14} />}
              </button>
            </form>

            {assistantError && <p className="alert error">{assistantError}</p>}

            <div className="assistant-conversation" role="log">
              {conversation.map((entry, idx) => (
                <div className="assistant-answer" key={idx}>
                  <strong>Q: {entry.question}</strong>
                  <p>{entry.answer.answer}</p>
                  <small>{entry.answer.intent} · Evidence: {entry.answer.evidence.join(", ") || "Summary"}</small>
                </div>
              ))}
              {!conversation.length && (
                <div style={{ textAlign: "center", padding: "24px 8px", color: "var(--text-dim)", fontSize: "11px" }}>
                  Operational Q&A ready. Select a suggested prompt or type an inquiry.
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <span className="muted" style={{ fontSize: "11px" }}>
              Simulate mid-horizon disruption & emergency quota drops.
            </span>

            <form className="disruption-form" onSubmit={startReplan}>
              <label>
                Disrupted Location
                <select value={location} onChange={(e) => setLocation(e.target.value)} required>
                  {locations.map((item) => (
                    <option key={item.location_id} value={item.location_id}>
                      {formatLocationName(item.location_id).primary}
                    </option>
                  ))}
                </select>
              </label>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <label>
                  Start Week
                  <input type="number" min={1} value={startWeek} onChange={(e) => setStartWeek(Number(e.target.value))} />
                </label>
                <label>
                  End Week
                  <input type="number" min={startWeek} value={endWeek} onChange={(e) => setEndWeek(Number(e.target.value))} />
                </label>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <label>
                  Quota Limit
                  <input type="number" min={0} max={Math.max(0, nominal - 1)} value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} />
                </label>
                <label>
                  Reason
                  <select value={reason} onChange={(e) => setReason(e.target.value)}>
                    <option value="urgent_maintenance">Urgent Maintenance</option>
                    <option value="defect">Track Defect</option>
                    <option value="access_restriction">Access Restriction</option>
                  </select>
                </label>
              </div>

              <button
                className="primary-button"
                disabled={starting || runStatus !== "completed" || !location || replan?.status === "running" || replan?.status === "queued"}
              >
                {starting || (replan && ["running", "queued"].includes(replan.status)) ? (
                  <LoaderCircle size={14} className="spin" />
                ) : (
                  <Wrench size={14} />
                )}
                Run Re-plan
              </button>
            </form>

            {error && <p className="alert error">{error}</p>}

            {summary && (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "8px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "6px" }}>
                  <div className="detail-field"><span>Moved</span><strong>{summary.moved_activities}</strong></div>
                  <div className="detail-field"><span>Preserved</span><strong>{summary.preserved_percent}%</strong></div>
                  <div className="detail-field"><span>Delta</span><strong>{summary.score_delta >= 0 ? `+${summary.score_delta}` : summary.score_delta}</strong></div>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Activity</th><th>Old</th><th>New</th></tr></thead>
                    <tbody>
                      {(replan?.diff.activity_changes ?? []).slice(0, 5).map((ch) => (
                        <tr key={ch.activity_id}>
                          <td><strong>{ch.activity_id}</strong></td>
                          <td>{ch.before.map((b) => `W${b.week}`).join(", ")}</td>
                          <td>{ch.after.map((a) => `W${a.week}`).join(", ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

// Backward compatibility
export const AIAssistantDrawer = AIAssistantPanel;
export const BonusTools = AIAssistantPanel;
