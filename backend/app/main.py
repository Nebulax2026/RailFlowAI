from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import datamall, ps1
from app.settings import allowed_hosts, cors_origins


app = FastAPI(
    title="RailFlow AI API",
    description="PS1 railway track access optimisation and validation service.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())

app.include_router(ps1.router, prefix="/api/ps1", tags=["ps1"])
app.include_router(datamall.router, prefix="/api/datamall", tags=["datamall"])


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
if STATIC_DIR.exists():
    app.mount("/_next", StaticFiles(directory=STATIC_DIR / "_next"), name="next-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def static_frontend(path: str):
        candidate = STATIC_DIR / path
        if candidate.is_dir():
            candidate = candidate / "index.html"
        elif not candidate.suffix:
            candidate = STATIC_DIR / path / "index.html"
        if candidate.is_file() and STATIC_DIR in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
