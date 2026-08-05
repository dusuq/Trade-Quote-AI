"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote E-Signature Service"
    app_env: str = "local"
    environment: str = "local"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote"

    # How long a signing link stays valid unless the caller overrides it.
    default_expiry_days: int = 30

    # proposal-service is read synchronously before a signature request is
    # created, to confirm the proposal exists in this tenant and is actually
    # sendable to a customer (T204c). ADR-0003: explicit timeout, bounded
    # attempts — GET is idempotent, so retrying it is safe.
    proposal_service_url: str = "http://localhost:8005"
    upstream_timeout_seconds: float = 5.0
    upstream_max_attempts: int = 3

    # Observability (T309b). Empty by default so every piece is opt-in — see
    # app/infrastructure/observability.py.
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""


settings = Settings()
