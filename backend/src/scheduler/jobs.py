"""
Daily scheduler — runs the attribution pipeline after market close.

Schedule:
  Primary:  4:15 PM ET on trading days
  Retry 1:  4:30 PM ET
  Retry 2:  5:00 PM ET

Uses APScheduler with a background thread scheduler so it doesn't block
the FastAPI async event loop.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SUPPORTED_ETFS = ["QQQ", "VOO", "SCHD"]


def start_scheduler() -> BackgroundScheduler:
    """Create and start the APScheduler BackgroundScheduler."""
    scheduler = BackgroundScheduler(timezone=ET)

    # Parse primary schedule time
    h, m = settings.schedule_time.split(":")
    scheduler.add_job(
        _run_daily_update,
        trigger=CronTrigger(day_of_week="mon-fri", hour=int(h), minute=int(m), timezone=ET),
        id="daily_primary",
        name="Daily attribution update (primary)",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Retry jobs
    for idx, retry_time in enumerate(settings.schedule_retries.split(","), start=1):
        retry_time = retry_time.strip()
        if not retry_time:
            continue
        rh, rm = retry_time.split(":")
        scheduler.add_job(
            _run_daily_update_retry,
            trigger=CronTrigger(day_of_week="mon-fri", hour=int(rh), minute=int(rm), timezone=ET),
            id=f"daily_retry_{idx}",
            name=f"Daily attribution update (retry {idx})",
            replace_existing=True,
            misfire_grace_time=600,
        )

    scheduler.start()
    logger.info(
        "Scheduler started. Primary update at %s ET (Mon-Fri). Retries: %s",
        settings.schedule_time,
        settings.schedule_retries,
    )
    return scheduler


def _run_daily_update() -> None:
    """Synchronous wrapper — runs the async pipeline in a new event loop."""
    logger.info("Daily update triggered at %s ET", datetime.now(ET).strftime("%H:%M"))
    asyncio.run(_daily_pipeline(is_retry=False))


def _run_daily_update_retry() -> None:
    """Retry wrapper — only runs if today's data is still missing."""
    logger.info("Retry update triggered at %s ET", datetime.now(ET).strftime("%H:%M"))
    asyncio.run(_daily_pipeline(is_retry=True))


async def _daily_pipeline(is_retry: bool = False) -> None:
    """
    Full daily attribution pipeline:
    1. Check if today is a trading day
    2. Refresh ETF holdings (if stale)
    3. Download prices for all held symbols
    4. Compute attribution
    5. Store results in database
    """
    today = date.today()

    if not _is_trading_day(today):
        logger.info("Skipping pipeline: %s is not a trading day.", today)
        return

    # On retry, skip if we already have data for today
    if is_retry:
        from src.models.database import AsyncSessionLocal
        from src.models.models import Attribution
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count()).where(Attribution.date == today)
            )
            count = result.scalar_one()
            if count > 0:
                logger.info("Retry skipped: attribution data already exists for %s (%d rows).", today, count)
                return

    logger.info("Starting daily attribution pipeline for %s…", today)

    from src.models.database import AsyncSessionLocal
    from src.models.models import Holding, DailyPrice, Attribution, ETF
    from src.providers.holdings.dispatcher import fetch_holdings
    from src.providers.factory import get_price_provider
    from src.core.attribution import calculate_attribution, calculate_sector_attribution
    from sqlalchemy import select, delete

    price_provider = get_price_provider()
    yesterday = today - timedelta(days=1)

    async with AsyncSessionLocal() as session:
        for etf_symbol in SUPPORTED_ETFS:
            try:
                await _process_etf(
                    session, etf_symbol, today, yesterday, price_provider, fetch_holdings
                )
            except Exception as exc:
                logger.error("Pipeline failed for %s: %s", etf_symbol, exc, exc_info=True)

        await session.commit()

    logger.info("Daily pipeline complete for %s.", today)


