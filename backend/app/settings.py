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


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def cors_origins() -> list[str]:
    origins = _csv_env("RAILFLOW_CORS_ORIGINS", ["http://localhost:3000", "http://127.0.0.1:3000"])
    return [origin.rstrip("/") for origin in origins]


def allowed_hosts() -> list[str]:
    hosts = _csv_env("RAILFLOW_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname and render_hostname not in hosts:
        hosts.append(render_hostname)
    return hosts


def hosted_environment() -> bool:
    return _bool_env("RENDER", False) or _bool_env("RAILFLOW_HOSTED", False)


def demo_controls_enabled() -> bool:
    if hosted_environment():
        return False
    return _bool_env("RAILFLOW_DEMO_CONTROLS_ENABLED", True)


def database_url() -> str | None:
    value = os.getenv("DATABASE_URL")
    return value.strip() if value and value.strip() else None


def database_path() -> Path:
    configured = os.getenv("RAILFLOW_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / ".railflow" / "railflow.sqlite3"
