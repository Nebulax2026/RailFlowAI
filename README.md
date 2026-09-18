# RailFlowAI

RailFlowAI is a validator-first railway possession planner for NebulaX 2026 PS1. It accepts the official eight CSV files, generates complete schedules for Scenarios A, B, and C, validates the exported CSVs independently, and produces submission-ready ZIP files.

## Workflow

1. Validate input schemas, references, dates, topology, capacities, and predecessors.
2. Use OR-Tools CP-SAT to assign access weeks, legal co-sharing groups, local nights, and ECLO decisions.
3. Apply the strict weekly-closure policy inferred from official validator feedback.
4. Re-read and validate the exact exported CSV bytes before enabling downloads.

The planner supports the existing CP-SAT solver plus integrated CP-SAT, random LNS, and adaptive LNS comparison runs on the same actual input. The Operations tab retains disruption re-planning and the grounded Schedule Assistant.
The AI Schedule Assistant supports evidence-grounded schedule Q&A and an explicit preview → re-plan → validation workflow. See [Schedule Assistant design](docs/ps1-schedule-assistant.md).

## Submission artifacts

`submission/final-submission/` contains the only upload-ready archives:

- `A.zip` — officially accepted score 608.3
- `B.zip` — officially accepted score 50.0
- `C.zip` — locally validated strict-model score 122.4, pending official confirmation

`manifest.json` records scores, status, and archive hashes. `official-closure-fix` and `official-score-optimized` preserve the supporting validation evidence.

## Architecture

```text
Next.js / React UI → FastAPI API → CP-SAT solver → CSV exporter → independent CSV validator → ZIP
```

## Development

Requirements: Python 3.12 and Node.js 22.

```powershell
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\frontend
npm install
cd ..
npm run dev
```

Open `http://127.0.0.1:3000`. FastAPI runs at `http://127.0.0.1:8000`.

## Documentation

- [Validator policy and official-feedback fix](docs/official-closure-fix.md)
- [Validator specification](docs/validator-spec.md)
- [Solution write-up](docs/solution-writeup.md)
- [Submission short answers](docs/submission-short-answers.md)
- [Demo script](docs/video-pitch.md)
- [Schedule Assistant design](docs/ps1-schedule-assistant.md)
