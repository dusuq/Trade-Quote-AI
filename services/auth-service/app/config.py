"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote Auth Service"
    app_env: str = "local"

    database_url: str = "postgresql+psycopg://tradequote:tradequote@localhost:5432/tradequote"

    # JWT
    jwt_secret: str = "local-dev-only-change-me-32byte-minimum-secret"
    jwt_algorithm: str = "HS256"
    jwt_expires_in: int = 3600  # access token seconds
    refresh_expires_in: int = 60 * 60 * 24 * 30  # 30 days

    # Encryption key for MFA secrets at rest (32-byte urlsafe base64 for Fernet).
    mfa_encryption_key: str = ""

    # PBKDF2 work factor (OWASP-aligned; argon2 is the production target).
    pbkdf2_iterations: int = 600_000


settings = Settings()
