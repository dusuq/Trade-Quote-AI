"""FastAPI application for the AI Quote Assistant (Module M15 / T201)."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router

app = FastAPI(
    title="TradeQuote AI — AI Quote Assistant",
    description=(
        "Voice or text job description -> structured scope -> pricebook-matched "
        "line items -> draft quote."
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
