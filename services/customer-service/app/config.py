"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote Customer Service"
    app_env: str = "local"

    database_url: str = "postgresql+psycopg://tradequote:tradequote@localhost:5432/tradequote"

    default_page_size: int = 20
    max_page_size: int = 100


settings = Settings()
