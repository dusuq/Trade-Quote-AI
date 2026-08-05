"""FastAPI application entrypoint for the integration-service.

Run locally (after the DB is up):
    uvicorn app.main:app --reload --port 8011
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.infrastructure.observability import instrument
from app.interface.routes import public_router as integration_public_router
from app.interface.routes import router as integration_router

app = FastAPI(title=settings.app_name, version="0.1.0")
instrument(
    app,
    service_name="integration-service",
    service_env=settings.app_env,
    sentry_dsn=settings.sentry_dsn,
    otel_endpoint=settings.otel_exporter_otlp_endpoint,
)
app.include_router(integration_router)
# Public, unauthenticated OAuth callback routes (QuickBooks/Xero redirect the
# browser here directly) — see routes.py's public_router docstring and
# apps/api-gateway/src/plugins/auth.ts's PUBLIC_PATH_PATTERNS, which must
# allowlist these two exact paths for the gateway to pass them through
# without demanding a bearer token.
app.include_router(integration_public_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "integration", "env": settings.app_env}
