"""
Provider factory — returns the configured DataProvider singleton.

Import get_price_provider() wherever you need to fetch prices.
"""

from src.config import settings
from src.providers.base import DataProvider

_provider: DataProvider | None = None


def get_price_provider() -> DataProvider:
    """Return the active price provider based on DATA_PROVIDER setting."""
    global _provider
    if _provider is not None:
        return _provider

    if settings.data_provider.lower() == "fmp":
        from src.providers.fmp_provider import FMPProvider
        _provider = FMPProvider()
    else:
        from src.providers.yfinance_provider import YFinanceProvider
        _provider = YFinanceProvider()

    return _provider
