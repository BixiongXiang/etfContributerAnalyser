"""
Market Attribution Dashboard — FastAPI entry point.

Start locally:
    uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.api.routes import etfs, attribution, summary, health, admin
from src.models.database import init_db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting up Market Attribution backend…")
    await init_db()
    logger.info("Database ready.")

    # Start the daily scheduler
    from src.scheduler.jobs import start_scheduler, startup_backfill
    scheduler = start_scheduler()

    # Backfill any missing data since last run (runs in background, won't block startup)
    import asyncio
    asyncio.create_task(startup_backfill(default_days=settings.backfill_days))
    logger.info(
        "Startup backfill task queued (default_days=%d). App is ready.",
        settings.backfill_days,
    )

    yield

    # Shutdown
    logger.info("Shutting down scheduler…")
    scheduler.shutdown(wait=False)
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Market Attribution Dashboard",
    description="Explains why an ETF moved today by ranking each holding's contribution.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["health"])
app.include_router(etfs.router, prefix="/api", tags=["etfs"])
app.include_router(attribution.router, prefix="/api", tags=["attribution"])
app.include_router(summary.router, prefix="/api", tags=["summary"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
