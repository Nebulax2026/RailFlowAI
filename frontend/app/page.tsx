import Link from "next/link";
import { CalendarClock, ClipboardPlus } from "lucide-react";

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">RailFlow AI</div>
        <nav className="nav">
          <Link className="secondary" href="/request/new">
            <ClipboardPlus size={18} />
            Field Request
          </Link>
          <Link href="/dashboard">
            <CalendarClock size={18} />
            Planner Dashboard
          </Link>
        </nav>
      </header>
      <section className="form-page">
        <h1>Explainable Railway Maintenance Scheduling System</h1>
        <p>
          Field teams submit maintenance requests from the web interface, while planners review
          conflicts, optimise schedules, and approve solver-validated changes.
        </p>
      </section>
    </main>
  );
}
