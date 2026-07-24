"""FastAPI application entrypoint for the quote-service.

Run locally (after DB is up):
    uvicorn app.main:app --reload --port 8004
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as quote_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(quote_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "quote", "env": settings.app_env}
