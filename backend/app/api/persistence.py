from fastapi import APIRouter

from app.storage import clear_database_state, get_database_path, load_state_from_database, save_state_to_database

router = APIRouter()


@router.get("/status")
def persistence_status() -> dict:
    path = get_database_path()
    counts = load_state_from_database()
    return {
        "database_path": str(path),
        "database_exists": path.exists(),
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
