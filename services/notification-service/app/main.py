"""FastAPI application for the Notification service (Module M22 / T205)."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router

app = FastAPI(
    title="TradeQuote AI — Notification Service",
    description=(
        "Multi-channel messaging: renders templates and delivers quotes, "
        "proposals, and signature requests over email and SMS."
    ),
    version="0.1.0",
)

app.include_router(router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
    }