async def _process_etf(session, etf_symbol, today, yesterday, price_provider, fetch_holdings):
    """Run the full pipeline for one ETF."""
    from datetime import timedelta
    from src.models.models import Holding, DailyPrice, Attribution, ETF
    from src.core.attribution import calculate_attribution, calculate_sector_attribution
    from sqlalchemy import select, delete
    import logging

    logger = logging.getLogger(__name__)

    # --- 1. Refresh holdings if stale ---
    result = await session.execute(
        select(Holding)
        .where(Holding.etf_symbol == etf_symbol)
        .order_by(Holding.as_of_date.desc())
        .limit(1)
    )
    latest_holding = result.scalar_one_or_none()

    stale = (
        latest_holding is None
        or (today - latest_holding.as_of_date).days >= 1
    )

    if stale:
        logger.info("Refreshing holdings for %s…", etf_symbol)
        holding_records, as_of_date = await fetch_holdings(etf_symbol)

        if holding_records:
            # Delete old holdings for this ETF and date to avoid duplicates
            await session.execute(
                delete(Holding)
                .where(Holding.etf_symbol == etf_symbol)
                .where(Holding.as_of_date == as_of_date)
            )
            for h in holding_records:
                session.add(
                    Holding(
                        etf_symbol=etf_symbol,
                        symbol=h.symbol,
                        company_name=h.company_name,
                        sector=h.sector,
                        weight=h.weight,
                        shares=h.shares,
                        as_of_date=as_of_date,
                    )
                )
            # Update ETF last_holdings_update
            etf_row = await session.get(ETF, etf_symbol)
            if etf_row:
                from datetime import datetime, timezone
                etf_row.last_holdings_update = datetime.now(timezone.utc)

    # --- 2. Load current holdings ---
    result = await session.execute(
        select(Holding)
        .where(Holding.etf_symbol == etf_symbol)
        .order_by(Holding.as_of_date.desc())
    )
    # Get the most recent as_of_date batch
    all_holdings = result.scalars().all()
    if not all_holdings:
        logger.warning("No holdings for %s — skipping attribution.", etf_symbol)
        return

    latest_date = max(h.as_of_date for h in all_holdings)
    current_holdings = [h for h in all_holdings if h.as_of_date == latest_date]

    # --- 3. Download prices ---
    symbols = [h.symbol for h in current_holdings] + [etf_symbol]
    # Need 2 days of prices to compute daily return (today + yesterday)
    price_records = await price_provider.get_daily_prices(
        symbols=symbols,
        start=yesterday - timedelta(days=3),  # extra buffer for weekends/holidays
        end=today,
    )

    # Build price lookup: symbol → {date: close}
    price_by_date: dict[str, dict] = {}
    for pr in price_records:
        price_by_date.setdefault(pr.symbol, {})[pr.date] = pr.close

    # Build (close, prev_close) pairs for today
    prices: dict[str, tuple[float, float]] = {}
    for sym, date_prices in price_by_date.items():
        sorted_dates = sorted(date_prices.keys())
        if len(sorted_dates) < 2:
            continue
        # Find today's close and the most recent prior close
        if today not in date_prices:
            continue
        today_close = date_prices[today]
        prev_dates = [d for d in sorted_dates if d < today]
        if not prev_dates:
            continue
        prev_close = date_prices[prev_dates[-1]]
        prices[sym] = (today_close, prev_close)

    if len(prices) < len(current_holdings) * 0.8:
        logger.warning(
            "%s: only %d/%d price pairs available (<80%%) — skipping attribution.",
            etf_symbol, len(prices), len(current_holdings),
        )
        return

    # --- 4. Compute attribution ---
    from src.providers.base import HoldingRecord as HR
    holding_list = [
        HR(symbol=h.symbol, company_name=h.company_name, weight=h.weight, sector=h.sector)
        for h in current_holdings
    ]

    attributions = calculate_attribution(holding_list, prices)

    # --- 5. Store attribution ---
    await session.execute(
        delete(Attribution)
        .where(Attribution.etf_symbol == etf_symbol)
        .where(Attribution.date == today)
    )
    for a in attributions:
        session.add(
            Attribution(
                etf_symbol=etf_symbol,
                date=today,
                symbol=a.symbol,
                company_name=a.company_name,
                sector=a.sector,
                weight=a.weight,
                return_pct=a.return_pct,
                contribution=a.contribution,
            )
        )

    # --- 6. Store today's prices in daily_prices (enables price display after hours) ---
    from src.models.models import DailyPrice
    stored_prices = 0
    for pr in price_records:
        if pr.date == today:
            existing = await session.get(DailyPrice, (pr.symbol, pr.date))
            if existing:
                existing.close = pr.close
                existing.open = pr.open
                existing.high = pr.high
                existing.low = pr.low
            else:
                session.add(DailyPrice(
                    symbol=pr.symbol,
                    date=pr.date,
                    open=pr.open,
                    high=pr.high,
                    low=pr.low,
                    close=pr.close,
                ))
            stored_prices += 1

    logger.info(
        "%s: stored %d attribution rows and %d price records for %s.",
        etf_symbol, len(attributions), stored_prices, today
    )


def _is_trading_day(d: date) -> bool:
    """Return True if the date is a NYSE trading day."""
    try:
        import exchange_calendars as xcals
        nyse = xcals.get_calendar("XNYS")
        return nyse.is_session(str(d))
    except Exception as exc:
        logger.warning("exchange_calendars check failed (%s) — assuming trading day.", exc)
        # Fallback: skip weekends only
        return d.weekday() < 5


async def startup_backfill(default_days: int = 30) -> None:
    """
    Called once at application startup to ensure the DB is not stale.

    Logic:
      - If the DB is empty → backfill the last `default_days` calendar days.
      - If the DB has data but is missing recent trading days → backfill only
        the gap (days since the latest stored date + a small buffer).
      - If the DB is up to date (latest date is today or last trading day) → do nothing.

    Runs in the background so it does not block the app from starting.
    """
    from src.models.database import AsyncSessionLocal
    from src.models.models import Attribution
    from sqlalchemy import select, func

    logger.info("Startup backfill check…")

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.max(Attribution.date))
            )
            latest_date = result.scalar_one_or_none()

        today = date.today()

        if latest_date is None:
            # Empty DB — full backfill
            days_to_fetch = default_days
            logger.info(
                "DB is empty. Backfilling last %d days…", days_to_fetch
            )
        else:
            gap_days = (today - latest_date).days
            if gap_days <= 1:
                # Up to date (today or yesterday — scheduler will handle today after close)
                logger.info(
                    "DB is up to date (latest: %s). No startup backfill needed.", latest_date
                )
                return
            # Add a 3-day buffer to ensure we have a valid prev_close for the first gap day
            days_to_fetch = gap_days + 3
            logger.info(
                "DB is %d day(s) behind (latest: %s). Backfilling %d days…",
                gap_days, latest_date, days_to_fetch,
            )

        # Import here to avoid circular dependency (admin also imports from jobs)
        from src.api.routes.admin import _run_backfill
        await _run_backfill(SUPPORTED_ETFS, days_to_fetch)
        logger.info("Startup backfill complete.")

    except Exception as exc:
        # Never crash the app on startup backfill failure
        logger.error("Startup backfill failed: %s", exc, exc_info=True)
