"""
POST /api/admin/backfill — manually trigger data download and attribution computation.

This endpoint is the primary way to populate data outside the 4:15 PM scheduler.
Use it on first startup or whenever you want to refresh data immediately.

Example:
    curl -X POST http://localhost:8888/api/admin/backfill
    curl -X POST "http://localhost:8888/api/admin/backfill?days=30"
    curl -X POST "http://localhost:8888/api/admin/backfill?symbol=QQQ&days=7"
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AsyncSessionLocal, get_db
from src.models.models import Attribution, ETF, Holding
from src.providers.factory import get_price_provider
from src.providers.holdings.dispatcher import fetch_holdings

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_ETFS = ["QQQ", "VOO", "SCHD"]


class BackfillStatus(BaseModel):
    status: str
    message: str
    symbols: list[str]
    days: int


@router.post("/admin/backfill", response_model=BackfillStatus)
async def trigger_backfill(
    background_tasks: BackgroundTasks,
    symbol: Optional[str] = Query(
        default=None,
        description="ETF symbol to backfill (QQQ, VOO, SCHD). Omit to backfill all.",
    ),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of calendar days of history to fetch.",
    ),
):
    """
    Trigger a data backfill in the background.

    Downloads holdings, fetches prices, and computes attribution for the
    requested number of days. Runs asynchronously — returns immediately
    and processes in the background.
    """
    symbols = [symbol.upper()] if symbol else SUPPORTED_ETFS

    # Validate symbol
    for sym in symbols:
        if sym not in SUPPORTED_ETFS:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported ETF '{sym}'. Supported: {SUPPORTED_ETFS}",
            )

    background_tasks.add_task(_run_backfill, symbols, days)

    return BackfillStatus(
        status="started",
        message=f"Backfill started for {symbols} ({days} days). Check server logs for progress.",
        symbols=symbols,
        days=days,
    )


@router.get("/admin/status")
async def backfill_status(db: AsyncSession = Depends(get_db)):
    """Return a summary of what data is currently in the database."""
    result = await db.execute(
        select(
            Attribution.etf_symbol,
            func.count(Attribution.symbol).label("rows"),
            func.min(Attribution.date).label("earliest"),
            func.max(Attribution.date).label("latest"),
        ).group_by(Attribution.etf_symbol)
    )
    rows = result.all()

    holdings_result = await db.execute(
        select(
            Holding.etf_symbol,
            func.count(Holding.symbol).label("holdings_count"),
            func.max(Holding.as_of_date).label("as_of"),
        ).group_by(Holding.etf_symbol)
    )
    holdings_rows = holdings_result.all()
    holdings_map = {r.etf_symbol: r for r in holdings_rows}

    summary = []
    for r in rows:
        h = holdings_map.get(r.etf_symbol, None)
        summary.append({
            "etf": r.etf_symbol,
            "attribution_rows": r.rows,
            "earliest_date": str(r.earliest),
            "latest_date": str(r.latest),
            "holdings_count": h.holdings_count if h else 0,
            "holdings_as_of": str(h.as_of) if h else None,
        })

    # ETFs with no attribution yet
    all_etfs = set(SUPPORTED_ETFS)
    populated = {r.etf_symbol for r in rows}
    for sym in all_etfs - populated:
        summary.append({
            "etf": sym,
            "attribution_rows": 0,
            "earliest_date": None,
            "latest_date": None,
            "holdings_count": holdings_map.get(sym, None) and holdings_map[sym].holdings_count or 0,
            "holdings_as_of": None,
        })

    return {"etfs": sorted(summary, key=lambda x: x["etf"])}


async def _run_backfill(symbols: list[str], days: int) -> None:
    """Background task: download holdings + prices, compute and store attribution."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    logger.info("Backfill started: %s, %s → %s", symbols, start_date, end_date)

    price_provider = get_price_provider()

    for etf_symbol in symbols:
        try:
            await _backfill_etf(etf_symbol, start_date, end_date, price_provider)
        except Exception as exc:
            logger.error("Backfill failed for %s: %s", etf_symbol, exc, exc_info=True)

    logger.info("Backfill complete for %s.", symbols)


