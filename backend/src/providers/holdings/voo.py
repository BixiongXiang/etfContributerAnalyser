"""
VOO holdings parser — downloads and parses the Vanguard monthly holdings CSV.

Vanguard publishes portfolio holdings CSVs at:
    https://advisors.vanguard.com/web/ecs/fas-portals-holdings/[FUND_ID]/csv

VOO's fund ID is 0968. The CSV format has a multi-line preamble.
Update frequency: monthly (acceptable for MVP per design doc).
"""

import io
import logging
from datetime import date

import httpx
import pandas as pd

from src.providers.base import HoldingRecord

logger = logging.getLogger(__name__)

# Vanguard holdings CSV for VOO (S&P 500 ETF, fund 0968)
_VOO_URL = "https://advisors.vanguard.com/web/ecs/fas-portals-holdings/0968/csv"


async def fetch_voo_holdings() -> tuple[list[HoldingRecord], date]:
    """Download and parse VOO holdings from Vanguard."""
    logger.info("Fetching VOO holdings from Vanguard…")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(_VOO_URL)
        resp.raise_for_status()
        raw = resp.text

    return _parse_vanguard_csv(raw)


def _parse_vanguard_csv(raw: str) -> tuple[list[HoldingRecord], date]:
    """
    Parse Vanguard CSV text into HoldingRecord list.

    Vanguard CSV preamble example:
        Vanguard 500 Index Fund Admiral Shares
        As of date: 06/30/2026
        ...
        Ticker,Security name,Shares,Market value,$,% of funds*,...
    """
    lines = raw.splitlines()
    header_idx = None
    as_of_date = date.today()

    for i, line in enumerate(lines):
        low = line.lower()
        if "as of date" in low or "as of:" in low:
            try:
                # "As of date: 06/30/2026" or "As of: June 30, 2026"
                date_part = line.split(":", 1)[-1].strip().strip('"')
                for fmt in ("%m/%d/%Y", "%B %d, %Y"):
                    try:
                        from datetime import datetime
                        as_of_date = datetime.strptime(date_part, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Locate column header row — look for "Ticker" and "% of funds"
        if "ticker" in low and ("% of funds" in low or "weight" in low):
            header_idx = i
            break

    if header_idx is None:
        logger.error("VOO CSV: could not find column header row. Raw snippet: %s", raw[:500])
        return [], as_of_date

    csv_body = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(csv_body))
    df.columns = [c.strip() for c in df.columns]

    # Find weight column (Vanguard labels it "% of funds*" or similar)
    weight_col = next(
        (c for c in df.columns if "%" in c and ("fund" in c.lower() or "weight" in c.lower())),
        None,
    )
    if weight_col is None:
        logger.error("VOO CSV: cannot identify weight column. Columns: %s", list(df.columns))
        return [], as_of_date

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker or ticker in ("", "NAN") or ticker.startswith("NaN"):
            continue

        try:
            weight = float(str(row[weight_col]).replace("%", "").strip())
        except (ValueError, TypeError):
            continue

        holdings.append(
            HoldingRecord(
                symbol=ticker,
                company_name=str(row.get("Security name", ticker)).strip(),
                weight=weight,
                sector=str(row.get("Sector", "")).strip() or None,
                shares=_to_int(row.get("Shares")),
            )
        )

    logger.info("VOO: parsed %d holdings as of %s", len(holdings), as_of_date)
    return holdings, as_of_date


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None
