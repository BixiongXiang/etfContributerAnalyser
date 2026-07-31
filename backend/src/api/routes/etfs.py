"""GET /api/etfs — list supported ETFs with metadata."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.models import ETF, Attribution

router = APIRouter()


class ETFResponse(BaseModel):
    symbol: str
    name: str
    last_updated: Optional[str]   # ISO datetime string
    today_return_pct: Optional[float]


@router.get("/etfs", response_model=list[ETFResponse])
async def list_etfs(db: AsyncSession = Depends(get_db)):
    """Return all supported ETFs with last-update time and today's return."""
    result = await db.execute(select(ETF).order_by(ETF.symbol))
    etfs = result.scalars().all()

    response = []
    for etf in etfs:
        today_return = await _get_today_return(db, etf.symbol)
        response.append(
            ETFResponse(
                symbol=etf.symbol,
                name=etf.name,
                last_updated=(
                    etf.last_holdings_update.isoformat()
                    if etf.last_holdings_update
                    else None
                ),
                today_return_pct=today_return,
            )
        )
    return response


async def _get_today_return(db: AsyncSession, etf_symbol: str) -> Optional[float]:
    """Get the ETF's own daily return from the most recent attribution date."""
    # Sum all contributions for the latest available date = ETF return approximation
    subq = (
        select(func.max(Attribution.date))
        .where(Attribution.etf_symbol == etf_symbol)
        .scalar_subquery()
    )
    result = await db.execute(
        select(func.sum(Attribution.contribution))
        .where(Attribution.etf_symbol == etf_symbol)
        .where(Attribution.date == subq)
    )
    total = result.scalar_one_or_none()
    return round(total, 4) if total is not None else None
