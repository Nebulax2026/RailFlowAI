from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter

router = APIRouter()
DATAMALL_URL = "https://datamall2.mytransport.sg/ltaodataservice/TrainServiceAlerts"
_cache: dict | None = None
_cache_until: datetime | None = None
_lock = threading.Lock()


@router.get("/train-service-alerts")
def train_service_alerts() -> dict:
    global _cache, _cache_until
    key = os.getenv("DATAMALL_ACCOUNT_KEY", "").strip()
    now = datetime.now(UTC)
    if not key:
        return {"configured": False, "available": False, "alerts": [], "message": "DataMall AccountKey is not configured."}
    with _lock:
        if _cache is not None and _cache_until and _cache_until > now:
            return {**_cache, "cached": True}
    try:
        response = httpx.get(DATAMALL_URL, headers={"AccountKey": key, "accept": "application/json"}, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        values = data.get("value", data if isinstance(data, list) else [])
        alerts = [
            {
                "status": item.get("Status"),
                "line": item.get("Line"),
                "direction": item.get("Direction"),
                "stations": item.get("Stations"),
                "message": item.get("Message") or item.get("AdditionalInfo"),
            }
            for item in values
        ]
        payload = {"configured": True, "available": True, "alerts": alerts, "fetched_at": now.isoformat(), "cached": False}
        with _lock:
            _cache = payload
            _cache_until = now + timedelta(seconds=60)
        return payload
    except (httpx.HTTPError, ValueError) as error:
        return {"configured": True, "available": False, "alerts": [], "message": f"DataMall is temporarily unavailable: {type(error).__name__}."}
