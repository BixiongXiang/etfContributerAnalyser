"""
GET /api/attribution/{symbol}          — daily attribution (defaults to latest date)
GET /api/attribution/{symbol}/history  — historical attribution
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db

router = APIRouter()


@router.get("/attribution/{symbol}")
async def get_attribution(
    symbol: str,
    date: Optional[date] = Query(default=None, description="Trading date (YYYY-MM-DD). Defaults to latest available."),
    db: AsyncSession = Depends(get_db),
):
    """Return daily attribution breakdown for the given ETF."""
    # TODO: implement — query attribution table, build response
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/attribution/{symbol}/history")
async def get_attribution_history(
    symbol: str,
    period: str = Query(default="30d", description="Period: 5d, 30d, 90d, ytd"),
    db: AsyncSession = Depends(get_db),
):
    """Return historical attribution for the given ETF over the requested period."""
    # TODO: implement (Phase 2)
    raise HTTPException(status_code=501, detail="Not implemented yet")
