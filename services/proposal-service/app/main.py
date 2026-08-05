"""FastAPI application entrypoint for the proposal-service (PDF engine, M9).

Run locally:
    uvicorn app.main:app --reload --port 8005
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.infrastructure.observability import instrument
from app.interface.proposal_routes import router as proposal_router
from app.interface.routes import router as pdf_router
from app.interface.template_routes import router as template_router

app = FastAPI(title=settings.app_name, version="0.1.0")
instrument(
    app,
    service_name="proposal-service",
    service_env=settings.app_env,
    sentry_dsn=settings.sentry_dsn,
    otel_endpoint=settings.otel_exporter_otlp_endpoint,
)
app.include_router(pdf_router)
app.include_router(proposal_router)
app.include_router(template_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "proposal", "env": settings.app_env}
