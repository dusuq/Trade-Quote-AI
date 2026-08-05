"""FastAPI application entrypoint for the customer-service.

Run locally (after the DB is up):
    uvicorn app.main:app --reload --port 8002
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.infrastructure.observability import instrument
from app.interface.routes import router as customer_router

app = FastAPI(title=settings.app_name, version="0.1.0")
instrument(
    app,
    service_name="customer-service",
    service_env=settings.app_env,
    sentry_dsn=settings.sentry_dsn,
    otel_endpoint=settings.otel_exporter_otlp_endpoint,
)
app.include_router(customer_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "customer", "env": settings.app_env}
