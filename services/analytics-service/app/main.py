from fastapi import FastAPI

from app.config import settings
from app.interface.routes import router as analytics_router

app = FastAPI(
    title="TradeQuote AI — Analytics Service",
    description="Analytics read models, trade breakdowns, customer LTV, and forecasting",
    version="0.1.0",
)

app.include_router(analytics_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
    }
