"""GET /api/summary/{symbol} — rule-based text summary for a given ETF and date."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db

router = APIRouter()


@router.get("/summary/{symbol}")
async def get_summary(
    symbol: str,
    date: Optional[date] = Query(default=None, description="Trading date (YYYY-MM-DD). Defaults to latest available."),
    db: AsyncSession = Depends(get_db),
):
    """Return a rule-based natural language summary for the given ETF."""
    # TODO: implement — call core/summary.py with attribution data
    raise HTTPException(status_code=501, detail="Not implemented yet")
