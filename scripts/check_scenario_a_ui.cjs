// Optional smoke test: requires Playwright and an installed Chrome browser.
// Run with the development servers already listening on ports 3000 and 8000.
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs/promises");
const { chromium } = require(process.env.RAILFLOW_PLAYWRIGHT_MODULE || "playwright");

(async () => {
  const output = process.env.RAILFLOW_UI_OUTPUT || "/private/tmp/railflow-strategy-ui";
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://127.0.0.1:3000", { waitUntil: "networkidle" });
    await page.getByText("Strategy comparison", { exact: true }).click();
    assert.equal(await page.getByRole("combobox", { name: /^Search method/ }).inputValue(), "alns");
    await page.getByRole("combobox", { name: /^Search method/ }).selectOption("greedy");
    const response = page.waitForResponse((r) => r.url().includes("/api/ps1/jobs?") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Load public dataset", exact: true }).click();
    const created = await (await response).json();
    assert.equal(created.algorithm, "strategies");
    assert.deepEqual(Object.keys(created.scenarios), ["A", "B", "C"]);
    await page.waitForSelector(".job-pill.completed", { timeout: 75000 });
    assert.equal(await page.locator(".scenario-card").count(), 3);
    await page.getByText("Internally validated", { exact: true }).waitFor();
    assert.equal(await page.locator(".comparison-panel tbody tr").count(), 3);
    for (const scenario of ["B", "C"]) {
      await page.locator(".scenario-card").filter({ has: page.locator(".scenario-code", { hasText: scenario }) }).click();
      await page.getByRole("heading", { name: `Scenario ${scenario} search`, exact: true }).waitFor();
      await page.getByRole("heading", { name: "Activity schedule and evidence", exact: true }).waitFor();
      const detailResponse = await page.request.get(`http://127.0.0.1:8000/api/ps1/jobs/${created.job_id}/scenarios/${scenario}`);
      const detail = await detailResponse.json();
      assert.equal(detail.validation.feasible, true);
      assert.equal(typeof detail.validation.soft_scores.objective_score, "number");
      assert.equal(detail.diagnostics.scenario, scenario);
      assert.equal(detail.diagnostics.strategy, "greedy");
    }
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download result ZIP" }).click();
    await (await download).saveAs(path.join(output, "strategies.zip"));

    await page.getByRole("combobox", { name: /^Search method/ }).selectOption("alns");
    await page.getByLabel("Time per scenario").selectOption("15");
    await page.getByLabel("Seed", { exact: true }).fill("11");
    await page.getByRole("button", { name: "Load public dataset", exact: true }).click();
    await page.waitForSelector(".job-pill.running", { timeout: 10000 });
    await page.waitForSelector(".job-pill.completed", { timeout: 75000 });
    await page.screenshot({ path: path.join(output, "strategies-desktop.png"), fullPage: true });

    // A live incumbent survives cancellation.
    await page.getByLabel("Time per scenario").selectOption("120");
    await page.getByRole("button", { name: "Load public dataset", exact: true }).click();
    await page.waitForSelector(".job-pill.running", { timeout: 10000 });
    await page.waitForSelector('a[href$="/download"]:not(.disabled)', { timeout: 10000 });
    await page.getByRole("button", { name: "Stop search" }).click();
    await page.waitForSelector(".job-pill.cancelled", { timeout: 10000 });
    assert.ok(await page.getByRole("link", { name: "Download result ZIP" }).getAttribute("href"));

    // The same selected algorithm accepts the eight uploaded CSVs.
    await page.getByRole("combobox", { name: /^Search method/ }).selectOption("greedy");
    const data = path.resolve(__dirname, "../PS1/01_data");
    const files = (await fs.readdir(data)).filter((name) => name.endsWith(".csv")).map((name) => path.join(data, name));
    await page.locator('input[type="file"]').setInputFiles(files);
    await page.getByRole("button", { name: "Run A, B and C", exact: true }).click();
    await page.waitForSelector(".job-pill.completed", { timeout: 75000 });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, "strategies-mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    await page.getByText("Existing planner", { exact: true }).click();
    assert.equal(await page.locator(".solver-options").count(), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, checks: ["selection", "public run", "A/B/C results and scores", "ZIP download", "ALNS completion", "cancel preserves incumbent", "CSV upload", "mobile layout", "legacy selection"], output }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
