"use client";

import Link from "next/link";
import { ArrowLeft, Send } from "lucide-react";

export default function NewRequestPage() {
  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">Field Request Mode</div>
        <nav className="nav">
          <Link className="secondary" href="/">
            <ArrowLeft size={18} />
            Back
          </Link>
        </nav>
      </header>
      <section className="form-page">
        <form className="panel form">
          <div className="panel-header">New Maintenance Request</div>
          <div className="panel-body form">
            <div className="field">
              <label>Work Type</label>
              <select>
                <option>Signal</option>
                <option>Electrical</option>
                <option>Track</option>
                <option>Inspection</option>
              </select>
            </div>
            <div className="field">
              <label>Track Sector</label>
              <input placeholder="T12" />
            </div>
            <div className="field">
              <label>Priority</label>
              <select>
                <option>5 - Critical</option>
                <option>4 - High</option>
                <option>3 - Normal</option>
                <option>2 - Low</option>
              </select>
            </div>
            <div className="field">
              <label>Earliest Start</label>
              <input type="datetime-local" />
            </div>
            <div className="field">
              <label>Deadline</label>
              <input type="datetime-local" />
            </div>
            <div className="field">
              <label>Estimated Duration</label>
              <input placeholder="90 minutes" />
            </div>
            <div className="field">
              <label>Required Crew</label>
              <input placeholder="E2, TG1" />
            </div>
            <div className="field">
              <label>Required Equipment</label>
              <input placeholder="GeometryCar-1" />
            </div>
            <div className="field">
              <label>Safety Constraint</label>
              <input placeholder="Power isolation required" />
            </div>
            <div className="field">
              <label>Notes</label>
              <textarea rows={4} />
            </div>
            <button className="button" type="button">
              <Send size={18} />
              Submit
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
