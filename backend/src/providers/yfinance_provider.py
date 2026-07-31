"""
Yahoo Finance price provider — fetches market prices directly from the
Yahoo Finance chart API (v8/finance/chart) using the requests library.

Why requests instead of httpx or yfinance:
  - requests with a minimal User-Agent header avoids the 429 rate limiting
    that httpx triggers due to different default headers
  - yfinance's crumb management is fragile and frequently breaks
  - The v8 chart API is stable and returns adjusted OHLC data

Concurrency: runs blocking requests.get calls in a thread pool via
asyncio.run_in_executor so the FastAPI event loop is not blocked.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime, timezone
from typing import Optional

import requests

from src.providers.base import DataProvider, HoldingRecord, PriceRecord

logger = logging.getLogger(__name__)

_CHART_URLS = [
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
]

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

_MAX_WORKERS = 8       # thread pool size for concurrent fetches
_BATCH_SIZE = 50       # symbols per asyncio.gather batch


class YFinanceProvider(DataProvider):
    """Price provider using the Yahoo Finance chart API via requests."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

    async def get_holdings(self, etf_symbol: str) -> tuple[list[HoldingRecord], date]:
        raise NotImplementedError(
            "YFinanceProvider does not supply holdings. "
            "Use the provider-specific holdings parser instead."
        )

    async def get_daily_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> list[PriceRecord]:
        """
        Fetch daily closing prices for all symbols using a thread pool.
        """
        if not symbols:
            return []

        all_records: list[PriceRecord] = []

        # Process in batches to avoid overwhelming the thread pool
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = symbols[i : i + _BATCH_SIZE]
            tasks = [
                self._fetch_in_thread(sym, start, end)
                for sym in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.debug("Price fetch failed for %s: %s", sym, result)
                elif result:
                    all_records.extend(result)

        logger.info(
            "Yahoo Finance: fetched %d price records for %d symbols (%s → %s)",
            len(all_records), len(symbols), start, end,
        )
        return all_records

    async def _fetch_in_thread(
        self, symbol: str, start: date, end: date
    ) -> list[PriceRecord]:
        """Run the blocking HTTP call in a thread pool executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            _fetch_symbol_sync,
            symbol,
            start,
            end,
        )


def _fetch_symbol_sync(symbol: str, start: date, end: date) -> list[PriceRecord]:
    """Synchronous fetch for one symbol — runs in a thread."""
    start_ts = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime(
        (end + timedelta(days=1)).year,
        (end + timedelta(days=1)).month,
        (end + timedelta(days=1)).day,
        tzinfo=timezone.utc,
    ).timestamp())

    params = {
        "interval": "1d",
        "period1": start_ts,
        "period2": end_ts,
        "events": "div,splits",
        "includePrePost": "false",
    }

    for url_template in _CHART_URLS:
        try:
            url = url_template.format(symbol=symbol)
            resp = _SESSION.get(url, params=params, timeout=15)
            if resp.status_code == 404:
                continue
            if resp.status_code == 429:
                logger.warning("Rate limited for %s (429) — will retry next backfill.", symbol)
                return []
            resp.raise_for_status()
            records = _parse_chart_response(resp.json(), symbol)
            if records:
                return records
        except requests.RequestException as exc:
            logger.debug("Request failed for %s: %s", symbol, exc)

    return []


def _parse_chart_response(data: dict, symbol: str) -> list[PriceRecord]:
    """Parse the Yahoo Finance v8 chart API JSON response."""
    try:
        result = data["chart"]["result"]
        if not result:
            return []

        chart = result[0]
        timestamps = chart.get("timestamp", [])
        quotes = chart.get("indicators", {}).get("quote", [{}])[0]

        # Prefer adjusted close if available
        adj_close_data = chart.get("indicators", {}).get("adjclose", [])
        adj_closes = adj_close_data[0].get("adjclose", []) if adj_close_data else []
        closes_raw = adj_closes if adj_closes else quotes.get("close", [])

        opens_raw = quotes.get("open", [])
        highs_raw = quotes.get("high", [])
        lows_raw = quotes.get("low", [])

        records: list[PriceRecord] = []
        for i, ts in enumerate(timestamps):
            close = _safe_float(closes_raw, i)
            if close is None:
                continue
            records.append(PriceRecord(
                symbol=symbol.upper(),
                date=datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                close=close,
                open=_safe_float(opens_raw, i),
                high=_safe_float(highs_raw, i),
                low=_safe_float(lows_raw, i),
            ))

        return records

    except (KeyError, IndexError, TypeError) as exc:
        logger.debug("Failed to parse chart response for %s: %s", symbol, exc)
        return []


def _safe_float(lst: list, i: int) -> Optional[float]:
    try:
        v = lst[i]
        return float(v) if v is not None else None
    except (IndexError, TypeError, ValueError):
        return None
