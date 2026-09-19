# RailFlowAI Cloud Deployment

RailFlowAI ships as a single containerized Docker service deployed on **Google Cloud Run**. The container builds Next.js as static assets, mounts them inside FastAPI, and serves both the frontend UI and REST API from a single unified origin. All uploaded CSVs and generated possession schedules reside safely in ephemeral memory (TTL: 60 minutes), requiring zero database (SQLite/Postgres) or persistent disk dependencies.

## Live Deployment

- **Production URL**: [https://railflowai-671082007167.asia-southeast1.run.app/](https://railflowai-671082007167.asia-southeast1.run.app/)
- **GCP Region**: `asia-southeast1` (Singapore)
- **Health Check Endpoint**: `GET /api/health` → `{"status":"ok"}`

## Architecture & Configuration

The service leverages Google Cloud Run's container execution environment:

```text
Google Cloud Run (asia-southeast1)
└── Single Docker Container
    ├── Static UI (Next.js 16 + React 19 Static Export)
    ├── FastAPI 1.0 (Port 8000 via $PORT)
    ├── OR-Tools CP-SAT Solver (Multi-threaded)
    └── Vertex AI / Gemini Integration (Optional AI Assistant mode)
```

### Environment Variables

| Variable | Recommended Cloud Run Value | Purpose |
|---|---|---|
| `PORT` | `8000` (injected automatically by Cloud Run) | Port for FastAPI / Uvicorn server |
| `RAILFLOW_ALLOWED_HOSTS` | `*.run.app,localhost,127.0.0.1` | Host header security check |
| `RAILFLOW_CORS_ORIGINS` | `https://railflowai-671082007167.asia-southeast1.run.app` | CORS origins |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID | Enables Gemini Agent Schedule Assistant via Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | `asia-southeast1` | Vertex AI model region |
| `RAILFLOW_GEMINI_MODEL` | `gemini-2.5-flash` | Model for plain-English schedule queries |

## Local Container Check

```bash
docker build -t railflowai .
docker run --rm -p 8000:8000 railflowai
```

Open `http://127.0.0.1:8000` and verify `GET /api/health` returns `{"status":"ok"}`.

## Production Verification

1. Open `https://railflowai-671082007167.asia-southeast1.run.app/`.
2. Load the bundled public dataset and start a solve job.
3. Confirm Scenarios A, B, and C expose live progress and verified metrics.
4. Inspect the score trajectory, contract table, timeline, heatmap, and occupancy views.
5. Download the final submission ZIP and confirm all scenario files and `manifest.json` are present.
6. Verify the AI Schedule Assistant answers natural-language queries grounded on schedule facts.
7. Confirm expired jobs cleanly purge in-memory caches without data leakage.
