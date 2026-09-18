# RailFlowAI

RailFlowAI is a validator-first railway possession planner for NebulaX 2026 Problem Statement 1. It accepts the official eight-file demand book, searches for complete schedules under Scenarios A, B, and C, explains the trade-offs, and exports the exact three CSV files required for each validated scenario.

## What It Does

- Validates all eight PS1 files and their cross-file references before solving.
- Expands activity spans into every tunnel and platform location they occupy.
- Uses OR-Tools CP-SAT to assign access weeks and contract-local access nights.
- Selects legal `PC + C` and `C + C` possessions inside the optimisation model.
- Optimises ECLO jointly with precedence and capacity, including C's per-line two-week windows.
- Applies strict-supply, strict-schedule, and balanced scenario policies.
- Re-parses and independently validates exported CSV bytes before enabling downloads.
- Shows activity timelines/tables, shared possessions, protection footprints, score breakdowns, and location/week evidence.

## Required Input

Upload these files together with their exact names:

```text
01_LINES.csv
02_STATIONS.csv
03_SECTORS.csv
04_LOCATION_SUPPLY.csv
05_BUFFER_LOCATION.csv
06_PARAMETERS.csv
07_PROJECT_DETAILS.csv
08_ACTIVITY_DETAILS.csv
```

The bundled public instance is available through **Load public dataset**.

## Output

Each scenario produces:

```text
SCHEDULE_ACCESS.csv
SCHEDULE_OCCUPANCY.csv
RESULTS.csv
```

The combined download includes only available validated scenarios under `scenario_A/`, `scenario_B/`, and `scenario_C/`. It includes `validation_summary.json` and `manifest.json`, which identifies included scenarios and revisions. Partial results remain downloadable during improvement and after cancellation.

## Architecture

```text
Next.js workspace
      |
FastAPI job API
      |
Strict CSV parser -> topology expansion -> CP-SAT solver
      |                                      |
      +---------- export-level validator <---+
                             |
                   scenario CSVs and ZIP
```

Solve jobs run one at a time and expire after 60 minutes. A/B/C each receive a first search budget of 30 seconds, then up to 90 additional seconds with the incumbent as a hint. Thirty seconds is a first-result target, not a guarantee. Optimal scenarios skip improvement. Cancellation interrupts the active solve; it retains validated results. Uploads remain in memory and are not logged.

## Local Development

The workspace has one search-method selector: Existing planner, Greedy,
integrated CP-SAT, random LNS or adaptive LNS. Each handles A/B/C. The
30 synthetic datasets (10 per scenario) can be downloaded and used for a
one-click average-score comparison, with valid-run counts shown beside averages.
See [dataset suite](datasets/scenario-suite-v1/README.md).
The browser can run one method over all 30 cases or all five methods over 150
case-method pairs. Reported means use only validated outputs and include the
valid-run denominator. A [reproducible batch command](docs/strategy-comparison.md)
can save the same data to JSON.
See [strategy selection and scenario scores](docs/strategy-comparison.md),
[Scenario A usage and benchmarks](docs/scenario-a-usage.md) and
[rule evidence / validation limitations](docs/scenario-a-rules.md).

Requirements: Python 3.11+, Node.js 22+, and npm.

```powershell
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\frontend
npm install
cd ..
npm run dev
```

Open `http://127.0.0.1:3000`. FastAPI and Swagger run at `http://127.0.0.1:8000` and `http://127.0.0.1:8000/docs`.

## Environment

```text
RAILFLOW_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_API_BASE_URL=
RAILFLOW_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
RAILFLOW_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=asia-southeast1
RAILFLOW_GEMINI_MODEL=
```

Scheduling uses the uploaded PS1 CSVs or the bundled public dataset. No external API key is required. When Agent Platform ADC and all three optional Google variables are available, Gemini classifies free-form Schedule Assistant questions; deterministic schedule evidence still produces every answer.

## API

```text
POST   /api/ps1/jobs
GET    /api/ps1/jobs/{job_id}
DELETE /api/ps1/jobs/{job_id}
GET    /api/ps1/jobs/{job_id}/scenarios/{A|B|C}
POST   /api/ps1/jobs/{job_id}/scenarios/{A|B|C}/replans
GET    /api/ps1/jobs/{job_id}/scenarios/{A|B|C}/replans/{replan_id}
GET    /api/ps1/jobs/{job_id}/scenarios/{A|B|C}/replans/{replan_id}/files/{filename}
POST   /api/ps1/jobs/{job_id}/assistant/query
GET    /api/ps1/jobs/{job_id}/download
GET    /api/health
```

Start a public-data run:

```bash
curl -X POST "http://127.0.0.1:8000/api/ps1/jobs?public=true"
```

## Verification

```powershell
cd backend
py -m pytest
cd ..\frontend
npm run lint
npm run build
cd ..
docker build -t railflowai .
```

Generated outputs are accepted only after schema, workload, actual completion dates, weekly allocation, workfront, occupancy, legal mix, cross-contract physical-night safety, work capacity, and ECLO checks pass. Scores are withheld for invalid schedules.

The supplied submission sample is **format-only**, per the user's clarification; it is not a feasible golden answer. We follow the README scheduling rules and independently reconstruct a consistent seven-night assignment from exported CSVs, including cross-contract protection conflicts. The UI and ZIP metadata expose that witness. Work groups alone consume supply. Exact maintenance calendars and the official executable validator are unavailable. See [validation rules](docs/validator-spec.md) and [sample diagnostics](submission/public-results/compatibility_report.json).

Regenerate public results and run reproducible stress probes:

```powershell
py scripts/generate_public_results.py
py scripts/benchmark_ps1.py --seconds 30
```

Public generation uses the same 30+90 second policy. `benchmark.json` records first-feasible time, score, bound, gap, and platform. Stress reports include infeasibility and time-limit outcomes instead of omitting failed cases. Process peak memory is a process-wide measurement, not per-scenario allocation.

## Deployment

The production image builds a static Next.js export and serves it from FastAPI on one origin.

```bash
docker build -t railflowai .
docker run --rm -p 8000:8000 railflowai
```

`render.yaml` defines the hosted Render service. Connect the GitHub repository, create the blueprint, and verify `/api/health` before submitting the generated domain.

## Submission Assets

- Public outputs and ZIP: `submission/public-results/`
- Short solution write-up: `docs/solution-writeup.md`
- 2-3 minute pitch script: `docs/video-pitch.md`
- Product and technical contract: `docs/requirements-design.md`
- Validator rules and known assumptions: `docs/validator-spec.md`
- Implementation checks and remaining limits: `docs/implementation-verification.md`

The official reference validator was not included in the information pack. The app says **Internally validated**. Optimality refers only to the documented conservative model, not to the unknown official benchmark.
