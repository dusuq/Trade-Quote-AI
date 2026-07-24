"""FastAPI application entrypoint for the customer-service.

Run locally (after the DB is up):
    uvicorn app.main:app --reload --port 8002
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as customer_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(customer_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "customer", "env": settings.app_env}
