import os
from functools import lru_cache
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    allowed_origins: list[str] = [
        item.strip()
        for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
        if item.strip()
    ]
    app_password: str | None = os.getenv("APP_PASSWORD")
    app_access_token: str | None = os.getenv("APP_ACCESS_TOKEN")
    session_secret: str = os.getenv("SESSION_SECRET", "change-me-for-production")
    database_url: str | None = os.getenv("DATABASE_URL")

    ai_enabled: bool = _bool_env("AI_ENABLED", False)
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model_primary: str = os.getenv("OPENAI_MODEL_PRIMARY", "gpt-5.4-mini")
    openai_model_fallback: str = os.getenv("OPENAI_MODEL_FALLBACK", "gpt-5.5")
    ai_confidence_fallback_threshold: float = _float_env("AI_CONFIDENCE_FALLBACK_THRESHOLD", 0.70)
    ai_confidence_auto_accept_threshold: float = _float_env("AI_CONFIDENCE_AUTO_ACCEPT_THRESHOLD", 0.90)
    max_ai_rows_per_job: int = _int_env("MAX_AI_ROWS_PER_JOB", 250)
    ai_timeout_seconds: int = _int_env("AI_TIMEOUT_SECONDS", 20)
    ai_max_retries: int = _int_env("AI_MAX_RETRIES", 1)
    ai_batch_size: int = _int_env("AI_BATCH_SIZE", 10)
    ai_daily_cost_limit_usd: float = _float_env("AI_DAILY_COST_LIMIT_USD", 25.0)

    max_upload_mb: int = _int_env("MAX_UPLOAD_MB", 50)
    max_rows_per_job: int = _int_env("MAX_ROWS_PER_JOB", 50000)
    temp_file_ttl_minutes: int = _int_env("TEMP_FILE_TTL_MINUTES", 120)
    temp_root: Path = Path(os.getenv("TEMP_ROOT", "/tmp/cb_failed_assistant"))

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_password or self.app_access_token)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.temp_root.mkdir(parents=True, exist_ok=True)
    return settings

