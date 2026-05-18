from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    metis_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    token_encryption_key: str = ""

    max_video_duration_seconds: int = 30 * 60
    max_video_bytes: int = 500 * 1024 * 1024
    max_jobs_per_user_per_day: int = 10
    max_active_jobs_per_user: int = 2
    local_artifact_dir: Path = Field(default=Path("./tmp/artifacts"))
    artifact_retention_hours: int = 6
    metis_parallel_chunks: int = 3
    audio_chunk_seconds: int = 60
    metis_poll_interval_seconds: int = 5
    metis_timeout_seconds: int = 30 * 60
    active_job_stale_minutes: int = 20
    session_cookie_name: str = "uptube_user_id"
    oauth_state_cookie_name: str = "uptube_oauth_state"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.database_url:
        settings.database_url = f"sqlite:///{PROJECT_ROOT / 'backend' / 'uptube.db'}"
    elif settings.database_url == "sqlite:///./uptube.db":
        settings.database_url = f"sqlite:///{PROJECT_ROOT / 'backend' / 'uptube.db'}"
    return settings
