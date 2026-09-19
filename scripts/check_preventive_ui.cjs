// End-to-end browser regression for the D/E comparison with a mocked API.
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const executable = process.env.RAILFLOW_CHROMIUM;
if (!executable) throw new Error("Set RAILFLOW_CHROMIUM to a Chromium executable.");
const baseUrl = process.env.RAILFLOW_UI_BASE || "http://127.0.0.1:3000";
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "railflow-preventive-ui-"));
const child = spawn(executable, ["--headless=new", `--user-data-dir=${profile}`, "--remote-debugging-pipe", "--no-sandbox", "--disable-gpu"], {
  stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"], windowsHide: true
});
child.stderr.on("data", () => {});
let id = 0, buffer = "", session;
const pending = new Map();
const errors = [];
let tradeoffRequests = 0;
let failedComparison = false;

function send(method, params = {}, sessionId = session) {
  return new Promise((resolve, reject) => {
    const requestId = ++id;
    pending.set(requestId, { resolve, reject });
    child.stdio[3].write(JSON.stringify({ id: requestId, method, params, ...(sessionId ? { sessionId } : {}) }) + "\0");
  });
}

const scoresD = { project_objective_score: 608.3, total_project_overrun_days: 21, on_time_maintenance_count: 6840,
  deferred_maintenance_count: 0, total_maintenance_deferral_days: 0, maximum_maintenance_deferral_days: 0 };
const scoresE = { ...scoresD, deferred_maintenance_count: 2, on_time_maintenance_count: 6838,
  total_maintenance_deferral_days: 3, maximum_maintenance_deferral_days: 2 };
const run = () => ({ status: "completed", progress: 100, message: "Validated result available.", feasible: true,
  phase: "finished", termination_reason: "optimal", solution_revision: 1, objective_score: 608.3, solver_stats: {}, scores: {} });
function currentJob() {
  const failed = { ...run(), status: "failed", feasible: false, message: "No validated result.", error: "Deliberate E failure." };
  return { job_id: failedComparison ? "preventive-ui-failed-job" : "preventive-ui-job", job_kind: "preventive",
    status: failedComparison ? "failed" : "completed", algorithm: "preventive_cp_sat",
    solver_config: { time_limit_seconds: 120, seed: 42, workers: 8 }, source: "preventive_tradeoff_public", expires_at: "2027-01-01T00:00:00Z",
    instance: { lines: 2, stations: 20, sectors: 18, locations: 76, contracts: 14, activities: 54, total_accesses: 192,
      horizon_start: "2027-01-04", horizon_weeks: 30 }, scenarios: { D: run(), E: failedComparison ? failed : run() } };
}
function detail(scenario) {
  return { scenario, job_kind: "preventive", status: "completed", solution_revision: 1, phase: "finished",
    termination_reason: "optimal", solver_stats: { optimal: true, search_workers: 8 }, validation: { feasible: true, hard_violations: [],
      soft_scores: scenario === "D" ? scoresD : scoresE, detail: { safety_status: "verified", experimental: true } },
    project_results: [], project_accesses: [], maintenance: [],
    downloads: ["PROJECT_ACCESS_DETAIL.csv", "MAINTENANCE_SCHEDULE.csv", "VALIDATION.json"] };
}
const tradeoff = { title: "Scenario D vs E Trade-off", metrics: {
  project_objective_score: { D: 608.3, E: 608.3, delta_E_minus_D: 0 },
  deferred_maintenance_count: { D: 0, E: 2, delta_E_minus_D: 2 },
  total_maintenance_deferral_days: { D: 0, E: 3, delta_E_minus_D: 3 }
}, project_schedule_impact: "The validated project objective is unchanged.",
preventive_maintenance_impact: "Scenario E adds 3 total maintenance deferral days versus D.",
summary: "D protects maintenance; E protects the project objective first.", optimality_proved: { D: true, E: true } };
tradeoff.schedule_difference_summary = { project_accesses_changed: 1, maintenance_occurrences_changed: 1 };
tradeoff.project_schedule_differences = [{ activity_id: "PMD05", access_seq: 1,
  D: { week: 2, physical_day: 1, access_date: "2027-01-11" },
  E: { week: 1, physical_day: 7, access_date: "2027-01-10" }, moved_days_E_minus_D: -1 }];
