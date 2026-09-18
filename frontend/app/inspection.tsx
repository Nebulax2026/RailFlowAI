"use client";

import { useMemo, useState } from "react";

export type EvidenceActivity = {
  activity_id: string; contract_number: string; line: string; access_type: string;
  required_workload: number; delivered_workload: number; completion_date: string;
  planned_start_date: string; planned_completion_date: string; overrun_days: number; delay_cost: number;
  predecessor: string | null; predecessor_finish_week: number | null; co_workers: string[];
  accesses: { week: number; eclo: number; access_night: number; physical_night?: number | null }[];
  protection: Record<string, string[]>;
  possessions: { week: number; location_id: string; co_share_group: string }[];
  evidence_note: string;
};
export type LocationUsage = { location_id: string; week: number; used: number; capacity: number;
  work_possessions: number; protection_possessions: number; activities: string[]; groups: Record<string,string[]>; protection_groups: string[][] };

export function Inspection({ activities, usage, view }: { activities: EvidenceActivity[]; usage: LocationUsage[]; view: "overview" | "activities" | "capacity" | "contracts" | null }) {
  const [contract, setContract] = useState("");
  const [line, setLine] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [location, setLocation] = useState("");
  const [week, setWeek] = useState("");
  const [table, setTable] = useState(false);
  const filtered = useMemo(() => activities.filter(a => (!contract || a.contract_number === contract) && (!line || a.line === line) && a.activity_id.toLowerCase().includes(query.toLowerCase())), [activities, contract, line, query]);
  const selected = filtered.find(a => a.activity_id === selectedId) ?? filtered[0];
  const sites = usage.filter(u => (!location || u.location_id === location) && (!week || u.week === Number(week)));
  return <div className="inspection" hidden={view !== "activities" && view !== "capacity"}>
    <section className="data-panel inspection-panel" role="tabpanel" id={view ? "panel-activities" : undefined} aria-labelledby="tab-activities" tabIndex={0} hidden={view !== "activities"}>
      <div className="subheading"><h3>Activity schedule and evidence</h3><button className="secondary-button" onClick={() => setTable(!table)}>{table ? "Show timeline" : "Show table"}</button></div>
      <div className="inspection-filters">
        <label>Contract<select value={contract} onChange={e => setContract(e.target.value)}><option value="">All contracts</option>{[...new Set(activities.map(a => a.contract_number))].sort().map(c => <option key={c}>{c}</option>)}</select></label>
        <label>Line<select value={line} onChange={e => setLine(e.target.value)}><option value="">All lines</option>{[...new Set(activities.map(a => a.line))].sort().map(l => <option key={l}>{l}</option>)}</select></label>
        <label>Activity<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search activity ID" /></label>
      </div>
      <div className="activity-browser">
        <div className="activity-list" aria-label="Activities">{filtered.map(a => <button aria-pressed={selected?.activity_id === a.activity_id} key={a.activity_id} onClick={() => setSelectedId(a.activity_id)}><strong>{a.activity_id}</strong><span>{a.contract_number} · {a.line}</span><small>{a.delivered_workload}/{a.required_workload} work units · {a.overrun_days ? `${a.overrun_days} days late` : "On plan"}</small></button>)}{!filtered.length && <p>No matching activities.</p>}</div>
        {selected && <article className="activity-evidence" aria-label={`Evidence for ${selected.activity_id}`}>
          <h4>{selected.activity_id} · {selected.access_type}</h4>
          <p>Planned start {selected.planned_start_date}; planned completion {selected.planned_completion_date}. Scheduled completion {selected.completion_date}. Weighted delay cost: {selected.delay_cost}.</p>
          {table ? <div className="table-wrap"><table><thead><tr><th>Week</th><th>Local access night</th><th>Verified physical night</th><th>Yield</th></tr></thead><tbody>{selected.accesses.map(a => <tr key={a.week}><td>{a.week}</td><td>{a.access_night}</td><td>{a.physical_night ?? "Unavailable"}</td><td>{a.eclo ? "1.5 · ECLO" : "1 · Standard"}</td></tr>)}</tbody></table></div> : <ol className="access-timeline" aria-label="Scheduled access weeks">{selected.accesses.map(a => <li key={a.week} className={a.eclo ? "eclo" : ""}><strong>Week {a.week}</strong><span>Local night {a.access_night}; physical night {a.physical_night ?? "unavailable"}</span><small>{a.eclo ? "ECLO · 1.5 units" : "Standard · 1 unit"}</small></li>)}</ol>}
          <p>Predecessor: {selected.predecessor ? `${selected.predecessor}, completes in week ${selected.predecessor_finish_week}` : "None"}. Co-sharing activities: {selected.co_workers.join(", ") || "None"}.</p>
          <p className="muted">Access-night numbers are local to the contract and week. Verified physical nights 1?7 form one consistent weekly assignment across contracts; they are not confirmed maintenance dates. Group labels remain local to each location and week.</p>
          {Object.entries(selected.protection).map(([kind, locations]) => <details key={kind}><summary>{kind.replaceAll("_", " ")} ({locations.length})</summary><ul>{locations.map(loc => <li key={loc}>{loc}</li>)}</ul></details>)}
          <details><summary>Possession memberships ({selected.possessions.length})</summary><div className="table-wrap"><table><thead><tr><th>Week</th><th>Location</th><th>Group</th></tr></thead><tbody>{selected.possessions.map(p => <tr key={`${p.week}-${p.location_id}`}><td>{p.week}</td><td>{p.location_id}</td><td>{p.co_share_group}</td></tr>)}</tbody></table></div></details>
          <p className="muted">{selected.evidence_note}</p>
        </article>}
      </div>
    </section>
    <section className="data-panel inspection-panel" role="tabpanel" id={view ? "panel-capacity" : undefined} aria-labelledby="tab-capacity" tabIndex={0} hidden={view !== "capacity"}>
      <div className="subheading"><h3>Location and week inspection</h3><span>{sites.length} rows</span></div>
      <div className="inspection-filters"><label>Location<select value={location} onChange={e => setLocation(e.target.value)}><option value="">All locations</option>{[...new Set(usage.map(u => u.location_id))].sort().map(l => <option key={l}>{l}</option>)}</select></label><label>Week<select value={week} onChange={e => setWeek(e.target.value)}><option value="">All weeks</option>{[...new Set(usage.map(u => u.week))].sort((a,b) => a-b).map(w => <option key={w}>{w}</option>)}</select></label></div>
      <p className="muted">Used slots count work possessions only. Protection footprints do not consume extra supply. CSV validation reconstructs a consistent weekly night assignment across contracts, checking sharing and protection conflicts. Exact maintenance calendars are not supplied.</p>
      <div className="table-wrap location-table"><table><thead><tr><th>Location</th><th>Week</th><th>Used / supply</th><th>Protecting activities</th><th>Activities</th><th>Groups</th></tr></thead><tbody>{sites.map(u => <tr key={`${u.location_id}-${u.week}`}><td>{u.location_id}</td><td>{u.week}</td><td>{u.used} / {u.capacity}</td><td>{u.protection_possessions}</td><td>{u.activities.join(", ")}</td><td>{Object.entries(u.groups).map(([g,ids]) => `${g}: ${ids.join(", ")}`).join("; ") || "Protection only"}</td></tr>)}{!sites.length && <tr><td colSpan={6}>No matching locations or weeks.</td></tr>}</tbody></table></div>
    </section>
  </div>;
}
