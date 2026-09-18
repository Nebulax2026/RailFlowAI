# Planner / Lab UI verification

## Latest main integration

UI changes are based on upstream `07e3cc6`. Lab uses 30 shared datasets,
90 runs per selected method and 450 runs across all methods. Individual rows
include scenario in their display and identity; downloads use the shared ZIP
endpoint. Current upstream CP-SAT runs use eight workers, while Greedy does not
use CP-SAT. The separate local automatic-CPU backend changes are not part of
this UI commit; optional diagnostic configuration remains backwards compatible.

Type checking and a Webpack production build passed in the isolated worktree.
Turbopack rejected the external node_modules junction used only for this checkout.
The browser regression passed again with 90/450 mocked runs, repeated dataset
IDs across scenarios, both desktop sizes, mobile, and worker configuration
compatibility. No actual backend solve was repeated for this main integration.

The following records describe earlier stages of the UI work.

The planner at `/` runs the existing planner with the backend's unchanged time
budget. `/lab` owns algorithm settings, single-input experiments and dataset
comparisons. Both use `schedule-results.tsx`; production components do not import
Lab code. Removing Lab later requires removing its route directory and the
planner's `Test tools` link, plus retiring the Lab-specific smoke checks.

Saved IDs are independent: `railflow-planner-job-id`, `railflow-lab-job-id`, and
the existing `railflow-benchmark-id`. Missing/expired jobs return to input with an
explanation; temporary request failures retain saved IDs. Re-plan inputs, running
re-plans, and Assistant conversations survive policy and detail-tab changes while
the result workspace is mounted. Full page reload restores the primary job, not
re-plan forms or conversation history.

## Checks completed

Worker-auto compatibility follow-up: the result dialog now reads the resolved
worker count, time budget and seed from `diagnostics.config`. Missing diagnostic
fields remain compatible with older jobs and never imply a worker count. Lab
copy distinguishes automatic single-input CPU allocation from the dataset
runner's explicit one-worker budget. Type checking, production build and the
mock browser regression passed again, including numeric, `auto`, and missing
worker configuration. Actual backend solves were not rerun for this follow-up;
the actual-backend results below belong to the original workspace split.

- `npm.cmd --prefix frontend run lint` and `npm.cmd --prefix frontend run build`
  passed. Both `/` and `/lab` are generated.
- Mock-API browser checks passed at 1366×768 and 1920×1080 for all five planner
  tabs, and for the Lab single-input and 150-row dataset views. Document overflow
  and mobile horizontal overflow were checked; screenshots were inspected.
- Verified production does not request benchmark APIs, five methods exist only
  in Lab, separate saved IDs restore, 30/150-case requests work, and cancellation
  targets the dataset endpoint. Running Lab work does not disable the planner.
- Verified activity filters, policy-specific re-plans and Assistant conversation
  retention, long result scrolling, expired-ID recovery, keyboard tab navigation,
  Escape/focus return, and diagnostics for runs without a solution. No browser
  runtime exceptions occurred.
- Actual backend browser/API checks used a separate local backend and an HTTP
  proxy, without replacing API responses. Uploading the eight A01_small CSVs with
  Integrated CP-SAT produced validated A/B/C results. ZIP, revision-specific CSVs,
  diagnostics, Assistant answers, saved Lab job restoration, planner default
  `legacy` execution/cancellation, 150-case creation/cancellation, dataset ZIP and
  raw batch report downloads passed.
- A public Greedy run returned no solution for A/B/C under the current solver.
  This was an actual backend outcome, not a successful schedule benchmark.

Completed re-plan results and long Assistant histories were tested with mocked
responses. The actual backend check did not wait for a full 150-case benchmark or
a completed legacy public solve. No solver, backend API, or dataset was changed;
no commit, push, or deployment was performed.

## Repeat the browser regression

Start the frontend, then run from the repository root in PowerShell:

```powershell
$env:RAILFLOW_CHROMIUM = 'C:/path/to/chrome-headless-shell.exe'
$env:RAILFLOW_UI_BASE = 'http://127.0.0.1:3000'
node scripts/check_workspace_ui.cjs
```

This test uses Chromium's DevTools pipe with mock responses and needs no extra
npm packages. Screenshots go to a temporary directory unless `RAILFLOW_UI_OUTPUT`
is set. The real-API `scripts/check_dataset_suite_ui.cjs` smoke test has also been
updated for `/lab`, shared policy controls and the diagnostics dialog; it requires
Playwright and a running current backend. That longer smoke script was not run
end-to-end in this verification.
