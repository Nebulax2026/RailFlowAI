# RailFlowAI Cloud Deployment

RailFlowAI ships as one Docker service. The image builds the Next.js workspace as static assets, copies them into FastAPI, and serves the UI and API from one origin. PS1 uploads and generated results remain in memory and expire after 60 minutes, so no database is required.

## Render Blueprint

The root `render.yaml` defines a Docker web service with `/api/health` as its health check. Connect the GitHub repository to Render and create a Blueprint from that file.

Set these values for the final hostname:

```text
RAILFLOW_ALLOWED_HOSTS=<render-hostname>,localhost,127.0.0.1
RAILFLOW_CORS_ORIGINS=https://<render-hostname>
DATAMALL_ACCOUNT_KEY=<optional secret>
```

`DATAMALL_ACCOUNT_KEY` must remain a backend secret. When it is absent or DataMall is unavailable, the service-alert panel reports an unavailable state without affecting scheduling.

## Local Container Check

```bash
docker build -t railflowai .
docker run --rm -p 8000:8000 -e DATAMALL_ACCOUNT_KEY=your-key railflowai
```

Open `http://127.0.0.1:8000` and verify `GET /api/health` returns `{"status":"ok"}`.

## Production Verification

1. Load the bundled public dataset and start a solve job.
2. Confirm Scenarios A, B, and C expose partial results as each completes.
3. Inspect the score, contract table, timeline, heatmap, and occupancy views.
4. Download the combined ZIP and confirm all three scenario directories and `validation_summary.json` are present.
5. Refresh the page and start another job to verify the single-origin API route.
6. Confirm the DataMall panel works with a valid key and degrades cleanly without one.
7. Confirm an expired job returns no downloadable uploaded data or output after 60 minutes.

The service intentionally has no persistent disk or Supabase dependency. Uploaded challenge data is ephemeral and must not be written to logs.
