"""FastAPI application entrypoint for the proposal-service (PDF engine, M9).

Run locally:
    uvicorn app.main:app --reload --port 8005
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as proposal_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(proposal_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "proposal", "env": settings.app_env}
