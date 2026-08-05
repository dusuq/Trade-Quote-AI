"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote AI Notification Service"
    app_env: str = "local"
    environment: str = "local"
    port: int = 8009

    # Provider selection. Default to "console" so the service runs and is fully
    # testable with no third-party credentials — it just logs the message.
    provider_email: str = "console"  # "sendgrid" | "resend" | "console"
    provider_sms: str = "console"  # "twilio" | "console"

    # Credentials (empty by default; the concrete adapters raise a clear error
    # if selected without one, rather than failing deep in an HTTP call).
    sendgrid_api_key: str = ""
    resend_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = "+15550000000"

    # Email envelope defaults.
    email_from_address: str = "no-reply@tradequote.ai"
    email_from_name: str = "TradeQuote AI"

    # Outbound provider call timeout, seconds.
    provider_timeout_seconds: float = 10.0

    # Outbox relay (off by default; enable in production).
    outbox_relay_enabled: bool = False
    outbox_relay_interval_seconds: float = 5.0
    outbox_relay_batch_size: int = 50

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote"

    # Observability (T309b). Empty by default so every piece is opt-in — see
    # app/infrastructure/observability.py.
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""


settings = Settings()
