from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, conflicts, import_data, kpis, requests, scenarios, schedule, stress_test


app = FastAPI(
    title="RailFlow AI API",
    description="Explainable railway maintenance scheduling system.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
app.include_router(import_data.router, prefix="/api/import", tags=["import"])
app.include_router(conflicts.router, prefix="/api/conflicts", tags=["conflicts"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
app.include_router(scenarios.router, prefix="/api/scenarios", tags=["scenarios"])
app.include_router(stress_test.router, prefix="/api/stress-test", tags=["stress-test"])
app.include_router(kpis.router, prefix="/api/kpis", tags=["kpis"])


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
