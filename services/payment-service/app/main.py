"""FastAPI application entrypoint for the payment-service.

Run locally (after DB is up):
    uvicorn app.main:app --reload --port 8010
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as payment_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(payment_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "payment", "env": settings.app_env}
