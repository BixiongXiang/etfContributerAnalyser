"""GET /api/summary/{symbol} — rule-based text summary for a given ETF and date."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.models import Attribution
from src.core.attribution import AttributionRecord, calculate_sector_attribution
from src.core.summary import generate_summary

router = APIRouter()


class SummaryResponse(BaseModel):
    etf: str
    date: str
    summary: str


@router.get("/summary/{symbol}", response_model=SummaryResponse)
async def get_summary(
    symbol: str,
    date: Optional[date] = Query(
        default=None,
        description="Trading date (YYYY-MM-DD). Defaults to latest available.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Return a rule-based natural language summary for the given ETF."""
    symbol = symbol.upper()

    # Resolve latest date if not provided
    if date is None:
        result = await db.execute(
            select(func.max(Attribution.date)).where(Attribution.etf_symbol == symbol)
        )
        date = result.scalar_one_or_none()

    if date is None:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data found for {symbol}. Run /api/admin/backfill first.",
        )

    # Fetch attribution rows
    result = await db.execute(
        select(Attribution)
        .where(Attribution.etf_symbol == symbol)
        .where(Attribution.date == date)
        .order_by(func.abs(Attribution.contribution).desc())
    )
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data for {symbol} on {date}.",
        )

    # Convert DB rows to AttributionRecord objects for the summary engine
    attributions = [
        AttributionRecord(
            symbol=r.symbol,
            company_name=r.company_name,
            sector=r.sector,
            weight=r.weight,
            return_pct=r.return_pct,
            contribution=r.contribution,
        )
        for r in rows
    ]

    etf_return = sum(a.contribution for a in attributions)
    sector_attributions = calculate_sector_attribution(attributions)

    summary_text = generate_summary(
        etf_symbol=symbol,
        trade_date=date,
        etf_return_pct=etf_return,
        attributions=attributions,
        sector_attributions=sector_attributions,
    )

    return SummaryResponse(etf=symbol, date=str(date), summary=summary_text)
