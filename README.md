# RailFlow AI

Explainable Railway Maintenance Scheduling System for NEBULA X Hackathon.

RailFlow AI is a web-first, human-in-the-loop scheduling system. Field teams submit maintenance requests through a browser interface, while planners generate schedules, inspect conflicts, compare alternatives, and approve solver-validated changes.

## Current Workflow

```text
New Request submitted
        |
Request is validated and saved to SQLite
        |
Request appears in the Planning Board queue
        |
Schedule Manager clicks Generate Schedule
        |
Backend creates tentative scheduled work
        |
Manager reviews conflicts, proposals, KPIs, and affected work
        |
Manager approves selected tentative work into locked baseline
```

New requests do not appear on the calendar immediately. They are queued first, then placed on the calendar only after `Generate Schedule` or an applied proposal creates `scheduled_work`.

Planning times are interpreted and displayed in Singapore time (`Asia/Singapore`, UTC+08:00). `earliest_start` is the earliest allowed start, not a fixed start. The scheduler may place work later in the allowed window, preferring the standard engineering window when it fits.

## Project Layout

```text
backend/
  app/
    main.py
    api/
    domain/
    adapters/
    validation/
    conflict/
    scheduler/
    kpi/
    explanation/
    stress/
  tests/

frontend/
  app/
    page.tsx
    request/new/page.tsx
    dashboard/page.tsx

data/
  sample_requests.csv
```

## Environment

Copy `.env.example` when local overrides are needed.

```bash
copy .env.example .env
```

Important variables:

```text
RAILFLOW_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_API_BASE_URL=
RAILFLOW_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
RAILFLOW_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
RAILFLOW_DB_PATH=backend/.railflow/railflow.sqlite3
```

By default, the frontend calls same-origin `/api/*` and Next.js rewrites those requests to `RAILFLOW_API_BASE_URL`. Leave `NEXT_PUBLIC_API_BASE_URL` empty unless the browser must call a backend directly.

## Install

Backend:

```bash
cd backend
# Windows: py -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS:   python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

Frontend:

```bash
cd frontend
npm install
```

## Run Locally

Run both backend and frontend from the repository root:

```bash
npm run dev
```

Default URLs:

```text
Frontend: http://127.0.0.1:3000
Backend:  http://127.0.0.1:8000
Swagger:  http://127.0.0.1:8000/docs
```

Run services separately:

```bash
npm run dev:backend
npm run dev:frontend
```

Or run the backend directly:

```bash
cd backend
# Windows: py -m uvicorn app.main:app --reload
# macOS:   python3 -m uvicorn app.main:app --reload
```

## Test And Build

Backend tests:

```bash
cd backend
# Windows: py -m pytest
# macOS:   python3 -m pytest
```

Frontend type-check:

```bash
cd frontend
npm run lint
```

Frontend production build:

```bash
cd frontend
npm run build
```

## Demo Data

The Planning Board has dashboard controls for deterministic demo state:

```text
Seed Demo -> load sample locked, tentative, and pending/conflicting work
Reset     -> clear demo state
```

Equivalent API endpoints:

```text
POST /api/demo/seed
POST /api/demo/reset
```

Basic demo click path:

```text
Seed Demo
Select pending request(s)
Show Proposals
Apply Proposal as Schedule Manager
Select tentative calendar tasks
Approve Selected
```

## Persistence

RailFlow stores state in SQLite:

```text
backend/.railflow/railflow.sqlite3
```

Persistence endpoints:

```text
GET  /api/persistence/status
POST /api/persistence/save
POST /api/persistence/load
POST /api/persistence/clear
```

## Imports

CSV and JSON are supported through API endpoints. Until the import UI is built, use Swagger at `http://127.0.0.1:8000/docs`.

```text
POST /api/import/preview
POST /api/import/confirm
POST /api/import/json/preview
POST /api/import/json/confirm
```

Sample CSV:

```text
data/sample_requests.csv
```

## Troubleshooting

`Failed to fetch` from New Request usually means the backend is not running or the frontend dev server needs a restart after `next.config.ts` changed. Run `npm run dev` from the repository root.

`Could not load planning board data.` means one dashboard API failed. Check these endpoints:

```text
GET  /api/requests
GET  /api/schedule
POST /api/conflicts/detect
GET  /api/kpis
```

If browser requests hit the backend directly, make sure `RAILFLOW_CORS_ORIGINS` includes the frontend origin. The default Next.js proxy avoids most local CORS issues.

If Python cannot import `app.main`, run the backend from `backend/` or use the root script:

```bash
npm run dev:backend
```

If frontend dependencies are missing, run:

```bash
cd frontend
npm.cmd install
```

If backend dependencies are missing, run:

```bash
cd backend
py -m pip install -r requirements.txt
```
