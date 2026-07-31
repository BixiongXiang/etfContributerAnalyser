"""
Async SQLAlchemy engine, session factory, and database initialisation.

Usage:
    from src.models.database import get_db, init_db

    # In FastAPI route (via Depends):
    async def my_route(db: AsyncSession = Depends(get_db)):
        ...

    # On startup:
    await init_db()
"""

import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.models.models import Base

logger = logging.getLogger(__name__)

# Ensure the data/ directory exists before SQLite tries to create the file
_db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
if _db_path.startswith("./"):
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=False,           # set True to log all SQL (very verbose)
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables if they do not exist. Safe to call on every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")

    # Seed the three supported ETFs if the table is empty
    await _seed_etfs()


async def _seed_etfs() -> None:
    """Insert the three supported ETFs on first startup."""
    from sqlalchemy import select, text
    from src.models.models import ETF

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ETF))
        existing = result.scalars().all()
        if existing:
            return  # already seeded

        etfs = [
            ETF(symbol="QQQ",  name="Invesco QQQ Trust",              provider="invesco"),
            ETF(symbol="VOO",  name="Vanguard S&P 500 ETF",           provider="vanguard"),
            ETF(symbol="SCHD", name="Schwab U.S. Dividend Equity ETF", provider="schwab"),
        ]
        session.add_all(etfs)
        await session.commit()
        logger.info("Seeded 3 ETFs: QQQ, VOO, SCHD.")


async def get_db():
    """FastAPI dependency — yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
