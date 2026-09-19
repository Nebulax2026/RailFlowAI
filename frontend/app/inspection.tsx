"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Calendar, CheckCircle2, Clock, Filter, Layers, MapPin, Shield, Users } from "lucide-react";
import { formatLocationName } from "./schedule-types";

export type EvidenceActivity = {
  activity_id: string;
  contract_number: string;
  line: string;
  access_type: string;
  required_workload: number;
  delivered_workload: number;
  completion_date: string;
  planned_start_date: string;
  planned_completion_date: string;
  overrun_days: number;
  delay_cost: number;
  contract_completion_date: string;
  contract_overrun_days: number;
  predecessor: string | null;
  predecessor_finish_week: number | null;
  co_workers: string[];
  accesses: { week: number; eclo: number; access_night: number; physical_night?: number | null }[];
  protection: Record<string, string[]>;
  possessions: { week: number; location_id: string; co_share_group: string }[];
  evidence_note: string;
};

export type LocationUsage = {
  location_id: string;
  week: number;
  used: number;
  capacity: number;
  work_possessions: number;
  protection_possessions: number;
  activities: string[];
  groups: Record<string, string[]>;
  protection_groups: string[][];
};

export type ActivityChange = {
  activity_id: string;
  contract_number: string;
  before: { week: number; eclo: number; access_night: number }[];
  after: { week: number; eclo: number; access_night: number }[];
  reason: string;
};

