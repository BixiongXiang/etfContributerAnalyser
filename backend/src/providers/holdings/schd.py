"""
SCHD holdings parser — downloads and parses the Schwab daily holdings CSV.

Schwab publishes ETF holdings at:
    https://www.schwabassetmanagement.com/resource/schd-fund-downloads

The direct CSV download URL is stable and updated daily.
"""

import io
import logging
from datetime import date

import httpx
import pandas as pd

from src.providers.base import HoldingRecord

logger = logging.getLogger(__name__)

# Schwab SCHD holdings CSV direct download
_SCHD_URL = "https://www.schwabassetmanagement.com/sites/g/files/pcvezn656/files/2024-02/SCHD_HOldings.csv"

# Alternate fallback URL format
_SCHD_URL_ALT = "https://www.schwabassetmanagement.com/resource/schd-fund-downloads"


async def fetch_schd_holdings() -> tuple[list[HoldingRecord], date]:
    """Download and parse SCHD holdings from Schwab."""
    logger.info("Fetching SCHD holdings from Schwab…")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(_SCHD_URL)
        resp.raise_for_status()
        raw = resp.text

    return _parse_schwab_csv(raw)


def _parse_schwab_csv(raw: str) -> tuple[list[HoldingRecord], date]:
    """
    Parse Schwab CSV text into HoldingRecord list.

    Schwab CSV preamble example:
        "Schwab U.S. Dividend Equity ETF"
        "As Of: 07/29/2026"
        ""
        "Symbol","Security Name","% of Net Assets","Shares Held","Market Value",...
    """
    lines = raw.splitlines()
    header_idx = None
    as_of_date = date.today()

    for i, line in enumerate(lines):
        low = line.lower()

        if "as of" in low:
            try:
                date_part = line.split(":", 1)[-1].strip().strip('"').strip()
                for fmt in ("%m/%d/%Y", "%B %d, %Y"):
                    try:
                        from datetime import datetime
                        as_of_date = datetime.strptime(date_part, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Header row contains "Symbol" and "% of Net Assets" or "Weight"
        if "symbol" in low and ("% of net" in low or "weight" in low):
            header_idx = i
            break

    if header_idx is None:
        logger.error("SCHD CSV: could not find column header row. Raw snippet: %s", raw[:500])
        return [], as_of_date

    csv_body = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(csv_body))
    df.columns = [c.strip().strip('"') for c in df.columns]

    weight_col = next(
        (c for c in df.columns if "%" in c and "net" in c.lower()),
        next((c for c in df.columns if "weight" in c.lower()), None),
    )
    if weight_col is None:
        logger.error("SCHD CSV: cannot identify weight column. Columns: %s", list(df.columns))
        return [], as_of_date

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        ticker = str(row.get("Symbol", "")).strip().strip('"').upper()
        if not ticker or ticker in ("", "NAN"):
            continue

        try:
            weight = float(str(row[weight_col]).replace("%", "").strip())
        except (ValueError, TypeError):
            continue

        holdings.append(
            HoldingRecord(
                symbol=ticker,
                company_name=str(row.get("Security Name", ticker)).strip().strip('"'),
                weight=weight,
                sector=str(row.get("Sector", "")).strip() or None,
                shares=_to_int(row.get("Shares Held")),
            )
        )

    logger.info("SCHD: parsed %d holdings as of %s", len(holdings), as_of_date)
    return holdings, as_of_date


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None
