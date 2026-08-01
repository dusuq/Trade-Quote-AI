"""FastAPI application for the Notification service (Module M22 / T205)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    relay_task = None
    if settings.outbox_relay_enabled:
        from app.infrastructure.relay import OutboxRelay

        relay = OutboxRelay()
        relay_task = asyncio.create_task(relay.run_forever())
    yield
    if relay_task:
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="TradeQuote AI — Notification Service",
    description=(
        "Multi-channel messaging: renders templates and delivers quotes, "
        "proposals, and signature requests over email and SMS."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
    }