export function Inspection({
  activities,
  usage,
  view,
  initialWeekFilter,
  onClearWeekFilter,
  activityChanges,
}: {
  activities: EvidenceActivity[];
  usage: LocationUsage[];
  view: "overview" | "activities" | "locations" | "contracts" | null;
  initialWeekFilter?: number | null;
  onClearWeekFilter?: () => void;
  activityChanges?: ActivityChange[];
}) {
  // Activities states
  const [contract, setContract] = useState("");
  const [line, setLine] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "delayed" | "ontime">("all");
  const [showMovedOnly, setShowMovedOnly] = useState(false);
  const [sortBy, setSortBy] = useState<"id" | "start" | "end" | "overrun" | "eclo">("id");
  const [sortAsc, setSortAsc] = useState(true);
  const [selectedId, setSelectedId] = useState("");
  const [showTimeline, setShowTimeline] = useState(true);

  // Locations states
  const [locLine, setLocLine] = useState("");
  const [locType, setLocType] = useState<"all" | "SEC" | "STN" | "BUF">("all");
  const [locContract, setLocContract] = useState<string>("all");
  const [locQuery, setLocQuery] = useState("");
  const [locWeek, setLocWeek] = useState(initialWeekFilter ? String(initialWeekFilter) : "");
  const [locSaturation, setLocSaturation] = useState<"all" | "saturated" | "available">("all");
  const [locSortBy, setLocSortBy] = useState<"name" | "week" | "saturation">("name");
  const [locSortAsc, setLocSortAsc] = useState(true);

  // Activity to contract mapping for location filtering
  const activityContractMap = useMemo(() => {
    const map = new Map<string, string>();
    activities.forEach((a) => {
      map.set(a.activity_id, a.contract_number);
    });
    return map;
  }, [activities]);

  const contractOptions = useMemo(() => {
    const set = new Set<string>();
    activities.forEach((a) => {
      if (a.contract_number) set.add(a.contract_number);
    });
    return Array.from(set).sort();
  }, [activities]);

  // Unique locations for activity filtering
  const locationOptions = useMemo(() => {
    const map = new Map<string, string>();
    activities.forEach((a) => {
      a.possessions?.forEach((p) => {
        if (p.location_id && !map.has(p.location_id)) {
          const formatted = formatLocationName(p.location_id);
          map.set(p.location_id, `${formatted.primary} (${p.location_id})`);
        }
      });
    });
    return Array.from(map.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [activities]);

  const movedMap = useMemo(() => {
    const map = new Map<string, ActivityChange>();
    activityChanges?.forEach((c) => map.set(c.activity_id, c));
    return map;
  }, [activityChanges]);

  const filteredActivities = useMemo(() => {
    return activities
      .filter((a) => {
        if (showMovedOnly && !movedMap.has(a.activity_id)) return false;
        if (contract && a.contract_number !== contract) return false;
        if (line && a.line !== line) return false;
        if (locationFilter && !a.possessions?.some((p) => p.location_id === locationFilter)) return false;
        if (query && !a.activity_id.toLowerCase().includes(query.toLowerCase())) return false;
        if (statusFilter === "delayed" && a.contract_overrun_days <= 0) return false;
        if (statusFilter === "ontime" && a.contract_overrun_days > 0) return false;
        if (initialWeekFilter && !a.accesses.some((acc) => acc.week === initialWeekFilter)) return false;
        return true;
      })
      .sort((a, b) => {
        let diff = 0;
        if (sortBy === "id") {
          diff = a.activity_id.localeCompare(b.activity_id);
        } else if (sortBy === "start") {
          diff = (a.planned_start_date || "").localeCompare(b.planned_start_date || "");
        } else if (sortBy === "end") {
          diff = (a.completion_date || "").localeCompare(b.completion_date || "");
        } else if (sortBy === "overrun") {
          diff = a.contract_overrun_days - b.contract_overrun_days;
        } else if (sortBy === "eclo") {
          const ecloA = a.accesses?.reduce((sum, acc) => sum + (acc.eclo > 0 ? 1 : 0), 0) ?? 0;
          const ecloB = b.accesses?.reduce((sum, acc) => sum + (acc.eclo > 0 ? 1 : 0), 0) ?? 0;
          diff = ecloA - ecloB;
        }
        return sortAsc ? diff : -diff;
      });
  }, [activities, contract, line, locationFilter, query, statusFilter, sortBy, sortAsc, initialWeekFilter, showMovedOnly, movedMap]);

  const selected = filteredActivities.find((a) => a.activity_id === selectedId) ?? filteredActivities[0];

  const filteredLocations = useMemo(() => {
    return usage
      .filter((u) => {
        const isSaturated = u.used >= u.capacity;
        if (locSaturation === "saturated" && !isSaturated) return false;
        if (locSaturation === "available" && isSaturated) return false;
        if (locWeek && u.week !== Number(locWeek)) return false;
        if (locLine) {
          const locLineCode = u.location_id.split(":")[1];
          if (locLineCode !== locLine) return false;
        }
        if (locType !== "all") {
          const prefix = u.location_id.split(":")[0];
          if (prefix !== locType) return false;
        }
        if (locContract !== "all") {
          const hasContract = u.activities.some((aid) => activityContractMap.get(aid) === locContract);
          if (!hasContract) return false;
        }
        if (locQuery) {
          const formatted = formatLocationName(u.location_id);
          const q = locQuery.toLowerCase();
          if (!u.location_id.toLowerCase().includes(q) && !formatted.primary.toLowerCase().includes(q)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        let diff = 0;
        if (locSortBy === "week") diff = a.week - b.week;
        else if (locSortBy === "saturation") diff = (a.used / a.capacity) - (b.used / b.capacity);
        else diff = a.location_id.localeCompare(b.location_id);
        return locSortAsc ? diff : -diff;
      });
  }, [usage, locLine, locType, locContract, locQuery, locWeek, locSaturation, locSortBy, locSortAsc, activityContractMap]);

  // Tab 2: ACTIVITIES
  if (view === "activities") {
    return (
      <section className="data-panel tab-full-panel" role="tabpanel" id="panel-activities" aria-labelledby="tab-activities">
        <div className="subheading">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h3>Scheduled Maintenance Activities</h3>
            {initialWeekFilter && (
              <span className="chip" style={{ background: "var(--cyan-soft)", color: "var(--cyan)", border: "1px solid var(--cyan)" }}>
                Week {initialWeekFilter} Filtered
                <button onClick={onClearWeekFilter} style={{ marginLeft: "4px", color: "inherit" }}>×</button>
              </span>
            )}
          </div>
          <span className="muted">{filteredActivities.length} matching activities</span>
        </div>

        <div className="inspection-filters">
          {/* Row 1: 4 Primary Filters (Proportional to Value Lengths) */}
          <div className="inspection-filters-row">
            <label style={{ flex: 1, minWidth: "110px" }}>
              Contract
              <select value={contract} onChange={(e) => setContract(e.target.value)}>
                <option value="">All contracts</option>
                {[...new Set(activities.map((a) => a.contract_number))].sort().map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <label style={{ flex: 1, minWidth: "110px" }}>
              Line
              <select value={line} onChange={(e) => setLine(e.target.value)}>
                <option value="">All lines</option>
                {[...new Set(activities.map((a) => a.line))].sort().map((l) => (
                  <option key={l} value={l}>{l === "ALP" ? "Alpha Line" : l === "BET" ? "Beta Line" : l}</option>
                ))}
              </select>
            </label>
            <label style={{ flex: 2.8, minWidth: "250px" }}>
              Location
              <select value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)}>
                <option value="">All locations</option>
                {locationOptions.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ flex: 1.25, minWidth: "135px" }}>
              Status
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as any)}>
                <option value="all">All statuses</option>
                <option value="delayed">Contract Delayed</option>
                <option value="ontime">Contract On-Time</option>
              </select>
            </label>
          </div>

          {/* Row 2: Search + Sort By Side-by-Side */}
          <div className="inspection-filters-row">
            <label style={{ flex: 1 }}>
              Search
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search Activity ID (e.g. A001)"
              />
            </label>
            {activityChanges && activityChanges.length > 0 && (
              <button
                type="button"
                className={`replan-filter-moved-btn ${showMovedOnly ? "active" : ""}`}
                onClick={() => setShowMovedOnly(!showMovedOnly)}
                title="Filter to activities whose scheduled weeks shifted in this re-plan"
              >
                ⚡ Moved Only ({activityChanges.length})
              </button>
            )}
            <label style={{ width: "240px", flexShrink: 0 }}>
              Sort By
              <div className="sort-combo-control">
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}>
                  <option value="id">Activity ID</option>
                  <option value="start">Planned Start</option>
                  <option value="end">Projected Finish</option>
                  <option value="overrun">Overrun Days</option>
                  <option value="eclo">ECLO Nights</option>
                </select>
                <button
                  type="button"
                  className="sort-toggle-dir"
                  onClick={() => setSortAsc(!sortAsc)}
                  title={sortAsc ? "Ascending (Click for Descending)" : "Descending (Click for Ascending)"}
                >
                  {sortAsc ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
                </button>
              </div>
            </label>
          </div>
        </div>

        <div className="activity-browser">
          <div className="activity-list" aria-label="Activities List">
            {filteredActivities.map((a) => {
              const isSelected = selected?.activity_id === a.activity_id;
              const hasContractDelay = a.contract_overrun_days > 0;
              const moved = movedMap.get(a.activity_id);
              return (
                <button
                  key={a.activity_id}
                  aria-pressed={isSelected}
                  onClick={() => setSelectedId(a.activity_id)}
                  style={{ borderLeft: moved ? "3px solid var(--amber)" : hasContractDelay ? "3px solid var(--rose)" : "3px solid var(--emerald)" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <strong>{a.activity_id}</strong>
                      {moved && <span className="replan-moved-pill">Moved</span>}
                    </div>
                    <span className={`tier-badge ${hasContractDelay ? "tier-1" : "tier-3"}`}>
                      {hasContractDelay ? `+${a.contract_overrun_days}d late` : "On plan"}
                    </span>
                  </div>
                  <span>{a.contract_number} · {a.line === "ALP" ? "Alpha Line" : "Beta Line"}</span>
                  {moved ? (
                    <small style={{ color: "var(--amber)", fontWeight: 600 }}>
                      Shifted: {moved.before.map((b) => `W${b.week}`).join(",")} → {moved.after.map((af) => `W${af.week}`).join(",")}
                    </small>
                  ) : (
                    <small>{a.delivered_workload}/{a.required_workload} work units · Projected: {a.completion_date}</small>
                  )}
                </button>
              );
            })}
            {!filteredActivities.length && <p className="muted">No matching activities found.</p>}
          </div>

          {selected && (
            <article className="activity-evidence" aria-label={`Evidence for ${selected.activity_id}`}>
              <div className="evidence-header">
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <h4>{selected.activity_id}</h4>
                    {movedMap.has(selected.activity_id) && <span className="replan-moved-pill">Moved in Re-plan</span>}
                    <span className="tier-badge" style={{ background: "var(--cyan-soft)", color: "var(--cyan)" }}>
                      {selected.line === "ALP" ? "Alpha Line" : "Beta Line"}
                    </span>
                    <span className="tier-badge" style={{ background: "var(--bg-shell)", color: "var(--text-secondary)" }}>
                      {selected.access_type} Possession
                    </span>
                  </div>
                  <span className="muted" style={{ fontSize: "11px", marginTop: "2px", display: "block" }}>
                    Contract {selected.contract_number} · Required Workload: {selected.required_workload} units ({selected.delivered_workload} delivered)
                  </span>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => setShowTimeline(!showTimeline)}
                  style={{ fontSize: "11px", padding: "4px 8px" }}
                >
                  {showTimeline ? "Table View" : "Timeline View"}
                </button>
              </div>

              {/* Re-plan Shift Callout if Moved */}
              {movedMap.has(selected.activity_id) && (() => {
                const m = movedMap.get(selected.activity_id)!;
                return (
                  <div className="replan-evidence-callout">
                    <div className="replan-callout-header">
                      <strong>Re-plan Schedule Shift Analysis</strong>
                      <span className="replan-callout-reason">Cause: <code>{m.reason}</code></span>
                    </div>
                    <div className="replan-callout-body">
                      <div>
                        <span className="callout-lbl">Baseline:</span>
                        <strong>{m.before.map((b) => `W${b.week} (N${b.access_night})`).join(", ") || "Unassigned"}</strong>
                      </div>
                      <span className="callout-sep">→</span>
                      <div>
                        <span className="callout-lbl">Revised:</span>
                        <strong style={{ color: "var(--amber)" }}>{m.after.map((af) => `W${af.week} (N${af.access_night})`).join(", ") || "Unassigned"}</strong>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Clean Key-Value Date Grids without verbose text */}
              <div className="dates-disambiguation-grid">
                <div className="date-status-box ontime">
                  <span className="title">Activity Schedule ({selected.activity_id})</span>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginTop: "2px" }}>
                    <span className="muted">Planned Start:</span>
                    <strong>{selected.planned_start_date}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                    <span className="muted">Projected Finish:</span>
                    <strong style={{ color: "var(--emerald)" }}>{selected.completion_date}</strong>
                  </div>
                </div>

                <div className={`date-status-box ${selected.contract_overrun_days > 0 ? "delayed" : "ontime"}`}>
                  <span className="title">Contract Completion ({selected.contract_number})</span>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginTop: "2px" }}>
                    <span className="muted">Target Deadline:</span>
                    <strong>{selected.planned_completion_date}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                    <span className="muted">Projected Finish:</span>
                    <strong>{selected.contract_completion_date}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", borderTop: "1px solid var(--border-subtle)", paddingTop: "4px", marginTop: "2px" }}>
                    <span className="muted">Overrun Status:</span>
                    <strong style={{ color: selected.contract_overrun_days > 0 ? "var(--rose)" : "var(--emerald)" }}>
                      {selected.contract_overrun_days > 0 ? `+${selected.contract_overrun_days} days` : "0 days"}
                    </strong>
                  </div>
                </div>
              </div>

              {/* Predecessors & Co-sharing interactive chips */}
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div className="chip-group">
                  <span className="chip-label">Predecessor:</span>
                  {selected.predecessor ? (
                    <button
                      className="chip"
                      onClick={() => setSelectedId(selected.predecessor!)}
                      title={`Click to view predecessor ${selected.predecessor}`}
                    >
                      <Clock size={12} />
                      <strong>{selected.predecessor}</strong> (Completes W{selected.predecessor_finish_week})
                    </button>
                  ) : (
                    <span className="muted" style={{ fontSize: "11px" }}>None (Root activity)</span>
                  )}
                </div>

                <div className="chip-group">
                  <span className="chip-label">Co-sharing Activities:</span>
                  {selected.co_workers.length > 0 ? (
                    selected.co_workers.map((coId) => (
                      <button
                        key={coId}
                        className="chip"
                        onClick={() => setSelectedId(coId)}
                        title={`Click to view co-worker ${coId}`}
                      >
                        <Users size={12} />
                        {coId}
                      </button>
                    ))
                  ) : (
                    <span className="muted" style={{ fontSize: "11px" }}>None (Exclusive possession)</span>
                  )}
                </div>
              </div>

              {/* Access Timeline or Table */}
              <div>
                <h5 style={{ margin: "0 0 8px", fontSize: "12px", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                  Scheduled Night Accesses ({selected.accesses.length} nights)
                </h5>
                {showTimeline ? (
                  <ol className="access-timeline">
                    {selected.accesses.map((a, idx) => (
                      <li key={idx} className={a.eclo ? "eclo" : ""}>
                        <div>
                          <strong>Week {a.week}</strong>
                          <span style={{ marginLeft: "8px", color: "var(--text-dim)", fontSize: "11px" }}>
                            Night #{a.access_night}
                          </span>
                        </div>
                        <div>
                          {a.eclo ? (
                            <span className="tier-badge" style={{ background: "rgba(236, 72, 153, 0.2)", color: "#f472b6", border: "1px solid rgba(236, 72, 153, 0.4)" }}>
                              ECLO · 1.5x Yield
                            </span>
                          ) : (
                            <span className="muted" style={{ fontSize: "11px" }}>Standard 1x</span>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Week</th>
                          <th>Night</th>
                          <th>Physical Night</th>
                          <th>Yield</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.accesses.map((a, idx) => (
                          <tr key={idx}>
                            <td>Week {a.week}</td>
                            <td>#{a.access_night}</td>
                            <td>{a.physical_night ?? "Consistent"}</td>
                            <td>{a.eclo ? "1.5x (ECLO)" : "1.0x (Standard)"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Possessions and Protection with Tunnel/Platform tags */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div className="detail-field">
                  <span>
                    <MapPin size={12} style={{ color: "var(--cyan)" }} /> Track Possessions ({selected.possessions.length})
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {selected.possessions.map((p, i) => {
                      const loc = formatLocationName(p.location_id);
                      return (
                        <div key={i} style={{ fontSize: "11.5px", display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
                          <span className="facility-tag">{loc.typeTag}</span>
                          <span style={{ color: "var(--text-dim)", fontWeight: 600 }}>W{p.week}</span>
                          <strong style={{ color: "var(--text-primary)" }}>{loc.primary}</strong>
                          <span className="muted" style={{ fontSize: "10px" }}>({p.co_share_group})</span>
                        </div>
                      );
                    })}
                    {selected.possessions.length === 0 && (
                      <span className="muted" style={{ fontSize: "11px" }}>No track possessions required</span>
                    )}
                  </div>
                </div>

                <div className="detail-field">
                  <span>
                    <Shield size={12} style={{ color: "var(--amber)" }} /> Protection Sectors ({Object.keys(selected.protection).length})
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {Object.entries(selected.protection).map(([kind, locs]) => (
                      <div key={kind} style={{ fontSize: "11.5px", display: "flex", alignItems: "center", gap: "6px" }}>
                        <span className="facility-tag" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--amber)", borderColor: "rgba(245, 158, 11, 0.3)" }}>
                          Isolation
                        </span>
                        <strong style={{ color: "var(--text-primary)" }}>{kind.replaceAll("_", " ")}</strong>
                        <span className="muted" style={{ fontSize: "10px" }}>({locs.length} sectors)</span>
                      </div>
                    ))}
                    {Object.keys(selected.protection).length === 0 && (
                      <span className="muted" style={{ fontSize: "11px" }}>No protection sectors required</span>
                    )}
                  </div>
                </div>
              </div>
            </article>
          )}
        </div>
      </section>
    );
  }

  // Tab 3: LOCATIONS (Independent view with standardized sort control)
  if (view === "locations") {
    return (
      <section className="data-panel tab-full-panel" role="tabpanel" id="panel-locations" aria-labelledby="tab-locations">
        <div className="subheading">
          <h3>Location Capacity & Week Matrix</h3>
          <span className="muted">{filteredLocations.length} location-week records</span>
        </div>

        <div className="inspection-filters">
          {/* Row 1: 5 Primary Filters (Proportional to Value Lengths) */}
          <div className="inspection-filters-row">
            <label style={{ flex: 1, minWidth: "110px" }}>
              Line
              <select value={locLine} onChange={(e) => setLocLine(e.target.value)}>
                <option value="">All Lines</option>
                <option value="ALP">Alpha Line</option>
                <option value="BET">Beta Line</option>
              </select>
            </label>
            <label style={{ flex: 1, minWidth: "110px" }}>
              Contract
              <select value={locContract} onChange={(e) => setLocContract(e.target.value)}>
                <option value="all">All Contracts</option>
                {contractOptions.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <label style={{ flex: 1.5, minWidth: "155px" }}>
              Type
              <select value={locType} onChange={(e) => setLocType(e.target.value as any)}>
                <option value="all">All Types</option>
                <option value="SEC">Tunnel Sector (SEC)</option>
                <option value="STN">Station Platform (STN)</option>
                <option value="BUF">Buffer Track (BUF)</option>
              </select>
            </label>
            <label style={{ flex: 1, minWidth: "105px" }}>
              Week
              <select value={locWeek} onChange={(e) => setLocWeek(e.target.value)}>
                <option value="">All weeks</option>
                {[...new Set(usage.map((u) => u.week))].sort((a, b) => a - b).map((w) => (
                  <option key={w} value={w}>Week {w}</option>
                ))}
              </select>
            </label>
            <label style={{ flex: 1.5, minWidth: "155px" }}>
              Saturation
              <select value={locSaturation} onChange={(e) => setLocSaturation(e.target.value as any)}>
                <option value="all">All levels</option>
                <option value="saturated">100% Saturated (Full)</option>
                <option value="available">Available Headroom</option>
              </select>
            </label>
          </div>

          {/* Row 2: Search + Sort By Side-by-Side */}
          <div className="inspection-filters-row">
            <label style={{ flex: 1 }}>
              Search Location
              <input
                value={locQuery}
                onChange={(e) => setLocQuery(e.target.value)}
                placeholder="Search by name or code (e.g. S01, H01)"
              />
            </label>
            <label style={{ width: "240px", flexShrink: 0 }}>
              Sort By
              <div className="sort-combo-control">
                <select value={locSortBy} onChange={(e) => setLocSortBy(e.target.value as any)}>
                  <option value="name">Location Name</option>
                  <option value="week">Week Number</option>
                  <option value="saturation">Saturation %</option>
                </select>
                <button
                  type="button"
                  className="sort-toggle-dir"
                  onClick={() => setLocSortAsc(!locSortAsc)}
                  title={locSortAsc ? "Ascending (Click for Descending)" : "Descending (Click for Ascending)"}
                >
                  {locSortAsc ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
                </button>
              </div>
            </label>
          </div>
        </div>

        <div className="table-wrap flex-scroll-table">
          <table>
            <thead>
              <tr>
                <th>Location / Facility</th>
                <th>Type</th>
                <th>Week</th>
                <th>Usage / Supply</th>
                <th>Saturation</th>
                <th>Active Activities</th>
                <th>Possession Groups</th>
              </tr>
            </thead>
            <tbody>
              {filteredLocations.map((u) => {
                const loc = formatLocationName(u.location_id);
                const isSaturated = u.used >= u.capacity;
                return (
                  <tr key={`${u.location_id}-${u.week}`}>
                    <td>
                      <strong>{loc.primary}</strong>
                      <div className="muted" style={{ fontSize: "10px" }}>{u.location_id}</div>
                    </td>
                    <td>
                      <span className="tier-badge" style={{ background: "var(--bg-shell)" }}>
                        {loc.typeTag}
                      </span>
                    </td>
                    <td>Week {u.week}</td>
                    <td>
                      <strong>{u.used}</strong> / {u.capacity} slots
                    </td>
                    <td>
                      <span className={`tier-badge ${isSaturated ? "tier-1" : "tier-3"}`}>
                        {isSaturated ? "100% Full" : `${Math.round((u.used / u.capacity) * 100)}%`}
                      </span>
                    </td>
                    <td>{u.activities.join(", ") || "Protection footprint only"}</td>
                    <td>
                      {Object.entries(u.groups)
                        .map(([g, ids]) => `${g}: ${ids.join(", ")}`)
                        .join("; ") || "—"}
                    </td>
                  </tr>
                );
              })}
              {!filteredLocations.length && (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "24px" }}>
                    No matching location records found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  return null;
}
