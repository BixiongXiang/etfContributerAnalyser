"""
Abstract base classes for all data providers.

Any concrete provider (yfinance, FMP, …) must implement DataProvider.
Business logic never imports a concrete provider directly — it always
works through this interface so swapping providers is zero-effort.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class HoldingRecord:
    """One row from an ETF holdings file."""
    symbol: str
    company_name: str
    # weight as a percentage, e.g. 8.2 for 8.2%
    weight: float
    sector: Optional[str] = None
    shares: Optional[int] = None


@dataclass
class PriceRecord:
    """End-of-day price for a single symbol on a single date."""
    symbol: str
    date: date
    close: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None


class DataProvider(ABC):
    """Interface that all data providers must satisfy."""

    @abstractmethod
    async def get_holdings(self, etf_symbol: str) -> tuple[list[HoldingRecord], date]:
        """
        Fetch current ETF holdings.

        Returns:
            A tuple of (list of HoldingRecord, as_of_date).
        """
        ...

    @abstractmethod
    async def get_daily_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> list[PriceRecord]:
        """
        Fetch daily closing prices for a list of symbols over a date range.

        Args:
            symbols:  Ticker symbols to fetch.
            start:    First date (inclusive).
            end:      Last date (inclusive).

        Returns:
            List of PriceRecord, one per (symbol, date) pair with available data.
        """
        ...
