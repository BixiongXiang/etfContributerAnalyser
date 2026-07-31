"""
Financial Modeling Prep (FMP) data provider — fallback when yfinance is unavailable.

Free tier: 250 API calls/day.
Set FMP_API_KEY in .env to enable.
"""

import logging
from datetime import date

import httpx

from src.config import settings
from src.providers.base import DataProvider, HoldingRecord, PriceRecord

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPProvider(DataProvider):
    """Implements DataProvider using the Financial Modeling Prep API."""

    def __init__(self) -> None:
        if not settings.fmp_api_key:
            raise ValueError(
                "FMP_API_KEY is not set. Either set it in .env or use DATA_PROVIDER=yfinance."
            )
        self._key = settings.fmp_api_key

    async def get_holdings(self, etf_symbol: str) -> tuple[list[HoldingRecord], date]:
        """Fetch ETF holdings from FMP."""
        url = f"{_BASE_URL}/etf-holder/{etf_symbol}?apikey={self._key}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        holdings = []
        for item in data:
            holdings.append(
                HoldingRecord(
                    symbol=item.get("asset", ""),
                    company_name=item.get("name", ""),
                    weight=float(item.get("weightPercentage", 0)),
                    sector=item.get("sector"),
                    shares=item.get("sharesNumber"),
                )
            )

        as_of = date.today()
        logger.info("FMP: fetched %d holdings for %s", len(holdings), etf_symbol)
        return holdings, as_of

    async def get_daily_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> list[PriceRecord]:
        """Fetch historical daily prices from FMP (one call per symbol — use sparingly)."""
        records: list[PriceRecord] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for symbol in symbols:
                url = (
                    f"{_BASE_URL}/historical-price-full/{symbol}"
                    f"?from={start}&to={end}&apikey={self._key}"
                )
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                    for row in data.get("historical", []):
                        records.append(
                            PriceRecord(
                                symbol=symbol,
                                date=date.fromisoformat(row["date"]),
                                close=float(row["adjClose"]),
                                open=float(row.get("open", 0)) or None,
                                high=float(row.get("high", 0)) or None,
                                low=float(row.get("low", 0)) or None,
                            )
                        )
                except Exception as exc:
                    logger.warning("FMP price fetch failed for %s: %s", symbol, exc)

        logger.info("FMP: fetched %d price records for %d symbols", len(records), len(symbols))
        return records
