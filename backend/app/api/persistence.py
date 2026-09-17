from fastapi import APIRouter, HTTPException

from app.settings import hosted_environment
from app.storage import (
    clear_database_state,
    get_database_backend,
    get_database_path,
    load_state_from_database,
    persistence_counts,
    save_state_to_database,
)

router = APIRouter()


@router.get("/status")
def persistence_status() -> dict:
    path = get_database_path()
    backend = get_database_backend()
    return {
        "database_backend": backend,
        "database_path": str(path) if backend == "sqlite" else None,
        "database_exists": path.exists() if backend == "sqlite" else True,
        **persistence_counts(),
    }


def require_local_persistence_controls() -> None:
    if hosted_environment():
        raise HTTPException(status_code=403, detail="Manual persistence controls are disabled in hosted environments.")


@router.post("/save")
def save_persistence_state() -> dict:
    require_local_persistence_controls()
    counts = save_state_to_database()
    return {"saved": True, **counts}


@router.post("/load")
def load_persistence_state() -> dict:
    require_local_persistence_controls()
    counts = load_state_from_database()
    return {"loaded": True, **counts}


@router.post("/clear")
def clear_persistence_state() -> dict:
    require_local_persistence_controls()
    counts = clear_database_state()
    return {"cleared": True, **counts}
