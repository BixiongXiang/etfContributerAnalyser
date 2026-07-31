"""
GET /api/attribution/{symbol}          — daily attribution (defaults to latest date)
GET /api/attribution/{symbol}/history  — historical attribution (Phase 2)
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.models import Attribution

router = APIRouter()


class ContributorRow(BaseModel):
    symbol: str
    company_name: str
    weight: float
    return_pct: float
    contribution: float
    sector: Optional[str]
    pct_of_total_move: float


class SectorRow(BaseModel):
    sector: str
    contribution: float
    pct_of_total_move: float
    num_stocks: int


class AttributionResponse(BaseModel):
    etf: str
    date: str
    etf_return_pct: float
    data_as_of: Optional[str]
    top_negative: list[ContributorRow]
    top_positive: list[ContributorRow]
    sector_attribution: list[SectorRow]


@router.get("/attribution/{symbol}", response_model=AttributionResponse)
async def get_attribution(
    symbol: str,
    date: Optional[date] = Query(
        default=None,
        description="Trading date (YYYY-MM-DD). Defaults to latest available.",
    ),
    top_n: int = Query(default=10, ge=1, le=50, description="Number of top contributors to return."),
    db: AsyncSession = Depends(get_db),
):
    """Return daily attribution breakdown for the given ETF."""
    symbol = symbol.upper()

    # Resolve date: use provided date or latest available
    trade_date = await _resolve_date(db, symbol, date)
    if trade_date is None:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data found for {symbol}. Run /api/admin/backfill first.",
        )

    # Fetch all attribution rows for this ETF + date, sorted by |contribution| desc
    result = await db.execute(
        select(Attribution)
        .where(Attribution.etf_symbol == symbol)
        .where(Attribution.date == trade_date)
        .order_by(func.abs(Attribution.contribution).desc())
    )
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data for {symbol} on {trade_date}.",
        )

    # Total ETF return = sum of all contributions
    etf_return = sum(r.contribution for r in rows)

    # Build contributor rows with pct_of_total_move
    def to_contributor(row: Attribution) -> ContributorRow:
        pct = (row.contribution / etf_return * 100) if etf_return != 0 else 0.0
        return ContributorRow(
            symbol=row.symbol,
            company_name=row.company_name,
            weight=round(row.weight, 4),
            return_pct=round(row.return_pct, 4),
            contribution=round(row.contribution, 6),
            sector=row.sector,
            pct_of_total_move=round(pct, 2),
        )

    all_contributors = [to_contributor(r) for r in rows]

    # Split into negative and positive, take top_n of each
    negatives = sorted(
        [c for c in all_contributors if c.contribution < 0],
        key=lambda x: x.contribution,  # most negative first
    )[:top_n]

    positives = sorted(
        [c for c in all_contributors if c.contribution > 0],
        key=lambda x: -x.contribution,  # most positive first
    )[:top_n]

    # Sector aggregation
    sector_map: dict[str, dict] = {}
    for r in rows:
        sector = r.sector or "Unknown"
        if sector not in sector_map:
            sector_map[sector] = {"contribution": 0.0, "count": 0}
        sector_map[sector]["contribution"] += r.contribution
        sector_map[sector]["count"] += 1

    sector_rows = sorted(
        [
            SectorRow(
                sector=s,
                contribution=round(v["contribution"], 6),
                pct_of_total_move=round(
                    (v["contribution"] / etf_return * 100) if etf_return != 0 else 0.0, 2
                ),
                num_stocks=v["count"],
            )
            for s, v in sector_map.items()
        ],
        key=lambda x: abs(x.contribution),
        reverse=True,
    )

    # Get last_holdings_update for data_as_of
    from src.models.models import ETF
    etf_row = await db.get(ETF, symbol)
    data_as_of = etf_row.last_holdings_update.isoformat() if etf_row and etf_row.last_holdings_update else None

    return AttributionResponse(
        etf=symbol,
        date=str(trade_date),
        etf_return_pct=round(etf_return, 4),
        data_as_of=data_as_of,
        top_negative=negatives,
        top_positive=positives,
        sector_attribution=sector_rows,
    )


@router.get("/attribution/{symbol}/history")
async def get_attribution_history(
    symbol: str,
    period: str = Query(default="30d", description="Period: 5d, 30d, 90d, ytd"),
    db: AsyncSession = Depends(get_db),
):
    """Return historical attribution for the given ETF over the requested period (Phase 2)."""
    raise HTTPException(status_code=501, detail="Historical attribution coming in Phase 2.")


async def _resolve_date(db: AsyncSession, symbol: str, requested: Optional[date]) -> Optional[date]:
    """Return the requested date if it has data, otherwise return the latest available date."""
    if requested is not None:
        result = await db.execute(
            select(Attribution.date)
            .where(Attribution.etf_symbol == symbol)
            .where(Attribution.date == requested)
            .limit(1)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        select(func.max(Attribution.date)).where(Attribution.etf_symbol == symbol)
    )
    return result.scalar_one_or_none()
