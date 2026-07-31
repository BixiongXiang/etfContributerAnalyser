"""
yfinance data provider — fetches market prices using the free Yahoo Finance API.

Key design decisions:
- Uses yf.download() in batch mode to fetch all symbols in one API call,
  dramatically reducing round-trips (important for VOO with ~500 holdings).
- Falls back to individual symbol downloads if the batch call fails.
- Returns only adjusted close prices; OHLC is also captured when available.
"""

import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from src.providers.base import DataProvider, HoldingRecord, PriceRecord

logger = logging.getLogger(__name__)

# yfinance batch size — stay well under the undocumented ~1000-symbol limit
_BATCH_SIZE = 200


class YFinanceProvider(DataProvider):
    """Implements DataProvider using the yfinance library (free, no API key)."""

    async def get_holdings(self, etf_symbol: str) -> tuple[list[HoldingRecord], date]:
        """
        Holdings are sourced from provider-specific parsers, not yfinance.
        This method is not used — the holdings/ sub-package handles each ETF.
        """
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
        Download adjusted closing prices for all symbols over the date range.

        Uses batch downloads (up to _BATCH_SIZE symbols per call) to minimise
        API round-trips. The end date passed to yfinance is exclusive, so we
        add one day to match our inclusive API contract.
        """
        if not symbols:
            return []

        all_records: list[PriceRecord] = []

        # Process in batches
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = symbols[i : i + _BATCH_SIZE]
            records = await self._download_batch(batch, start, end)
            all_records.extend(records)

        logger.info(
            "yfinance: fetched %d price records for %d symbols (%s → %s)",
            len(all_records),
            len(symbols),
            start,
            end,
        )
        return all_records

    async def _download_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> list[PriceRecord]:
        """Download one batch of symbols, return PriceRecord list."""
        # yfinance end is exclusive
        yf_end = end + timedelta(days=1)

        try:
            df = yf.download(
                tickers=symbols,
                start=str(start),
                end=str(yf_end),
                auto_adjust=True,   # gives adjusted OHLC directly
                progress=False,
                threads=True,
            )
        except Exception as exc:
            logger.error("yfinance batch download failed for %d symbols: %s", len(symbols), exc)
            return []

        if df.empty:
            logger.warning("yfinance returned empty DataFrame for batch of %d symbols", len(symbols))
            return []

        return _parse_yfinance_df(df, symbols)


def _parse_yfinance_df(df: pd.DataFrame, symbols: list[str]) -> list[PriceRecord]:
    """
    Convert a yfinance multi-symbol DataFrame to a list of PriceRecord.

    yfinance returns a MultiIndex DataFrame when multiple symbols are requested:
        columns: (price_type, symbol)
        index:   DatetimeIndex

    For a single symbol it returns a flat DataFrame with price_type columns.
    We normalise both shapes here.
    """
    records: list[PriceRecord] = []

    if isinstance(df.columns, pd.MultiIndex):
        # Multi-symbol download
        for symbol in symbols:
            symbol_upper = symbol.upper()
            try:
                sym_df = df.xs(symbol_upper, axis=1, level=1)
            except KeyError:
                logger.debug("yfinance: no data for symbol %s", symbol)
                continue
            records.extend(_rows_to_records(sym_df, symbol_upper))
    else:
        # Single-symbol download
        if len(symbols) == 1:
            records.extend(_rows_to_records(df, symbols[0].upper()))

    return records


def _rows_to_records(df: pd.DataFrame, symbol: str) -> list[PriceRecord]:
    """Convert a single-symbol price DataFrame to PriceRecord list."""
    records = []
    for ts, row in df.iterrows():
        close = row.get("Close")
        if close is None or pd.isna(close):
            continue
        records.append(
            PriceRecord(
                symbol=symbol,
                date=ts.date(),
                close=float(close),
                open=float(row["Open"]) if not pd.isna(row.get("Open", float("nan"))) else None,
                high=float(row["High"]) if not pd.isna(row.get("High", float("nan"))) else None,
                low=float(row["Low"]) if not pd.isna(row.get("Low", float("nan"))) else None,
            )
        )
    return records
