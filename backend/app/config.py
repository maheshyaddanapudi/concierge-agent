"""Application configuration — env-only secrets (spec §13).

Provider API keys live exclusively in environment variables: never in the
database, never in the UI, never logged.
"""

from functools import lru_cache

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/concierge"
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    fake_llm_enabled: bool = False
    langsmith_api_key: str | None = None
    redis_url: str | None = None  # optional registry-cache backend (spec §7.3)
    otel_exporter_otlp_endpoint: str | None = None
    workspace_dir: str = "/workspace"
    # ambient delivery channels (spec §18.4) — env-only, like all secrets
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None
    ambient_webhook_url: str | None = None
    # custom OpenAI-compatible gateway (spec §18.7) — env-only, like all keys;
    # the comma-separated model list is env too (sync list_models() contract)
    custom_gateway_base_url: str | None = None
    custom_gateway_api_key: str | None = None
    custom_gateway_models: str | None = None
    # §18.8 auth & tenancy — dark by default: off ⇒ byte-identical
    auth_enabled: bool = False
    frontend_origin: str | None = None  # CORS pin when auth is on
    # M50 (PLAN M50, arch-C1): the connection budget is explicit. Per replica
    # the pooled ceiling is pool_size + max_overflow; the checkpointer pool,
    # the LISTEN connection and the leader lease sit outside it.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    # M51: every provider call carries a timeout and a bounded retry budget,
    # set ONCE at the port (spec §2.1 — the port is unbreached, so this is
    # the one place a hang or a retry storm can be bounded)
    llm_timeout_s: int = 120
    llm_max_retries: int = 2
    # M51: how long a draining replica lets in-flight runs finish before
    # cancelling them with a truthful terminal status
    shutdown_grace_s: int = 25
    backend_port: int = 8000
    frontend_port: int = 5173
    log_level: str = "INFO"

    @field_validator("*", mode="before")
    @classmethod
    def _blank_env_means_unset(cls, v: object, info: ValidationInfo) -> object:
        # compose passes `${VAR:-}`, so a variable absent from .env arrives
        # as "" — treat that as unset, not as a value to parse
        if isinstance(v, str) and v.strip() == "" and info.field_name is not None:
            return cls.model_fields[info.field_name].get_default()
        return v


@lru_cache
def get_config() -> AppConfig:
    return AppConfig()
