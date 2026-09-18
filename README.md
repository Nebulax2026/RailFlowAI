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
- Displays LTA DataMall train service alerts as context only; live data never changes synthetic PS1 inputs.

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
FastAPI job API ---- LTA DataMall context proxy
      |
Strict CSV parser -> topology expansion -> CP-SAT solver
      |                                      |
      +---------- export-level validator <---+
                             |
                   scenario CSVs and ZIP
```

Solve jobs run one at a time and expire after 60 minutes. A/B/C each receive a first search budget of 30 seconds, then up to 90 additional seconds with the incumbent as a hint. Thirty seconds is a first-result target, not a guarantee. Optimal scenarios skip improvement. Cancellation interrupts the active solve; it retains validated results. Uploads remain in memory and are not logged.

## Local Development

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
DATAMALL_ACCOUNT_KEY=
```

`DATAMALL_ACCOUNT_KEY` is optional. It remains server-side and is never returned to the browser.

## API

```text
POST   /api/ps1/jobs
GET    /api/ps1/jobs/{job_id}
DELETE /api/ps1/jobs/{job_id}
GET    /api/ps1/jobs/{job_id}/scenarios/{A|B|C}
GET    /api/ps1/jobs/{job_id}/download
GET    /api/datamall/train-service-alerts
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

Generated outputs are accepted only after schema, workload, actual completion dates, weekly allocation, workfront, occupancy, legal mix, protection reservations, capacity, and ECLO checks pass. Scores are withheld for invalid schedules.

The organizers describe their sample as feasible. Our explicit conservative protection policy reports compatibility differences against it; it is a compatibility fixture, not a claimed parity certificate. See [validator assumptions](docs/validator-spec.md) and [compatibility report](submission/public-results/compatibility_report.json). In particular, protection-only slots constrain safety supply while the published excess-access penalty counts exported work possessions. The official executable validator is unavailable.

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
docker run --rm -p 8000:8000 -e DATAMALL_ACCOUNT_KEY=your-key railflowai
```

`render.yaml` defines the hosted Render service. Connect the GitHub repository, create the blueprint, set `DATAMALL_ACCOUNT_KEY` as a secret, and verify `/api/health` before submitting the generated domain.

## Submission Assets

- Public outputs and ZIP: `submission/public-results/`
- Short solution write-up: `docs/solution-writeup.md`
- 2-3 minute pitch script: `docs/video-pitch.md`
- Product and technical contract: `docs/requirements-design.md`
- Validator rules and known assumptions: `docs/validator-spec.md`
- Implementation checks and remaining limits: `docs/implementation-verification.md`

The official reference validator was not included in the information pack. The app says **Internally validated**. Optimality refers only to the documented conservative model, not to the unknown official benchmark.
