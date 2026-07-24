"""FastAPI application entrypoint for the pricebook-service.

Run locally (after DB is up):
    uvicorn app.main:app --reload --port 8003
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as pricebook_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(pricebook_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pricebook", "env": settings.app_env}
