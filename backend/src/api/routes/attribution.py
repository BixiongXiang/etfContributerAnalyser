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
    price: Optional[float] = None  # latest close price (USD)


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

    # Fetch close prices for the trade date to populate price field
    from src.models.models import DailyPrice
    symbols_list = [r.symbol for r in rows]
    price_result = await db.execute(
        select(DailyPrice.symbol, DailyPrice.close)
        .where(DailyPrice.symbol.in_(symbols_list))
        .where(DailyPrice.date == trade_date)
    )
    price_map: dict[str, float] = {r.symbol: r.close for r in price_result.all()}

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
            price=round(price_map[row.symbol], 2) if row.symbol in price_map else None,
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


@router.get("/attribution/{symbol}/live", response_model=AttributionResponse)
async def get_live_attribution(
    symbol: str,
    top_n: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Return intraday attribution using current market prices.

    Fetches live quotes from Yahoo Finance and computes contribution against
    yesterday's closing prices stored in the DB.

    Outside market hours, falls back to the latest stored (end-of-day) attribution.
    """
    from src.core.market_hours import market_status
    from src.providers.factory import get_price_provider
    from src.core.attribution import calculate_attribution
    from src.providers.base import HoldingRecord as HR
    from src.models.models import Holding
    from datetime import datetime, timezone, timedelta

    symbol = symbol.upper()
    status = market_status()

    # Outside market hours — return latest stored attribution
    if not status["is_open"]:
        resp = await get_attribution(symbol=symbol, date=None, top_n=top_n, db=db)
        # Patch the response to include market status
        return resp

    # --- Live path: fetch intraday prices ---
    # Load latest holdings from DB
    result = await db.execute(
        select(Holding)
        .where(Holding.etf_symbol == symbol)
        .order_by(Holding.as_of_date.desc())
    )
    all_holdings = result.scalars().all()
    if not all_holdings:
        raise HTTPException(status_code=404, detail=f"No holdings for {symbol}. Run /api/admin/backfill first.")

    latest_date = max(h.as_of_date for h in all_holdings)
    current_holdings = [h for h in all_holdings if h.as_of_date == latest_date]

    # Fetch today's intraday prices + yesterday's close
    price_provider = get_price_provider()
    today = datetime.now(timezone.utc).date()
    symbols = [h.symbol for h in current_holdings] + [symbol]

    price_records = await price_provider.get_daily_prices(
        symbols=symbols,
        start=today - timedelta(days=5),  # buffer for prev_close
        end=today,
    )

    # Build (current_price, prev_close) pairs
    price_by_symbol: dict[str, dict] = {}
    for pr in price_records:
        price_by_symbol.setdefault(pr.symbol, {})[pr.date] = pr.close

    prices: dict[str, tuple[float, float]] = {}
    for sym, date_prices in price_by_symbol.items():
        sorted_dates = sorted(date_prices.keys())
        if today not in date_prices or len(sorted_dates) < 2:
            continue
        prev_dates = [d for d in sorted_dates if d < today]
        if not prev_dates:
            continue
        prices[sym] = (date_prices[today], date_prices[prev_dates[-1]])

    if len(prices) < len(current_holdings) * 0.5:
        # Not enough live data — fall back to stored
        return await get_attribution(symbol=symbol, date=None, top_n=top_n, db=db)

    holding_list = [
        HR(symbol=h.symbol, company_name=h.company_name, weight=h.weight, sector=h.sector)
        for h in current_holdings
    ]
    attributions = calculate_attribution(holding_list, prices)
    etf_return = sum(a.contribution for a in attributions)

    def to_contributor(a) -> ContributorRow:
        pct = (a.contribution / etf_return * 100) if etf_return != 0 else 0.0
        current_price = prices.get(a.symbol)
        return ContributorRow(
            symbol=a.symbol,
            company_name=a.company_name,
            weight=round(a.weight, 4),
            return_pct=round(a.return_pct, 4),
            contribution=round(a.contribution, 6),
            sector=a.sector,
            pct_of_total_move=round(pct, 2),
            price=round(current_price[0], 2) if current_price else None,
        )

    all_contributors = [to_contributor(a) for a in attributions]
    negatives = sorted([c for c in all_contributors if c.contribution < 0], key=lambda x: x.contribution)[:top_n]
    positives = sorted([c for c in all_contributors if c.contribution > 0], key=lambda x: -x.contribution)[:top_n]

    sector_map: dict[str, dict] = {}
    for a in attributions:
        sec = a.sector or "Unknown"
        sector_map.setdefault(sec, {"contribution": 0.0, "count": 0})
        sector_map[sec]["contribution"] += a.contribution
        sector_map[sec]["count"] += 1

    sector_rows = sorted([
        SectorRow(
            sector=s,
            contribution=round(v["contribution"], 6),
            pct_of_total_move=round((v["contribution"] / etf_return * 100) if etf_return != 0 else 0.0, 2),
            num_stocks=v["count"],
        )
        for s, v in sector_map.items()
    ], key=lambda x: abs(x.contribution), reverse=True)

    return AttributionResponse(
        etf=symbol,
        date=str(today),
        etf_return_pct=round(etf_return, 4),
        data_as_of=datetime.now(timezone.utc).isoformat(),
        top_negative=negatives,
        top_positive=positives,
        sector_attribution=sector_rows,
    )


@router.get("/attribution/{symbol}/available-dates")
async def get_available_dates(
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return all dates that have attribution data for the given ETF.
    The frontend uses this to disable unavailable dates in the date picker.
    """
    symbol = symbol.upper()
    result = await db.execute(
        select(Attribution.date)
        .where(Attribution.etf_symbol == symbol)
        .distinct()
        .order_by(Attribution.date)
    )
    dates = result.scalars().all()
    if not dates:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data found for {symbol}. Run /api/admin/backfill first.",
        )
    return {
        "etf": symbol,
        "dates": [str(d) for d in dates],
        "earliest": str(dates[0]),
        "latest": str(dates[-1]),
    }


