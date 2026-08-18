import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing, contextmanager
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar

from app.domain.models import AuditEvent, MaintenanceRequest, ProposalSnapshot, ScheduledWork
from app.settings import database_path


T = TypeVar("T", AuditEvent, MaintenanceRequest, ScheduledWork, ProposalSnapshot)

COLLECTION_REQUESTS = "requests"
COLLECTION_SCHEDULED_WORK = "scheduled_work"
COLLECTION_PROPOSAL_SNAPSHOTS = "proposal_snapshots"
COLLECTION_AUDIT_EVENTS = "audit_events"

_lock = RLock()
_db_path = database_path()
_transaction_depth = 0
_dirty_collections: set[str] = set()


def get_database_path() -> Path:
    return _db_path


def initialize_database() -> None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS railflow_state (
                collection TEXT NOT NULL,
                item_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (collection, item_key)
            )
            """
        )


def load_state_from_database() -> dict[str, int]:
    initialize_database()
    requests = _load_collection(COLLECTION_REQUESTS, MaintenanceRequest)
    scheduled_work = _load_collection(COLLECTION_SCHEDULED_WORK, ScheduledWork)
    proposal_snapshots = _load_collection(COLLECTION_PROPOSAL_SNAPSHOTS, ProposalSnapshot)
    audit_events = _load_collection(COLLECTION_AUDIT_EVENTS, AuditEvent)

    REQUESTS.replace_without_persist(requests)
    SCHEDULED_WORK.replace_without_persist(scheduled_work)
    PROPOSAL_SNAPSHOTS.replace_without_persist(proposal_snapshots)
    AUDIT_EVENTS.replace_without_persist(audit_events)
    return {
        "requests": len(REQUESTS),
        "scheduled_work": len(SCHEDULED_WORK),
        "proposal_snapshots": len(PROPOSAL_SNAPSHOTS),
        "audit_events": len(AUDIT_EVENTS),
    }


def save_state_to_database() -> dict[str, int]:
    initialize_database()
    _replace_collection(COLLECTION_REQUESTS, REQUESTS)
    _replace_collection(COLLECTION_SCHEDULED_WORK, SCHEDULED_WORK)
    _replace_collection(COLLECTION_PROPOSAL_SNAPSHOTS, PROPOSAL_SNAPSHOTS)
    _replace_collection(COLLECTION_AUDIT_EVENTS, AUDIT_EVENTS)
    return {
        "requests": len(REQUESTS),
        "scheduled_work": len(SCHEDULED_WORK),
        "proposal_snapshots": len(PROPOSAL_SNAPSHOTS),
        "audit_events": len(AUDIT_EVENTS),
    }


def clear_database_state() -> dict[str, int]:
    initialize_database()
    with _lock, closing(_connect()) as connection, connection:
        connection.execute("DELETE FROM railflow_state")
    REQUESTS.replace_without_persist({})
    SCHEDULED_WORK.replace_without_persist({})
    PROPOSAL_SNAPSHOTS.replace_without_persist({})
    AUDIT_EVENTS.replace_without_persist({})
    return {"requests": 0, "scheduled_work": 0, "proposal_snapshots": 0, "audit_events": 0}


@contextmanager
def persistence_transaction():
    global _transaction_depth
    snapshots = _state_snapshot() if _transaction_depth == 0 else None
    with _lock:
        _transaction_depth += 1
    try:
        yield
    except Exception:
        with _lock:
            _transaction_depth -= 1
            if _transaction_depth == 0:
                _dirty_collections.clear()
                if snapshots is not None:
                    REQUESTS.replace_without_persist(snapshots[COLLECTION_REQUESTS])
                    SCHEDULED_WORK.replace_without_persist(snapshots[COLLECTION_SCHEDULED_WORK])
                    PROPOSAL_SNAPSHOTS.replace_without_persist(snapshots[COLLECTION_PROPOSAL_SNAPSHOTS])
                    AUDIT_EVENTS.replace_without_persist(snapshots[COLLECTION_AUDIT_EVENTS])
        raise
    else:
        with _lock:
            _transaction_depth -= 1
            if _transaction_depth == 0:
                dirty = set(_dirty_collections)
                _dirty_collections.clear()
                _flush_dirty_collections(dirty)


class PersistentDict(dict[str, T], Generic[T]):
    def __init__(self, collection: str) -> None:
        super().__init__()
        self.collection = collection

    def __setitem__(self, key: str, value: T) -> None:
        super().__setitem__(key, value)
        _persist_or_mark_dirty(self.collection, lambda: _upsert_item(self.collection, key, value))

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        _persist_or_mark_dirty(self.collection, lambda: _delete_item(self.collection, key))

    def clear(self) -> None:
        super().clear()
        _persist_or_mark_dirty(self.collection, lambda: _delete_collection(self.collection))

    def pop(self, key: str, default=None):  # type: ignore[no-untyped-def]
        exists = key in self
        value = super().pop(key, default)
        if exists:
            _persist_or_mark_dirty(self.collection, lambda: _delete_item(self.collection, key))
        return value

    def update(self, values: Mapping[str, T] | Iterable[tuple[str, T]] = (), **kwargs: T) -> None:
        items = dict(values, **kwargs)
        for key, value in items.items():
            self[key] = value

    def replace_without_persist(self, values: Mapping[str, T]) -> None:
        dict.clear(self)
        dict.update(self, values)


REQUESTS: PersistentDict[MaintenanceRequest] = PersistentDict(COLLECTION_REQUESTS)
SCHEDULED_WORK: PersistentDict[ScheduledWork] = PersistentDict(COLLECTION_SCHEDULED_WORK)
PROPOSAL_SNAPSHOTS: PersistentDict[ProposalSnapshot] = PersistentDict(COLLECTION_PROPOSAL_SNAPSHOTS)
AUDIT_EVENTS: PersistentDict[AuditEvent] = PersistentDict(COLLECTION_AUDIT_EVENTS)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_db_path)


def _state_snapshot() -> dict[str, dict]:
    return {
        COLLECTION_REQUESTS: dict(REQUESTS),
        COLLECTION_SCHEDULED_WORK: dict(SCHEDULED_WORK),
        COLLECTION_PROPOSAL_SNAPSHOTS: dict(PROPOSAL_SNAPSHOTS),
        COLLECTION_AUDIT_EVENTS: dict(AUDIT_EVENTS),
    }


def _persist_or_mark_dirty(collection: str, operation) -> None:  # type: ignore[no-untyped-def]
    if _transaction_depth > 0:
        _dirty_collections.add(collection)
        return
    operation()


def _flush_dirty_collections(collections: set[str]) -> None:
    if COLLECTION_REQUESTS in collections:
        _replace_collection(COLLECTION_REQUESTS, REQUESTS)
    if COLLECTION_SCHEDULED_WORK in collections:
        _replace_collection(COLLECTION_SCHEDULED_WORK, SCHEDULED_WORK)
    if COLLECTION_PROPOSAL_SNAPSHOTS in collections:
        _replace_collection(COLLECTION_PROPOSAL_SNAPSHOTS, PROPOSAL_SNAPSHOTS)
    if COLLECTION_AUDIT_EVENTS in collections:
        _replace_collection(COLLECTION_AUDIT_EVENTS, AUDIT_EVENTS)


def _load_collection(collection: str, model: type[T]) -> dict[str, T]:
    with _lock, closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT item_key, payload FROM railflow_state WHERE collection = ? ORDER BY item_key",
            (collection,),
        ).fetchall()
    return {key: model.model_validate_json(payload) for key, payload in rows}


def _replace_collection(collection: str, values: Mapping[str, T]) -> None:
    with _lock, closing(_connect()) as connection, connection:
        connection.execute("DELETE FROM railflow_state WHERE collection = ?", (collection,))
        connection.executemany(
            """
            INSERT INTO railflow_state (collection, item_key, payload, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [(collection, key, value.model_dump_json()) for key, value in values.items()],
        )


def _upsert_item(collection: str, key: str, value: T) -> None:
    initialize_database()
    with _lock, closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO railflow_state (collection, item_key, payload, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(collection, item_key)
            DO UPDATE SET payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
            """,
            (collection, key, value.model_dump_json()),
        )


def _delete_item(collection: str, key: str) -> None:
    initialize_database()
    with _lock, closing(_connect()) as connection, connection:
        connection.execute(
            "DELETE FROM railflow_state WHERE collection = ? AND item_key = ?",
            (collection, key),
        )


def _delete_collection(collection: str) -> None:
    initialize_database()
    with _lock, closing(_connect()) as connection, connection:
        connection.execute("DELETE FROM railflow_state WHERE collection = ?", (collection,))


load_state_from_database()
