"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote Integration Service"
    app_env: str = "local"

    database_url: str = "postgresql+psycopg://tradequote:tradequote@localhost:5432/tradequote"

    # QuickBooks Online OAuth2
    quickbooks_client_id: str = ""
    quickbooks_client_secret: str = ""
    quickbooks_redirect_uri: str = "http://localhost:8011/v1/integrations/quickbooks/callback"
    quickbooks_environment: str = "sandbox"  # sandbox | production

    # Xero OAuth2
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = "http://localhost:8011/v1/integrations/xero/callback"

    # Zapier
    zapier_webhook_secret: str = ""

    default_page_size: int = 20
    max_page_size: int = 100


settings = Settings()
