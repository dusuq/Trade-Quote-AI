"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote Proposal Service"
    app_env: str = "local"

    # Where rendered PDFs are written. Local disk for MVP; swap for an
    # S3-compatible bucket (see infra/docker minio) once the object-storage
    # client is wired — the storage Protocol makes that a drop-in change.
    pdf_storage_dir: str = "./_pdf_storage"


settings = Settings()
