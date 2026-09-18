"use client";

import { Download, LoaderCircle, Send, Sparkles, Wrench } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { LocationUsage } from "./inspection";
import {
  formatLocationName,
  type ContractResult,
  type ReplanState,
  type Scenario,
  type Status,
} from "./schedule-types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type Answer = {
  answer: string;
  intent: string;
  evidence: string[];
  mode: string;
  data?: Record<string, unknown>;
  approved_preview_id?: string;
};

type Entry = {
  id: number;
  question: string;
  answer?: Answer;
  error?: string;
};

type Preview = {
  preview_id: string;
  scenario: Scenario;
  nominal_capacity: number;
  note: string;
  disruption: {
    location_id: string;
    start_week: number;
    end_week: number;
    capacity: number;
    reason: string;
  };
};

export type ResultSummary = {
  objectiveScore?: number;
  overrunDays?: number;
  excessAccess?: number;
  ecloNights?: number;
  contracts: ContractResult[];
};

type Change = {
  activity_id: string;
  contract_number: string;
  before: { week: number; eclo: number; access_night: number }[];
  after: { week: number; eclo: number; access_night: number }[];
  reason: string;
};

type LegacyReplan = {
  replan_id: string;
  status: Status;
  message: string;
  error?: string | null;
  disruption: {
    location_id: string;
    start_week: number;
    end_week: number;
    capacity: number;
    reason: string;
  };
  disruption_audit: { feasible?: boolean };
  diff: {
    summary?: {
      moved_activities: number;
      preserved_percent: number;
      contracts_impacted: number;
      score_delta: number;
      baseline_score: number;
      revised_score: number;
    };
    activity_changes?: Change[];
  };
  solution?: {
    validation: { feasible: boolean; soft_scores: Record<string, number> };
    solver_stats: { churn_score?: number };
  };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status}).`);
  return payload as T;
}

function AnswerBody({ text }: { text: string }) {
  return (
    <div className="agent-markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{ a: (props: any) => <a {...props} target="_blank" rel="noreferrer noopener" /> }}
      >
        {text}
      </Markdown>
    </div>
  );
}

function EvidenceCard({ answer }: { answer: Answer }) {
  if (answer.intent === "scenario_comparison" && Array.isArray(answer.data?.scenarios)) {
    const rows = answer.data.scenarios as { scenario: string; objective_score: number; overrun_days: number }[];
    return (
      <div className="agent-evidence">
        <strong>Scenario comparison</strong>
        {rows.map((row) => (
          <span key={row.scenario}>
            Scenario {row.scenario} · {row.overrun_days}d overrun · score {row.objective_score}
          </span>
        ))}
      </div>
    );
  }
  if (answer.intent === "score_explanation" && answer.data?.largest_driver) {
    return (
      <div className="agent-evidence">
        <strong>Score evidence</strong>
        <span>Largest driver: {String((answer.data.largest_driver as { component?: string }).component)}</span>
        <span>Total overrun: {String(answer.data.total_overrun_days)} days</span>
      </div>
    );
  }
  return null;
}

/**
 * Full AI Copilot & Scenario Briefing component
 */
export function BonusTools({
  jobId,
  scenario,
  runStatus,
  usage,
  hotspots,
  summary,
  initialAgentMode = false,
  onReplanChange,
}: {
  jobId: string;
  scenario: Scenario;
  runStatus: string;
  usage: LocationUsage[];
  hotspots: LocationUsage[];
  summary: ResultSummary;
  initialAgentMode?: boolean;
  onReplanChange?: (replan: ReplanState | null) => void;
}) {
  const suggested = hotspots[0] ?? usage[0];
  const [agentMode, setAgentMode] = useState(initialAgentMode);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [conversation, setConversation] = useState<Entry[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [replan, setReplan] = useState<ReplanState | null>(null);
  const [executing, setExecuting] = useState(false);
  const askingRef = useRef(false);
  const executingRef = useRef(false);
  const introduced = useRef(false);
  const mounted = useRef(true);
  const nextEntryId = useRef(0);
  const log = useRef<HTMLDivElement>(null);
  const notifyReplan = useRef(onReplanChange);
  notifyReplan.current = onReplanChange;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    notifyReplan.current?.(replan);
  }, [replan]);

  useEffect(() => () => notifyReplan.current?.(null), []);

  useEffect(() => {
    if (!agentMode || introduced.current) return;
    introduced.current = true;
    void ask(
      "Read the validated results for all available scenarios and briefly compare their scores, delays and key risks in English. Explain what I can ask and how to approve a reviewed replan preview in chat. Do not execute any changes.",
      true
    );
  });

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [conversation, asking, preview]);

  useEffect(() => {
    if (!replan || !["queued", "running"].includes(replan.status)) return;
    const timer = window.setInterval(
      () =>
        void request<ReplanState>(
          `/api/ps1/jobs/${jobId}/scenarios/${replan.scenario}/replans/${replan.replan_id}`
        )
          .then(setReplan)
          .catch(() => {}),
      1200
    );
    return () => window.clearInterval(timer);
  }, [jobId, replan]);

  function amend(id: number, patch: Partial<Entry>) {
    if (mounted.current) {
      setConversation((current) =>
        current.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry))
      );
    }
  }

  async function ask(text = question, introduction = false) {
    const prompt = text.trim();
    if (!prompt || askingRef.current || executingRef.current) return;
    askingRef.current = true;
    setAsking(true);
    setError("");

    const history = conversation
      .slice(-6)
      .filter((entry) => entry.answer)
      .flatMap((entry) => [
        ...(entry.question ? [{ role: "user", content: entry.question }] : []),
        { role: "assistant", content: entry.answer!.answer.slice(0, 12000) },
      ]);
    const id = nextEntryId.current++;
    const appendSentMessage = () => {
      setConversation((current) => [...current, { id, question: introduction ? "" : prompt }]);
      if (!introduction) setQuestion("");
    };

    if (introduction) appendSentMessage();
    else flushSync(appendSentMessage);

    try {
      const next = await request<Answer>(`/api/ps1/jobs/${jobId}/assistant/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pending_preview_id: preview?.preview_id, question: prompt, history }),
      });
      if (!mounted.current) return;
      setAnswer(next);
      amend(id, { answer: next });

      if (next.intent === "disruption_preview" && next.data?.valid === true) {
        setPreview(null);
        const target = next.data.scenario;
        if (target !== "A" && target !== "B" && target !== "C") {
          throw new Error("The Copilot must specify A, B, or C for a replan draft.");
        }
        setPreview(
          await request<Preview>(`/api/ps1/jobs/${jobId}/scenarios/${target}/replans/preview`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(next.data),
          })
        );
      } else if (
        !introduction &&
        next.approved_preview_id &&
        next.approved_preview_id === preview?.preview_id
      ) {
        await executePreview();
      }
    } catch (err) {
      amend(id, { error: err instanceof Error ? err.message : "Copilot could not answer." });
    } finally {
      askingRef.current = false;
      setAsking(false);
    }
  }

  async function executePreview() {
    if (!preview || executingRef.current || !mounted.current) return;
    executingRef.current = true;
    setExecuting(true);
    try {
      const started = await request<ReplanState>(
        `/api/ps1/jobs/${jobId}/scenarios/${preview.scenario}/replans/execute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preview_id: preview.preview_id }),
        }
      );
      setReplan(started);
      setPreview(null);
      setConversation((current) => [
        ...current,
        {
          id: nextEntryId.current++,
          question: "",
          answer: {
            answer:
              "Your replan request has been accepted. The solver and independent validation are pending; the revised schedule is not yet validated. Progress is shown in the policy comparison panel.",
            intent: "replan_started",
            mode: "system",
            evidence: [started.replan_id],
          },
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the re-plan.");
    } finally {
      executingRef.current = false;
      setExecuting(false);
    }
  }

  const quick = [
    "Compare scenarios A, B and C",
    "What is driving Scenario A's score?",
    "What is the milestone risk for C001 in Scenario A?",
    suggested
      ? `Prepare a Scenario A capacity reduction at ${suggested.location_id} to 0 in week ${suggested.week}`
      : "What changed in the latest replan?",
  ];

  if (!agentMode) {
    return (
      <section className="agent-mode-entry data-panel">
        <div>
          <span className="eyebrow">Operations workspace</span>
          <h3>Need a guided decision view?</h3>
          <p>Open AI Agent Mode for a concise scenario briefing alongside a Gemini-assisted planning conversation.</p>
        </div>
        <button className="primary-button" onClick={() => setAgentMode(true)}>
          <Sparkles size={16} />
          AI Agent Mode
        </button>
      </section>
    );
  }

  const completedReplan =
    replan &&
    replan.status === "completed" &&
    replan.disruption_audit?.feasible &&
    replan.solution?.validation.feasible &&
    replan.solution.validation.detail.safety_status === "verified"
      ? replan
      : null;
  const briefing = completedReplan
    ? {
        objectiveScore: completedReplan.solution!.validation.soft_scores.objective_score,
        overrunDays: completedReplan.solution!.validation.soft_scores.overrun_days_total,
        excessAccess: completedReplan.solution!.validation.soft_scores.excess_access_nights_total,
        ecloNights: completedReplan.solution!.validation.soft_scores.eclo_nights_total,
        contracts: completedReplan.solution!.results,
      }
    : summary;
  const briefingScenario = completedReplan?.scenario ?? scenario;
  const replanSummary = completedReplan?.diff.summary;

  return (
    <section className="agent-mode-workspace" aria-label="AI Agent Mode">
      <header className="agent-mode-toolbar">
        <div>
          <span className="eyebrow">AI Agent Mode · All scenarios</span>
          <h3>Decision briefing and Copilot</h3>
        </div>
        <button className="secondary-button" onClick={() => setAgentMode(false)}>
          Exit Agent Mode
        </button>
      </header>
      <div className="agent-mode-grid">
        <section className="agent-briefing data-panel" aria-label="Scenario result summary">
          <div className="subheading">
            <h3>{completedReplan ? `Validated Scenario ${briefingScenario} re-plan` : `Scenario ${briefingScenario} summary`}</h3>
            <span>{completedReplan ? "validated" : runStatus}</span>
          </div>
          <div className="agent-summary-metrics">
            <span>
              <small>Objective score</small>
              <strong>{briefing.objectiveScore ?? "—"}</strong>
            </span>
            <span>
              <small>Overrun days</small>
              <strong>{briefing.overrunDays ?? "—"}</strong>
            </span>
            <span>
              <small>Excess access</small>
              <strong>{briefing.excessAccess ?? "—"}</strong>
            </span>
            <span>
              <small>ECLO nights</small>
              <strong>{briefing.ecloNights ?? "—"}</strong>
            </span>
          </div>
          <h4>{completedReplan ? "Revised contract outcome" : "Contract outcome"}</h4>
          <div className="agent-contract-list">
            {briefing.contracts.map((contract) => (
              <div key={contract.contract_number}>
                <strong>{contract.contract_number}</strong>
                <span>{contract.simulated_completion_date}</span>
                <em className={contract.overrun_days ? "late" : "on-time"}>
                  {contract.overrun_days ? `${contract.overrun_days}d overrun` : "On plan"}
                </em>
              </div>
            ))}
          </div>
          {replanSummary && (
            <section className="agent-replan-result">
              <strong>Re-plan effect</strong>
              <p>
                {replanSummary.moved_activities} activities moved · {replanSummary.preserved_percent}% preserved · score delta{" "}
                {replanSummary.score_delta >= 0 ? "+" : ""}
                {replanSummary.score_delta}
              </p>
            </section>
          )}
          <p className="muted">
            Ask the Copilot to explain score drivers, milestone risk, co-sharing, capacity, or prepare a validated disruption re-plan.
          </p>
        </section>
        <section className="agent-chat" aria-label="PS1 Schedule Copilot">
          <header className="agent-chat-header">
            <div>
              <span className="eyebrow">RailFlowAI · A/B/C</span>
              <h2>PS1 Schedule Copilot</h2>
            </div>
            <span className="agent-live">{answer?.mode ?? "Gemini ready"}</span>
          </header>
          <div className="agent-suggestions">
            {quick.map((item) => (
              <button type="button" key={item} onClick={() => void ask(item)}>
                {item}
              </button>
            ))}
          </div>
          <div className="agent-messages" role="log" ref={log}>
            {conversation.map((entry) => (
              <div key={entry.id}>
                {entry.question && (
                  <div className="agent-message user">
                    <span className="agent-message-role">You</span>
                    <p>{entry.question}</p>
                  </div>
                )}
                {entry.answer && (
                  <div className="agent-message assistant">
                    <span className="agent-message-role">Copilot</span>
                    <AnswerBody text={entry.answer.answer} />
                    <EvidenceCard answer={entry.answer} />
                    {entry.answer.evidence.length > 0 && (
                      <small>Evidence: {entry.answer.evidence.join(", ")}</small>
                    )}
                  </div>
                )}
                {entry.error && (
                  <div className="agent-message assistant failed">
                    <span className="agent-message-role">Copilot</span>
                    <p>{entry.error}</p>
                  </div>
                )}
              </div>
            ))}
            {preview && (
              <section className="copilot-preview">
                <strong>Scenario {preview.scenario} draft re-plan preview</strong>
                <p>{preview.note}</p>
                <p>After reviewing the preview, you can also approve it in chat by saying “Approve” or “Run it”.</p>
                <dl>
                  <div>
                    <dt>Location</dt>
                    <dd>{preview.disruption.location_id}</dd>
                  </div>
                  <div>
                    <dt>Capacity</dt>
                    <dd>
                      {preview.nominal_capacity} → {preview.disruption.capacity}
                    </dd>
                  </div>
                  <div>
                    <dt>Weeks</dt>
                    <dd>
                      {preview.disruption.start_week}–{preview.disruption.end_week}
                    </dd>
                  </div>
                </dl>
                <div className="preview-actions">
                  <button
                    className="secondary-button"
                    disabled={asking || executing}
                    onClick={() => setPreview(null)}
                  >
                    Cancel
                  </button>
                  <button
                    className="primary-button"
                    disabled={asking || executing}
                    onClick={() => void executePreview()}
                  >
                    {executing ? "Starting…" : "Run validated re-plan"}
                  </button>
                </div>
              </section>
            )}
            {asking && <p className="agent-thinking">Copilot is checking validated evidence…</p>}
          </div>
          {error && <p className="inline-error">{error}</p>}
          <form
            className="agent-composer"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              void ask();
            }}
          >
            <textarea
              value={question}
              maxLength={500}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask across scenarios A, B and C, or describe a scenario-specific disruption"
              rows={3}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div>
              <button
                className="primary-button"
                disabled={asking || executing || !question.trim()}
              >
                {asking ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}
                Send
              </button>
            </div>
          </form>
        </section>
      </div>
    </section>
  );
}

/**
 * Permanent right-column AI Assistant & Replan Panel for 2-column dashboard
 */
export function AIAssistantPanel({
  jobId,
  scenario,
  runStatus,
  usage,
  hotspots,
  locations,
  onOpenAgentMode,
}: {
  jobId: string;
  scenario: Scenario;
  runStatus: string;
  usage: LocationUsage[];
  hotspots: LocationUsage[];
  locations: { location_id: string; capacity: number }[];
  onOpenAgentMode?: () => void;
}) {
  const suggested = hotspots[0] ?? usage[0];
  const [location, setLocation] = useState(suggested?.location_id ?? locations[0]?.location_id ?? "");
  const [startWeek, setStartWeek] = useState(suggested?.week ?? 1);
  const [endWeek, setEndWeek] = useState(suggested?.week ?? 1);
  const [capacity, setCapacity] = useState(0);
  const [reason, setReason] = useState("urgent_maintenance");
  const [replan, setReplan] = useState<LegacyReplan | null>(null);
  const [view, setView] = useState<"baseline" | "revised">("baseline");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState<{ question: string; answer: Answer }[]>([]);
  const [asking, setAsking] = useState(false);
  const [assistantError, setAssistantError] = useState("");
  const askingRef = useRef(false);
  const startingRef = useRef(false);
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
        const next = await request<LegacyReplan>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans/${replanId}`);
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
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [jobId, replan, scenario]);

  async function startReplan(event: FormEvent) {
    event.preventDefault();
    if (startingRef.current || runStatus !== "completed" || (replan && ["queued", "running"].includes(replan.status))) {
      return;
    }
    startingRef.current = true;
    setStarting(true);
    setError("");
    try {
      const next = await request<LegacyReplan>(`/api/ps1/jobs/${jobId}/scenarios/${scenario}/replans`, {
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
        body: JSON.stringify({
          scenario,
          replan_id: view === "revised" ? replan?.replan_id : null,
          question: text.trim(),
        }),
      });
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
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Sparkles size={16} color="var(--cyan)" />
          <h3 style={{ margin: 0, fontSize: "13px", fontWeight: 700 }}>RailFlow AI</h3>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {onOpenAgentMode && (
            <button
              type="button"
              className="secondary-button"
              style={{ fontSize: "10px", padding: "2px 6px" }}
              onClick={onOpenAgentMode}
              title="Full Agent Mode"
            >
              Expand
            </button>
          )}
          <div className="segmented-control" role="group" style={{ margin: 0 }}>
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
      </div>

      <div className="ai-sidebar-body">
        {mode === "chat" ? (
          <>
            <div className="query-suggestions">
              {[
                "Why was A001 moved?",
                "What is the downstream delay risk?",
                `Capacity at ${location || "SEC:ALP:S01_S02:EB"} week ${startWeek}`,
                `Handover brief for week ${startWeek}`,
              ].map((item) => (
                <button type="button" key={item} onClick={() => void ask(item)}>
                  {item}
                </button>
              ))}
            </div>

            <form
              className="assistant-form"
              onSubmit={(e) => {
                e.preventDefault();
                void ask();
              }}
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
                  <AnswerBody text={entry.answer.answer} />
                  <small>
                    {entry.answer.intent} · Evidence: {entry.answer.evidence?.join(", ") || "Summary"}
                  </small>
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
                  <input
                    type="number"
                    min={0}
                    max={Math.max(0, nominal - 1)}
                    value={capacity}
                    onChange={(e) => setCapacity(Number(e.target.value))}
                  />
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
                disabled={
                  starting ||
                  runStatus !== "completed" ||
                  !location ||
                  replan?.status === "running" ||
                  replan?.status === "queued"
                }
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
                  <div className="detail-field">
                    <span>Moved</span>
                    <strong>{summary.moved_activities}</strong>
                  </div>
                  <div className="detail-field">
                    <span>Preserved</span>
                    <strong>{summary.preserved_percent}%</strong>
                  </div>
                  <div className="detail-field">
                    <span>Delta</span>
                    <strong>{summary.score_delta >= 0 ? `+${summary.score_delta}` : summary.score_delta}</strong>
                  </div>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Activity</th>
                        <th>Old</th>
                        <th>New</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(replan?.diff.activity_changes ?? []).slice(0, 5).map((ch) => (
                        <tr key={ch.activity_id}>
                          <td>
                            <strong>{ch.activity_id}</strong>
                          </td>
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