async def _backfill_etf(etf_symbol: str, start_date: date, end_date: date, price_provider) -> None:
    """Backfill one ETF: refresh holdings, fetch prices, compute attribution for each date."""
    from datetime import datetime, timezone
    from src.core.attribution import calculate_attribution
    from src.providers.base import HoldingRecord as HR

    async with AsyncSessionLocal() as session:
        # --- 1. Refresh holdings ---
        logger.info("%s: downloading holdings…", etf_symbol)
        holding_records, as_of_date = await fetch_holdings(etf_symbol)

        if not holding_records:
            logger.warning("%s: no holdings returned — skipping.", etf_symbol)
            return

        # Delete existing holdings for this as_of_date and re-insert
        await session.execute(
            delete(Holding)
            .where(Holding.etf_symbol == etf_symbol)
            .where(Holding.as_of_date == as_of_date)
        )
        for h in holding_records:
            session.add(Holding(
                etf_symbol=etf_symbol,
                symbol=h.symbol,
                company_name=h.company_name,
                sector=h.sector,
                weight=h.weight,
                shares=h.shares,
                as_of_date=as_of_date,
            ))

        # Update ETF last_holdings_update
        etf_row = await session.get(ETF, etf_symbol)
        if etf_row:
            etf_row.last_holdings_update = datetime.now(timezone.utc)

        await session.commit()
        logger.info("%s: stored %d holdings (as of %s).", etf_symbol, len(holding_records), as_of_date)

        # --- 2. Fetch prices ---
        symbols = [h.symbol for h in holding_records] + [etf_symbol]
        logger.info("%s: downloading prices for %d symbols (%s → %s)…",
                    etf_symbol, len(symbols), start_date, end_date)

        # Add extra buffer days to ensure we have a prev_close for start_date
        price_start = start_date - timedelta(days=7)
        price_records = await price_provider.get_daily_prices(
            symbols=symbols,
            start=price_start,
            end=end_date,
        )

        if not price_records:
            logger.warning("%s: no price data returned — skipping attribution.", etf_symbol)
            return

        # Build price lookup: symbol → {date: close}
        price_by_symbol: dict[str, dict[date, float]] = {}
        for pr in price_records:
            price_by_symbol.setdefault(pr.symbol, {})[pr.date] = pr.close

        logger.info("%s: received prices for %d symbols.", etf_symbol, len(price_by_symbol))

        # --- 3. Compute attribution for each trading date ---
        holding_list = [
            HR(symbol=h.symbol, company_name=h.company_name, weight=h.weight, sector=h.sector)
            for h in holding_records
        ]

        # Get all dates we have price data for (for at least one symbol)
        all_dates = sorted({d for dates in price_by_symbol.values() for d in dates})
        trading_dates = [d for d in all_dates if start_date <= d <= end_date]

        total_stored = 0
        for trade_date in trading_dates:
            # Build (close, prev_close) pairs for this date
            prices: dict[str, tuple[float, float]] = {}
            for sym, date_prices in price_by_symbol.items():
                if trade_date not in date_prices:
                    continue
                sorted_dates = sorted(date_prices.keys())
                prev_dates = [d for d in sorted_dates if d < trade_date]
                if not prev_dates:
                    continue
                prices[sym] = (date_prices[trade_date], date_prices[prev_dates[-1]])

            if len(prices) < len(holding_list) * 0.5:
                logger.debug("%s %s: only %d/%d price pairs — skipping.",
                             etf_symbol, trade_date, len(prices), len(holding_list))
                continue

            attributions = calculate_attribution(holding_list, prices)
            if not attributions:
                continue

            # Delete existing attribution for this date and re-insert
            await session.execute(
                delete(Attribution)
                .where(Attribution.etf_symbol == etf_symbol)
                .where(Attribution.date == trade_date)
            )
            for a in attributions:
                session.add(Attribution(
                    etf_symbol=etf_symbol,
                    date=trade_date,
                    symbol=a.symbol,
                    company_name=a.company_name,
                    sector=a.sector,
                    weight=a.weight,
                    return_pct=a.return_pct,
                    contribution=a.contribution,
                ))
            total_stored += len(attributions)

        await session.commit()
        logger.info("%s: backfill complete. Stored %d attribution rows across %d dates.",
                    etf_symbol, total_stored, len(trading_dates))
