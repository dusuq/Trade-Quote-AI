"""Runtime configuration, loaded from environment (12-factor)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# The committed dev-only signing key (T310). It is public in this repository,
# so anyone can mint an HS256 token with any `tid` and `roles`; the gateway
# would verify it and forward that forged tenant id downstream as trusted.
# Kept as a default so local dev works with no setup, but refused at startup
# in any non-local environment — see _assert_production_secrets.
DEV_ONLY_JWT_SECRET = "local-dev-only-change-me-32byte-minimum-secret"

# Environments that must never boot on development defaults.
NON_LOCAL_ENVS = frozenset({"production", "prod", "staging", "preprod"})

# HS256 keys shorter than the 256-bit hash output weaken the construction and
# are brute-forceable offline from a single captured token.
MIN_PRODUCTION_SECRET_LENGTH = 32


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when a non-local environment is running on dev defaults."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote Auth Service"
    app_env: str = "local"

    database_url: str = "postgresql+psycopg://tradequote:tradequote@localhost:5432/tradequote"

    # JWT
    jwt_secret: str = DEV_ONLY_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_in: int = 3600  # access token seconds
    refresh_expires_in: int = 60 * 60 * 24 * 30  # 30 days

    # Encryption key for MFA secrets at rest (32-byte urlsafe base64 for Fernet).
    mfa_encryption_key: str = ""

    # PBKDF2 work factor (OWASP-aligned; argon2 is the production target).
    pbkdf2_iterations: int = 600_000

    # Observability (T309b). Empty by default so every piece is opt-in — see
    # app/infrastructure/observability.py.
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    def is_non_local(self) -> bool:
        return self.app_env.strip().lower() in NON_LOCAL_ENVS

    def model_post_init(self, __context: object, /) -> None:
        _assert_production_secrets(self)


def _assert_production_secrets(s: Settings) -> None:
    """Refuse to start a non-local environment on development defaults (T310).

    Raises rather than warns, deliberately. A warning in a log nobody reads is
    exactly how a fail-open configuration survives into production; a process
    that will not start gets caught during the deploy, which is the cheapest
    possible moment to catch it.
    """
    if not s.is_non_local():
        return

    problems: list[str] = []

    if s.jwt_secret == DEV_ONLY_JWT_SECRET:
        problems.append(
            "JWT_SECRET is still the committed dev default. It is public in this repo, so "
            "anyone could forge a token for any tenant with any role. Set a unique random "
            "secret (e.g. `openssl rand -base64 48`), identical to the api-gateway's."
        )
    elif len(s.jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET is only {len(s.jwt_secret)} characters; HS256 signing keys must be "
            f"at least {MIN_PRODUCTION_SECRET_LENGTH}."
        )

    if not s.mfa_encryption_key:
        problems.append(
            "MFA_ENCRYPTION_KEY is unset. MFA/TOTP secrets are the second authentication "
            "factor; without a key they cannot be encrypted at rest, so a single database "
            "read would hand an attacker every user's TOTP seed."
        )

    if problems:
        raise InsecureConfigurationError(
            f'Refusing to start auth-service in APP_ENV="{s.app_env}" with insecure '
            "configuration:\n" + "\n".join(f"  - {p}" for p in problems)
        )


settings = Settings()
