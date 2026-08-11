import Link from "next/link";
import type { CSSProperties } from "react";
import { Lock, Plus, SlidersHorizontal } from "lucide-react";

const requests = [
  { id: "M-101", title: "Signal relay inspection", meta: "T12 / Signal / Priority 5", status: "conflict" },
  { id: "M-102", title: "Track geometry check", meta: "T12 / Inspection / Priority 3", status: "conflict" },
  { id: "M-103", title: "Power isolation test", meta: "T08 / Electrical / Priority 4", status: "normal" },
  { id: "M-104", title: "Brake system inspection", meta: "T14 / Emergency / Priority 5", status: "suggested" }
];

const ganttRows = [
  { track: "T08", task: "M-103", left: "4%", width: "28%", status: "normal" },
  { track: "T12", task: "M-101", left: "12%", width: "26%", status: "conflict" },
  { track: "T12", task: "M-102", left: "24%", width: "22%", status: "conflict" },
  { track: "T14", task: "M-104", left: "54%", width: "18%", status: "suggested" }
];

export default function DashboardPage() {
  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">Planner Dashboard</div>
        <nav className="nav">
          <Link className="secondary" href="/request/new">
            <Plus size={18} />
            New Request
          </Link>
          <button className="button">
            <SlidersHorizontal size={18} />
            Optimise
          </button>
        </nav>
      </header>

      <section className="kpis">
        <div className="kpi"><span>Unresolved Conflicts</span><strong>2</strong></div>
        <div className="kpi"><span>Critical Jobs Scheduled</span><strong>3</strong></div>
        <div className="kpi"><span>Window Utilisation</span><strong>76%</strong></div>
        <div className="kpi"><span>Estimated Overtime</span><strong>0h</strong></div>
        <div className="kpi"><span>Schedule Stability</span><strong>91%</strong></div>
        <div className="kpi"><span>Robustness Score</span><strong>84</strong></div>
      </section>

      <section className="dashboard-grid">
        <aside className="panel">
          <div className="panel-header">Requests</div>
          <div className="panel-body request-list">
            {requests.map((request) => (
              <div className="request-item" key={request.id}>
                <strong>{request.id} / {request.title}</strong>
                <span>{request.meta}</span>
              </div>
            ))}
          </div>
        </aside>

        <section className="panel">
          <div className="panel-header">Gantt Schedule</div>
          <div className="panel-body gantt">
            {ganttRows.map((row) => (
              <div className="gantt-row" key={`${row.track}-${row.task}`}>
                <div className="track-label">{row.track}</div>
                <div className="timeline">
                  <div
                    className={`task ${row.status}`}
                    style={{ "--left": row.left, "--width": row.width } as CSSProperties}
                  >
                    {row.task}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="panel">
          <div className="panel-header">Decision Review</div>
          <div className="panel-body">
            <p>
              M-101 and M-102 use track sector T12 during an overlapping maintenance window.
              M-101 has higher priority and an earlier deadline, so M-102 is the better move candidate.
            </p>
            <p>
              Suggested movement: move M-102 after 02:30 to preserve critical signal work and keep the
              approved schedule stable.
            </p>
            <div className="nav">
              <button className="button">Accept</button>
              <button className="button secondary">Modify</button>
              <button className="button secondary">Reject</button>
              <button className="button secondary" title="Lock schedule">
                <Lock size={18} />
              </button>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
