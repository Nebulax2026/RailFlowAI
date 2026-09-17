from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api import (
    approvals,
    audit,
    catalog,
    conflicts,
    demo,
    displacement_approvals,
    import_data,
    kpis,
    notifications,
    persistence,
    requests,
    scenarios,
    schedule,
    settings_api,
    stress_test,
)
from app.settings import allowed_hosts, cors_origins
from app.storage import load_state_from_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_state_from_database()
    yield


app = FastAPI(
    title="RailFlow AI API",
    description="Explainable railway maintenance scheduling system.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())

app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
app.include_router(import_data.router, prefix="/api/import", tags=["import"])
app.include_router(persistence.router, prefix="/api/persistence", tags=["persistence"])
app.include_router(conflicts.router, prefix="/api/conflicts", tags=["conflicts"])
app.include_router(demo.router, prefix="/api/demo", tags=["demo"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(displacement_approvals.router, prefix="/api/displacement-approvals", tags=["displacement-approvals"])
app.include_router(scenarios.router, prefix="/api/scenarios", tags=["scenarios"])
app.include_router(stress_test.router, prefix="/api/stress-test", tags=["stress-test"])
app.include_router(kpis.router, prefix="/api/kpis", tags=["kpis"])


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
