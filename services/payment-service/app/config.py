"""Configuration settings for the payment-service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "tradequote-payment-service"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    square_access_token: str = ""
    square_webhook_signature_key: str = ""
    square_webhook_notification_url: str = ""
    square_environment: str = "sandbox"

    # Observability (T309b). Empty by default so every piece is opt-in — see
    # app/infrastructure/observability.py.
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
