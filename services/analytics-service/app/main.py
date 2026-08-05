from fastapi import FastAPI

from app.config import settings
from app.infrastructure.observability import instrument
from app.interface.routes import router as analytics_router

app = FastAPI(
    title="TradeQuote AI — Analytics Service",
    description="Analytics read models, trade breakdowns, customer LTV, and forecasting",
    version="0.1.0",
)
instrument(
    app,
    service_name="analytics-service",
    service_env=settings.environment,
    sentry_dsn=settings.sentry_dsn,
    otel_endpoint=settings.otel_exporter_otlp_endpoint,
)

app.include_router(analytics_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
    }
