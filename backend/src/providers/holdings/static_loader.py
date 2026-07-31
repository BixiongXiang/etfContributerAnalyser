"""
Static holdings loader — reads bundled CSV files shipped with the project.

These CSVs are the primary data source for holdings. They are accurate as of
their as_of_date and should be refreshed periodically using the refresh script
(scripts/refresh_holdings.py).

Live scraping of provider websites is attempted first when available, but
falls back to these files silently when providers change their URLs or
rate-limit requests.
"""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.providers.base import HoldingRecord

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def load_static_holdings(etf_symbol: str) -> tuple[list[HoldingRecord], date]:
    """
    Load holdings from the bundled static CSV for the given ETF.

    CSV columns: symbol, company_name, sector, weight, as_of_date

    Returns:
        (list of HoldingRecord, as_of_date)

    Raises:
        FileNotFoundError: if no static file exists for this ETF.
    """
    path = _STATIC_DIR / f"{etf_symbol.upper()}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No static holdings file for {etf_symbol} at {path}. "
            f"Run scripts/refresh_holdings.py to generate it."
        )

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    # Parse as_of_date from first row
    as_of = date.today()
    if "as_of_date" in df.columns and not df["as_of_date"].isna().all():
        try:
            as_of = date.fromisoformat(str(df["as_of_date"].iloc[0]))
        except (ValueError, TypeError):
            pass

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        try:
            weight = float(row["weight"])
        except (ValueError, TypeError):
            continue

        holdings.append(
            HoldingRecord(
                symbol=symbol,
                company_name=str(row.get("company_name", symbol)).strip(),
                weight=weight,
                sector=str(row.get("sector", "")).strip() or None,
                shares=None,
            )
        )

    logger.info(
        "Loaded %d holdings for %s from static file (as of %s).",
        len(holdings),
        etf_symbol,
        as_of,
    )
    return holdings, as_of
