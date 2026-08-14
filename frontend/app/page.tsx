import Link from "next/link";
import { ArrowRight, CalendarClock, ClipboardPlus, GitBranch, ShieldCheck, Sparkles } from "lucide-react";

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">RailFlow AI</div>
        <nav className="nav">
          <Link className="secondary" href="/request/new">
            <ClipboardPlus size={18} />
            New Request
          </Link>
          <Link href="/dashboard">
            <CalendarClock size={18} />
            Schedule Dashboard
          </Link>
        </nav>
      </header>
      <section className="home-hero">
        <div className="hero-copy">
          <h1>RailFlow AI</h1>
          <div className="hero-actions">
            <Link href="/dashboard">
              <CalendarClock size={18} />
              Open Dashboard
              <ArrowRight size={16} />
            </Link>
            <Link className="secondary" href="/request/new">
              <ClipboardPlus size={18} />
              Create Request
            </Link>
          </div>
        </div>
        <div className="signal-panel" aria-label="RailFlow AI workflow summary">
          <div className="signal-track">
            <span />
            <span />
            <span />
          </div>
          <div className="signal-metric">
            <span>Schedule Stability</span>
            <strong>96%</strong>
          </div>
          <div className="signal-metric accent">
            <span>Open Contentions</span>
            <strong>02</strong>
          </div>
        </div>
      </section>

      <section className="feature-band" aria-label="Core workflow">
        <article>
          <ClipboardPlus size={22} />
          <h2>Capture Work</h2>
          <p>Guided request entry keeps track sector, work type, crew, and equipment requirements consistent.</p>
        </article>
        <article>
          <GitBranch size={22} />
          <h2>Resolve Dependencies</h2>
          <p>Prerequisite rules and conflict checks make it easier to understand why work can or cannot fit.</p>
        </article>
        <article>
          <ShieldCheck size={22} />
          <h2>Approve Safely</h2>
          <p>Schedule Managers can review alternatives before locking a solver-validated plan.</p>
        </article>
        <article>
          <Sparkles size={22} />
          <h2>Compare Options</h2>
          <p>Ranked alternatives expose tradeoffs across disruption, overtime, completion, and robustness.</p>
        </article>
      </section>
    </main>
  );
}
