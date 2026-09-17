"use client";

import { FormEvent, useRef, useState } from "react";

type Pending = {
  approval_id: string;
  preview: {
    action: string;
    description: string;
    parameters: Record<string, unknown>;
    affected: Array<{ collection: string; item?: Record<string, unknown>; count?: number }>;
    import_result?: Record<string, unknown>;
    note: string;
    [key: string]: unknown;
  };
};

type Message = { id: string; role: "user" | "assistant"; content: string; pending?: Pending; result?: unknown; state?: "pending" | "complete" | "rejected" | "failed" };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export default function AgentChat({ role, owner, onChanged }: { role: string; owner: string; onChanged: () => Promise<void> }) {
  const [messages, setMessages] = useState<Message[]>([{ id: "welcome", role: "assistant", content: "I can help with requests, schedule generation, alternatives, approvals, and freeze windows. I will preview every change and wait for your approval before applying it." }]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function parseResponse(response: Response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail ?? "Agent request failed."));
    }
    return data;
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    const latestPending = [...messages].reverse().find((item) => item.pending && item.state === "pending");
    if (latestPending && /^(yes|approve|confirm|apply)( it| this)?[.!]?$/i.test(text)) {
      setDraft("");
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: text }]);
      await decide(latestPending, "approve");
      return;
    }
    const history = messages.filter((item) => !item.pending).slice(-12).map(({ role: messageRole, content }) => ({ role: messageRole, content }));
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: text }]);
    setDraft("");
    setBusy(true);
    try {
      const data = await parseResponse(await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history, role, owner })
      }));
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: data.message, pending: data.pending, state: data.pending ? "pending" : undefined }]);
    } catch (error) {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: error instanceof Error ? error.message : "Agent request failed.", state: "failed" }]);
    } finally { setBusy(false); }
  }

  async function decide(message: Message, decision: "approve" | "reject") {
    if (!message.pending || busy || message.state !== "pending") return;
    setBusy(true);
    try {
      const data = await parseResponse(await fetch(`${API_BASE}/api/agent/${decision}/${message.pending.approval_id}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role, owner })
      }));
      setMessages((current) => current.map((item): Message => item.id === message.id ? { ...item, state: decision === "approve" ? "complete" : "rejected" } : item).concat({ id: crypto.randomUUID(), role: "assistant", content: data.message, result: data.result }));
      if (decision === "approve") await onChanged();
    } catch (error) {
      setMessages((current) => current.map((item): Message => item.id === message.id ? { ...item, state: "failed" } : item).concat({ id: crypto.randomUUID(), role: "assistant", content: error instanceof Error ? error.message : "Action failed.", state: "failed" }));
    } finally { setBusy(false); }
  }

  async function upload(file: File) {
    if (busy) return;
    setBusy(true);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: `Preview file: ${file.name}` }]);
    try {
      const form = new FormData(); form.append("file", file);
      const query = new URLSearchParams({ role, owner });
      const data = await parseResponse(await fetch(`${API_BASE}/api/agent/import/preview?${query}`, { method: "POST", body: form }));
      const errors = Array.isArray(data.result?.errors) ? `\n${data.result.errors.join("\n")}` : "";
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: data.message + errors, pending: data.pending, state: data.pending ? "pending" : undefined }]);
    } catch (error) {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: error instanceof Error ? error.message : "File preview failed.", state: "failed" }]);
    } finally { setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  }

  return <section className="agent-chat" aria-label="AI Agent chat">
    <header className="agent-chat-header"><div><span className="eyebrow">RailFlowAI</span><h2>AI Agent</h2></div><span className="agent-live">Approval required for changes</span></header>
    <div className="agent-messages" aria-live="polite">
      {messages.map((message) => <div className={`agent-message ${message.role}`} key={message.id}>
        <span className="agent-message-role">{message.role === "assistant" ? "Agent" : "You"}</span>
        <p>{message.content}</p>
        {message.result !== undefined && <details><summary>View API result</summary><pre>{JSON.stringify(message.result, null, 2)}</pre></details>}
        {message.pending && <div className="agent-approval">
          <strong>{message.pending.preview.description}</strong>
          <p>{message.pending.preview.note}</p>
          <details><summary>Review changes and impact</summary>
            <pre>{JSON.stringify(message.pending.preview, null, 2)}</pre>
          </details>
          <span className="agent-state">{message.state === "pending" ? "Awaiting approval" : message.state === "complete" ? "Applied" : message.state === "rejected" ? "Cancelled" : "Failed"}</span>
          {message.state === "pending" && <div className="agent-approval-actions"><button className="button secondary" disabled={busy} onClick={() => void decide(message, "reject")}>Reject</button><button className="button" disabled={busy} onClick={() => void decide(message, "approve")}>Approve and apply</button></div>}
        </div>}
      </div>)}
      {busy && <p className="agent-thinking">Agent is working…</p>}
    </div>
    <form className="agent-composer" onSubmit={(event) => void send(event)}>
      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="For example: Show pending requests / Freeze D+3" rows={3} aria-label="Agent message" onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
      <div><input ref={fileInput} type="file" accept=".csv,.json" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} /><button type="button" className="button secondary" disabled={busy} onClick={() => fileInput.current?.click()}>CSV / JSON</button><button className="button" disabled={busy || !draft.trim()} type="submit">Send</button></div>
    </form>
  </section>;
}
