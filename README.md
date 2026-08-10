# RailFlow AI

Explainable Railway Maintenance Scheduling System for NEBULA X Hackathon.

RailFlow AI is a web-first, human-in-the-loop scheduling system. Field teams submit maintenance requests through a browser interface, while planners detect conflicts, optimise schedules, compare alternatives, and approve solver-validated changes.

## Architecture

```text
Field Request Created
        ↓
Request Validation
        ↓
Conflict Detection
        ↓
Planner Dashboard Update
        ↓
Optimisation Engine
        ↓
Alternative Schedule Generation
        ↓
Impact Analysis
        ↓
Explanation Generation
        ↓
Planner Approval
        ↓
Final Schedule
```

CSV and JSON are supported as secondary inputs for seed data, official hackathon datasets, and legacy integrations.

```text
CSV / JSON / Official Dataset
        ↓
Adapter Layer
        ↓
Internal Request Model
        ↓
Same Validation + Scheduling Pipeline
```

## Backend

```text
backend/
  app/
    main.py
    domain/
    adapters/
    validation/
    conflict/
    scheduler/
    kpi/
    explanation/
    stress/
    api/
```

Run locally:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Frontend

```text
frontend/
  app/
    page.tsx
    request/new/page.tsx
    dashboard/page.tsx
```

Run locally:

```bash
cd frontend
npm install
npm run dev
```

## MVP Scope

- Web-based maintenance request creation
- Request list management
- Gantt schedule view
- Conflict detection
- OR-Tools scheduling boundary
- KPI before/after structure
- Rule-based explanation layer
- Emergency rescheduling boundary
- Approval, reject, and lock workflow boundary
- CSV import for seed and official data
