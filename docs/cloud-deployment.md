# RailFlowAI Cloud Deployment

This deployment is intended for the shared coursework demonstration environment. It does not add authentication and must run a single backend instance because application state is cached in memory between transactional database writes.

## Architecture

- Supabase PostgreSQL stores shared application state.
- Render runs one FastAPI backend instance.
- Vercel runs the Next.js frontend.
- The frontend proxies `/api/*` to Render using the server-only `RAILFLOW_API_BASE_URL` value.
- The dashboard silently reloads shared state every 15 seconds while the tab is visible.

## 1. Supabase

1. Create a free project in the Singapore region.
2. Disable the Data API and automatic table exposure; RailFlowAI connects directly to PostgreSQL.
3. Open **Connect**, choose **Session pooler**, and copy the PostgreSQL connection string.
4. Replace the password placeholder locally when entering the value in Render. Never commit or paste the completed URL into GitHub, frontend configuration, logs, or documentation.

No table needs to be created manually. FastAPI creates `railflow_state` on startup. PostgreSQL uses a `JSONB` payload column; local SQLite continues using text-encoded JSON.

## 2. Render backend

The root `render.yaml` defines the backend service with `rootDir: backend`, Singapore region, the health check at `/api/health`, and one instance.

Set these Render environment values:

```text
DATABASE_URL=<Supabase session-pooler URL; secret>
RAILFLOW_CORS_ORIGINS=<deployed Vercel origin>
RAILFLOW_HOSTED=true
RAILFLOW_DEMO_CONTROLS_ENABLED=false
```

Do not add a persistent disk. Supabase is the durable store. Keep the service at one instance; multiple instances would retain separate in-memory copies.

## 3. Vercel frontend

The repository is organization-owned, so the frontend can be deployed manually from `frontend/` without connecting the GitHub organization.

1. Install or invoke the Vercel CLI.
2. From `frontend/`, link or create the Vercel project.
3. Add this server-side environment value for Preview and Production:

```text
RAILFLOW_API_BASE_URL=https://<render-service>.onrender.com
```

4. Leave `NEXT_PUBLIC_API_BASE_URL` empty. This keeps the backend target out of the browser bundle and uses the same-origin `/api/*` rewrite.
5. Deploy a preview, verify it, then promote or deploy to production.

## Hosted safety behavior

When `RAILFLOW_HOSTED=true` or Render's built-in `RENDER=true` is present:

- `POST /api/demo/seed` returns `403`.
- `POST /api/demo/reset` returns `403`.
- `POST /api/persistence/save` returns `403`.
- `POST /api/persistence/load` returns `403`.
- `POST /api/persistence/clear` returns `403`.
- `GET /api/persistence/status` remains available and never returns the database URL.

## Verification

1. Confirm `GET /api/health` returns `{"status":"ok"}`.
2. Confirm `GET /api/persistence/status` reports `database_backend: postgresql` and no database path or URL.
3. Submit a request, restart the Render backend, and confirm the request remains.
4. Open the Vercel site in two browsers. Make a change in one and confirm the other shows it within 15 seconds while visible.
5. Verify schedule generation, urgent approval/rejection, CSV and JSON imports, and D+3 freezing.
6. Verify every hosted demo/reset/persistence mutation endpoint listed above returns `403`.
7. Search GitHub, frontend build output, Render logs, and API responses for the database hostname and password. Neither should appear.

Render free services can sleep after inactivity. The first request after sleeping can take longer while the backend starts.
