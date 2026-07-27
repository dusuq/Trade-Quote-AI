"""FastAPI application for the E-Signature service (Module M10 / T204)."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import public_router, router

app = FastAPI(
    title="TradeQuote AI — E-Signature Service",
    description=(
        "Signature capture with a tamper-evident, hash-chained audit trail "
        "(IP, timestamp, consent, document binding)."
    ),
    version="0.1.0",
)

app.include_router(router)
app.include_router(public_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
    }
