"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote AI Service"
    app_env: str = "local"
    environment: str = "local"
    port: int = 8008

    # AI providers. Empty by default so the service imports and tests without
    # credentials; the adapters raise a clear error if actually invoked unset.
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Current models. NOTE: the M15 plan named `claude-sonnet-4-20250514`;
    # that ID is superseded, and the `temperature` it also specified is
    # rejected outright by current models. See docs/modules/M15-*.md §Decisions.
    claude_model: str = "claude-opus-5"
    whisper_model: str = "whisper-1"

    # Copilot (T202) runs on Sonnet 5: its output is advisory prose + markup
    # suggestions, not the schema-critical scope extraction that justifies
    # Opus, so the ~40% cheaper, faster tier is the right trade-off.
    copilot_model: str = "claude-sonnet-5"

    # Upstream services (ADR-0003).
    pricebook_service_url: str = "http://localhost:8003"
    quote_service_url: str = "http://localhost:8004"
    upstream_timeout_seconds: float = 5.0
    upstream_max_attempts: int = 3

    # Audio limits. Whisper accepts up to 25 MB; 10 MB (~5 min) is the MVP cap.
    max_audio_size_bytes: int = 10 * 1024 * 1024

    # Image limits (M18 AI Vision). Claude accepts up to 5 MB per image on the
    # Messages API; 8 MB is the upload cap so a slightly-larger phone photo
    # fails with a clear 413 instead of an opaque provider error.
    max_image_size_bytes: int = 8 * 1024 * 1024

    # Document limits (M19 AI OCR). Same Messages API image constraint and
    # same cap as Vision — a photographed invoice/blueprint/note is subject
    # to the same 5 MB provider limit as a job-site photo.
    max_document_size_bytes: int = 8 * 1024 * 1024

    # Per-tenant daily AI spend cap, in minor units (cents). 0 disables it.
    daily_spend_cap_minor: int = 0

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote"

    feature_ai_voice: bool = True
    feature_copilot: bool = True
    feature_ai_vision: bool = True
    feature_ai_ocr: bool = True
    feature_ai_sales_coach: bool = True

    # Observability (T309b). Empty by default so every piece is opt-in — see
    # app/infrastructure/observability.py.
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""


settings = Settings()
