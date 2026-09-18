// Optional Chrome smoke check. Requires Playwright via RAILFLOW_PLAYWRIGHT_MODULE.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.RAILFLOW_PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const output = process.env.RAILFLOW_UI_OUTPUT || '/private/tmp/railflow-dataset-ui';
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const baseUrl = process.env.RAILFLOW_UI_BASE || 'http://127.0.0.1:3000';
    await page.goto(`${baseUrl}/lab`, { waitUntil: 'networkidle' });
    const picker = page.getByRole('combobox', { name: /^Search method/ });
    assert.equal(await picker.locator('option').count(), 4);
    assert.equal(await picker.inputValue(), 'legacy');
    await picker.selectOption('integrated');
    const inputDir = path.resolve(__dirname, '../datasets/scenario-suite-v1/cases/D01_small/input');
    const inputFiles = (await fs.readdir(inputDir)).filter(name => name.endsWith('.csv')).map(name => path.join(inputDir, name));
    await page.getByLabel('Select demand book CSV files').setInputFiles(inputFiles);
    await page.getByRole('button', { name: 'Run demand book', exact: true }).click();
    await page.waitForSelector('.job-pill.completed', { timeout: 30000 });
    assert.equal(await page.locator('.comparison-panel').last().locator('tbody tr').count(), 3);
    for (const scenario of ['B', 'C']) {
      await page.locator('.policy-select').filter({ has: page.locator('.scenario-code', { hasText: scenario }) }).click();
      await page.getByRole('button', { name: 'Result details', exact: true }).click();
      await page.getByRole('heading', { name: `Scenario ${scenario} search`, exact: true }).waitFor();
      await page.getByRole('button', { name: 'Close result details' }).click();
    }
    await page.getByRole('button', { name: 'Dataset suite', exact: true }).click();
    await picker.selectOption('integrated');
    const created = page.waitForResponse(r => r.url().includes('/api/ps1/benchmark/runs?') && r.request().method() === 'POST');
    await page.getByRole('button', { name: /Run selected method/ }).click();
    const started = await (await created).json();
    assert.equal(started.rows.length, 90);
    await page.getByText('90/90 finished').waitFor({ timeout: 600000 });
    const response = await page.request.get(`${baseUrl}/api/ps1/benchmark/runs/${started.id}`);
    const report = await response.json();
    assert.ok(['completed', 'partial'].includes(report.status));
    assert.equal(report.summary.length, 3);
    assert.deepEqual(report.summary.map(x => x.finished), [30, 30, 30]);
    for (const row of report.summary) {
      assert.ok(row.valid >= 0 && row.valid <= 30);
      assert.equal(row.mean_score === null, row.valid === 0);
    }
    const download = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Download all 30 shared datasets' }).click();
    await (await download).saveAs(path.join(output, 'all-30-inputs.zip'));
    const allResponse = page.waitForResponse(r => r.url().includes('/api/ps1/benchmark/runs?') && r.request().method() === 'POST');
    await page.getByRole('button', { name: /Compare all 4 methods/ }).click();
    const all = await (await allResponse).json();
    assert.equal(all.rows.length, 360);
    assert.equal(all.summary.length, 12);
    await page.getByRole('button', { name: 'Stop comparison' }).click();
    await page.getByText('Dataset results · cancelled').waitFor();
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, checks: ['four methods merged', 'uploaded D01 A/B/C scores', '30-case averages', 'success denominators', 'dataset ZIP', '360-run setup', 'cancel', 'mobile'], output }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
