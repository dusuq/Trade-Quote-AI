"""FastAPI application entrypoint for the integration-service.

Run locally (after the DB is up):
    uvicorn app.main:app --reload --port 8011
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as integration_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(integration_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "integration", "env": settings.app_env}