tradeoff.maintenance_schedule_differences = [{ occurrence_id: "PM-001-SUN-001", location_id: "SEC:ALP:S01_S02:EB",
  planned_date: "2027-01-10", D: { actual_date: "2027-01-10", deferral_days: 0 },
  E: { actual_date: "2027-01-11", deferral_days: 1 }, moved_days_E_minus_D: 1 }];

async function intercept(message) {
  if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text);
  if (message.method !== "Fetch.requestPaused") return;
  const { requestId, request } = message.params;
  const url = new URL(request.url);
  let payload = currentJob();
  if (/\/scenarios\/D$/.test(url.pathname)) payload = detail("D");
  else if (/\/scenarios\/E$/.test(url.pathname)) payload = detail("E");
  else if (url.pathname.endsWith("/preventive-tradeoff")) { payload = tradeoff; tradeoffRequests += 1; }
  await send("Fetch.fulfillRequest", { requestId, responseCode: 200,
    responseHeaders: [{ name: "Content-Type", value: "application/json" }],
    body: Buffer.from(JSON.stringify(payload)).toString("base64") }, message.sessionId);
}

child.stdio[4].on("data", (data) => {
  buffer += data.toString();
  let at;
  while ((at = buffer.indexOf("\0")) >= 0) {
    const raw = buffer.slice(0, at); buffer = buffer.slice(at + 1);
    if (!raw) continue;
    const message = JSON.parse(raw);
    if (message.id) {
      const item = pending.get(message.id); pending.delete(message.id);
      if (message.error) item.reject(Error(JSON.stringify(message.error))); else item.resolve(message.result);
    } else intercept(message).catch((error) => errors.push(error.message));
  }
});

async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(expression) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await pause(50);
  }
  throw Error(`Timed out: ${expression}`);
}

(async () => {
  try {
    const target = await send("Target.createTarget", { url: "about:blank" }, null);
    session = (await send("Target.attachToTarget", { targetId: target.targetId, flatten: true }, null)).sessionId;
    await send("Page.enable"); await send("Runtime.enable");
    await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/ps1/*" }] });
    await send("Page.navigate", { url: baseUrl }); await pause(300);
    await evaluate("localStorage.clear(); location.reload()");
    await until("Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('Run Preventive Maintenance Comparison') && !b.disabled)");
    await evaluate("Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Run Preventive Maintenance Comparison')).click()");
    await until("document.querySelector('[role=dialog]')");
    assert.equal(await evaluate("document.querySelectorAll('.preventive-card').length"), 2);
    assert.ok(await evaluate("Array.from(document.querySelectorAll('.preventive-worker-note')).every(e => e.textContent.includes('8 CP-SAT workers'))"));
    assert.ok(await evaluate("document.querySelector('.schedule-comparison').textContent.includes('PMD05')"));
    assert.ok(await evaluate("document.querySelector('.schedule-comparison').textContent.includes('SEC:ALP:S01_S02:EB')"));
    assert.equal(await evaluate("document.querySelector('[role=dialog]').getAttribute('aria-modal')"), "true");
    assert.ok(await evaluate("document.querySelector('[role=dialog]').textContent.includes('Deferred maintenance')"));
    assert.ok(await evaluate("document.activeElement.getAttribute('aria-label') === 'Close trade-off'"));
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
    await pause(100);
    assert.equal(await evaluate("document.querySelector('[role=dialog]') === null"), true);
    assert.ok(await evaluate("document.activeElement.textContent.includes('View trade-off')"));
    await pause(1500);
    assert.equal(tradeoffRequests, 1);
    assert.equal(await evaluate("document.querySelector('[role=dialog]') === null"), true);
    failedComparison = true;
    await evaluate("Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Change Data')).click()");
    await until("Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('Run Preventive Maintenance Comparison'))");
    await evaluate("Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Run Preventive Maintenance Comparison')).click()");
    await until("document.querySelector('.preventive-terminal-error')");
    assert.equal(await evaluate("document.querySelector('[role=dialog]') === null"), true);
    assert.ok(await evaluate("document.querySelector('.preventive-terminal-error').textContent.includes('unavailable')"));
    assert.equal(tradeoffRequests, 1);
    assert.equal(errors.length, 0, errors.join("; "));
    console.log("PASS preventive D/E cards, metrics, auto-open-once modal, Escape/focus restoration, and failed-run handling");
  } finally {
    child.kill();
    fs.rmSync(profile, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
