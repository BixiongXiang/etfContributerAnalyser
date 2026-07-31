"""Holdings dispatcher — routes ETF symbol to the correct parser."""

from datetime import date

from src.providers.base import HoldingRecord
from src.providers.holdings.qqq import fetch_qqq_holdings
from src.providers.holdings.voo import fetch_voo_holdings
from src.providers.holdings.schd import fetch_schd_holdings


_DISPATCHERS = {
    "QQQ": fetch_qqq_holdings,
    "VOO": fetch_voo_holdings,
    "SCHD": fetch_schd_holdings,
}


async def fetch_holdings(etf_symbol: str) -> tuple[list[HoldingRecord], date]:
    """
    Fetch holdings for the given ETF symbol.

    Raises:
        ValueError: if the ETF symbol is not supported.
    """
    fetcher = _DISPATCHERS.get(etf_symbol.upper())
    if fetcher is None:
        raise ValueError(
            f"No holdings parser registered for '{etf_symbol}'. "
            f"Supported: {list(_DISPATCHERS.keys())}"
        )
    return await fetcher()
