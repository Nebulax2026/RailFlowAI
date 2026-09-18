import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def cors_origins() -> list[str]:
    origins = _csv_env("RAILFLOW_CORS_ORIGINS", ["http://localhost:3000", "http://127.0.0.1:3000"])
    return [origin.rstrip("/") for origin in origins]


def allowed_hosts() -> list[str]:
    hosts = _csv_env("RAILFLOW_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname and render_hostname not in hosts:
        hosts.append(render_hostname)
    return hosts
