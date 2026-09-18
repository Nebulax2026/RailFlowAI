# RailFlowAI

RailFlowAI is a validator-first railway possession planner for NebulaX 2026 Problem Statement 1. It accepts the official eight-file demand book, schedules every activity under Scenarios A, B, and C, explains the trade-offs, and exports the exact three CSV files required for each scenario.

## What It Does

- Validates all eight PS1 files and their cross-file references before solving.
- Expands activity spans into every tunnel and platform location they occupy.
- Uses OR-Tools CP-SAT to assign access weeks and contract-local access nights.
- Packs legal `PC + C` and `C + C` co-sharing possessions.
- Applies strict-supply, strict-schedule, and balanced scenario policies.
- Re-parses and independently validates exported CSV bytes before enabling downloads.
- Shows contract completion, weekly workload, capacity hotspots, and plain-language explanations.
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

The combined download uses `scenario_A/`, `scenario_B/`, and `scenario_C/` directories and includes `validation_summary.json`.

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

Solve jobs run one at a time, expose scenario progress independently, and expire after 60 minutes. Uploads are held only in memory and are not logged.

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

The supplied feasible submission is a golden validator fixture. Generated outputs are accepted only after workload, dates, weekly allocation, workfront, occupancy, capacity, ECLO, completion, and schema checks pass.

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

The official reference validator was not included in the information pack. RailFlowAI therefore uses the published rules and organizers' feasible sample as its parity baseline.
