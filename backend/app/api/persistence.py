from fastapi import APIRouter

from app.storage import (
    clear_database_state,
    get_database_backend,
    get_database_path,
    load_state_from_database,
    save_state_to_database,
)

router = APIRouter()


@router.get("/status")
def persistence_status() -> dict:
    path = get_database_path()
    backend = get_database_backend()
    counts = load_state_from_database()
    return {
        "database_backend": backend,
        "database_path": str(path) if backend == "sqlite" else None,
        "database_exists": path.exists() if backend == "sqlite" else True,
        **counts,
    }


@router.post("/save")
def save_persistence_state() -> dict:
    counts = save_state_to_database()
    return {"saved": True, **counts}


@router.post("/load")
def load_persistence_state() -> dict:
    counts = load_state_from_database()
    return {"loaded": True, **counts}


@router.post("/clear")
def clear_persistence_state() -> dict:
    counts = clear_database_state()
    return {"cleared": True, **counts}
