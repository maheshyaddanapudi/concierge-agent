"""Application configuration — env-only secrets (spec §13).

Provider API keys live exclusively in environment variables: never in the
database, never in the UI, never logged.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/concierge"
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    openai_api_key: str | None = None
    fake_llm_enabled: bool = False
    langsmith_api_key: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    workspace_dir: str = "/workspace"
    backend_port: int = 8000
    frontend_port: int = 5173
    log_level: str = "INFO"


@lru_cache
def get_config() -> AppConfig:
    return AppConfig()
