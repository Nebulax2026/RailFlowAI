import os


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def cors_origins() -> list[str]:
    return _csv_env("RAILFLOW_CORS_ORIGINS", ["http://localhost:3000", "http://127.0.0.1:3000"])


def allowed_hosts() -> list[str]:
    return _csv_env("RAILFLOW_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])


def cp_sat_time_limit_seconds() -> float:
    value = os.getenv("RAILFLOW_CP_SAT_TIME_LIMIT_SECONDS")
    if not value:
        return 10.0
    try:
        return max(0.1, float(value))
    except ValueError:
        return 10.0