class RangeAttributionResponse(BaseModel):
    etf: str
    start_date: str
    end_date: str
    # Approximate ETF return over the range: sum of cumulative contributions
    etf_return_pct: float
    top_negative: list[ContributorRow]
    top_positive: list[ContributorRow]
    sector_attribution: list[SectorRow]


@router.get("/attribution/{symbol}/range", response_model=RangeAttributionResponse)
async def get_range_attribution(
    symbol: str,
    start: date = Query(..., description="Range start date (YYYY-MM-DD)"),
    end: date = Query(..., description="Range end date (YYYY-MM-DD)"),
    top_n: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Return cumulative attribution for the given ETF over a date range.

    For each holding:
      - cumulative_contribution = SUM(daily contribution) over all days in [start, end]
      - return_pct = (close on last trading day in range - close on first trading day in range)
                     / close on first trading day * 100
        computed from daily_prices; falls back to SUM(daily return_pct) if price data missing.

    The etf_return_pct is the sum of all holdings' cumulative contributions (approximate).
    """
    from src.models.models import DailyPrice
    from sqlalchemy import text

    symbol = symbol.upper()

    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end.")

    # --- 1. Sum daily contributions per holding over the range ---
    result = await db.execute(
        select(
            Attribution.symbol,
            Attribution.company_name,
            Attribution.sector,
            Attribution.weight,
            func.sum(Attribution.contribution).label("cumulative_contribution"),
        )
        .where(Attribution.etf_symbol == symbol)
        .where(Attribution.date >= start)
        .where(Attribution.date <= end)
        .group_by(Attribution.symbol, Attribution.company_name, Attribution.sector, Attribution.weight)
        .order_by(func.abs(func.sum(Attribution.contribution)).desc())
    )
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data for {symbol} between {start} and {end}. "
                   "Check available dates via /api/attribution/{symbol}/available-dates.",
        )

    # Use the average weight across the period (weight changes day-to-day are small)
    # For single day, this is just the weight on that day.
    # Re-query to get average weight properly
    weight_result = await db.execute(
        select(
            Attribution.symbol,
            func.avg(Attribution.weight).label("avg_weight"),
        )
        .where(Attribution.etf_symbol == symbol)
        .where(Attribution.date >= start)
        .where(Attribution.date <= end)
        .group_by(Attribution.symbol)
    )
    avg_weights = {r.symbol: r.avg_weight for r in weight_result.all()}

    # --- 2. Fetch cumulative stock returns from daily_prices ---
    # For each symbol, find:
    #   start_price = close on the earliest trading day >= start
    #   end_price   = close on the latest  trading day <= end
    # Then cumulative_return = (end_price - start_price) / start_price * 100

    all_symbols = [r.symbol for r in rows]

    # Get min date >= start and max date <= end for each symbol in one query
    price_bounds_result = await db.execute(
        select(
            DailyPrice.symbol,
            func.min(DailyPrice.date).label("first_date"),
            func.max(DailyPrice.date).label("last_date"),
        )
        .where(DailyPrice.symbol.in_(all_symbols))
        .where(DailyPrice.date >= start)
        .where(DailyPrice.date <= end)
        .group_by(DailyPrice.symbol)
    )
    price_bounds = {r.symbol: (r.first_date, r.last_date) for r in price_bounds_result.all()}

    # Fetch the actual prices for those specific dates
    # Build a set of (symbol, date) pairs we need
    needed_dates: dict[str, list[date]] = {}
    for sym, (fd, ld) in price_bounds.items():
        needed_dates[sym] = list({fd, ld})  # dedup if same day

    # Fetch prices in one query using IN on dates
    all_needed_date_values = list({d for dates in needed_dates.values() for d in dates})
    prices_result = await db.execute(
        select(DailyPrice.symbol, DailyPrice.date, DailyPrice.close)
        .where(DailyPrice.symbol.in_(all_symbols))
        .where(DailyPrice.date.in_(all_needed_date_values))
    )
    price_map: dict[str, dict] = {}
    for pr in prices_result.all():
        price_map.setdefault(pr.symbol, {})[pr.date] = pr.close

    # --- 3. Build contributor rows ---
    # Fallback return_pct per symbol from attribution table (sum of daily returns, approximate)
    fallback_result = await db.execute(
        select(
            Attribution.symbol,
            func.sum(Attribution.return_pct).label("sum_return_pct"),
        )
        .where(Attribution.etf_symbol == symbol)
        .where(Attribution.date >= start)
        .where(Attribution.date <= end)
        .group_by(Attribution.symbol)
    )
    fallback_returns = {r.symbol: r.sum_return_pct for r in fallback_result.all()}

    contributors: list[ContributorRow] = []
    etf_return = 0.0

    for row in rows:
        sym = row.symbol
        cumulative_contribution = row.cumulative_contribution
        etf_return += cumulative_contribution

        # Compute cumulative return from prices
        bounds = price_bounds.get(sym)
        return_pct = fallback_returns.get(sym, 0.0)  # default to fallback
        if bounds:
            fd, ld = bounds
            sym_prices = price_map.get(sym, {})
            start_price = sym_prices.get(fd)
            end_price = sym_prices.get(ld)
            if start_price and end_price and start_price != 0:
                return_pct = (end_price - start_price) / start_price * 100

        pct_of_total = (cumulative_contribution / etf_return * 100) if etf_return != 0 else 0.0
        # Use end-date close price as the "current" price for the range
        end_price_for_display: Optional[float] = None
        bounds = price_bounds.get(sym)
        if bounds:
            _, ld = bounds
            end_price_for_display = price_map.get(sym, {}).get(ld)
        contributors.append(
            ContributorRow(
                symbol=sym,
                company_name=row.company_name,
                weight=round(avg_weights.get(sym, row.weight), 4),
                return_pct=round(return_pct, 4),
                contribution=round(cumulative_contribution, 6),
                sector=row.sector,
                pct_of_total_move=round(pct_of_total, 2),
                price=round(end_price_for_display, 2) if end_price_for_display else None,
            )
        )

    # Recalculate pct_of_total now that etf_return is final
    for c in contributors:
        c.pct_of_total_move = round(
            (c.contribution / etf_return * 100) if etf_return != 0 else 0.0, 2
        )

    negatives = sorted(
        [c for c in contributors if c.contribution < 0],
        key=lambda x: x.contribution,
    )[:top_n]

    positives = sorted(
        [c for c in contributors if c.contribution > 0],
        key=lambda x: -x.contribution,
    )[:top_n]

    # --- 4. Sector aggregation ---
    sector_map: dict[str, dict] = {}
    for c in contributors:
        sector = c.sector or "Unknown"
        sector_map.setdefault(sector, {"contribution": 0.0, "count": 0})
        sector_map[sector]["contribution"] += c.contribution
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

    return RangeAttributionResponse(
        etf=symbol,
        start_date=str(start),
        end_date=str(end),
        etf_return_pct=round(etf_return, 4),
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
